"""SQLAlchemy/SQLite persistence and the explicit task-confirmation boundary."""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from .scheduling import get_schedule, poll_schedules, save_schedule, validate_schedule


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def default_database_path():
    if os.environ.get("PETLINK_DATA_DIR"):
        return Path(os.environ["PETLINK_DATA_DIR"]) / "petlink.sqlite3"
    root = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home() / ".local" / "share"
    return root / "PetLink" / "petlink.sqlite3"


class Database:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from sqlalchemy.engine import URL
        self.engine = create_engine(URL.create("sqlite", database=str(self.path)), connect_args={"timeout": 2, "check_same_thread": False})
        @event.listens_for(self.engine, "connect")
        def configure(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def close(self):
        self.engine.dispose()

    def check_due_notifications(self, today=None):
        """Once per task/due-date; run only while the manually launched app is open."""
        today = today or date.today()
        with self.engine.begin() as conn:
            rows = conn.execute(text("SELECT t.id,t.title,t.due_date FROM tasks t LEFT JOIN task_schedules s ON s.task_id=t.id WHERE t.deleted_at IS NULL AND t.status!='done' AND t.due_date<=:today AND (s.task_id IS NULL OR (s.frequency='none' AND s.reminder_time IS NULL))"), {"today": today.isoformat()}).mappings()
            added = 0
            for task in rows:
                statement = f"{task['title']} — due {task['due_date']}. Open Tasks & Pending to review it."
                result = conn.execute(text("INSERT OR IGNORE INTO notifications(task_id,due_date,statement,created_at,event_key) VALUES(:task,:due,:statement,:now,:key)"),
                    {"task": task["id"], "due": task["due_date"], "statement": statement, "now": utc_now(), "key": f"due:{task['id']}:{task['due_date']}"})
                added += result.rowcount
            return added

    def poll_reminders(self, now=None):
        with self.engine.begin() as conn:
            return poll_schedules(conn, now or datetime.now(timezone.utc))

    def occurrences(self, limit=100):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text("SELECT o.*,t.title,t.version AS task_version,s.frequency,s.timezone,s.reminder_time AS local_time FROM task_occurrences o JOIN tasks t ON t.id=o.task_id JOIN task_schedules s ON s.task_id=t.id AND s.revision=o.schedule_revision WHERE o.cancelled_at IS NULL AND t.deleted_at IS NULL AND t.status!='done' ORDER BY o.scheduled_date DESC,o.id DESC LIMIT :limit"), {"limit": limit}).mappings()]

    def notifications(self, limit=100):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text("SELECT * FROM notifications ORDER BY id DESC LIMIT :limit"), {"limit": limit}).mappings()]

    def unread_notifications(self):
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM notifications WHERE read_at IS NULL")).scalar_one()

    def read_notification(self, notification_id):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE notifications SET read_at=:now WHERE id=:id AND read_at IS NULL"), {"id": notification_id, "now": utc_now()})

    def conversation(self):
        with self.engine.begin() as conn:
            current = conn.execute(text("SELECT id FROM conversations ORDER BY id DESC LIMIT 1")).scalar()
            return current or conn.execute(text("INSERT INTO conversations(created_at,draft) VALUES(:now,'')"), {"now": utc_now()}).lastrowid

    def messages(self, conversation_id, limit=60):
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM messages WHERE conversation_id=:id ORDER BY id DESC LIMIT :limit"),
                                {"id": conversation_id, "limit": limit}).mappings().all()
            return [dict(row) for row in reversed(rows)]

    def add_message(self, conversation_id, role, content, status="complete"):
        with self.engine.begin() as conn:
            result = conn.execute(text("INSERT INTO messages(conversation_id,role,content,status,created_at) VALUES(:conversation,:role,:content,:status,:now)"),
                dict(conversation=conversation_id, role=role, content=content, status=status, now=utc_now()))
            if role == "user":
                conn.execute(text("UPDATE conversations SET draft='' WHERE id=:id"), {"id": conversation_id})
            return result.lastrowid

    def save_chat_draft(self, conversation_id, draft):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE conversations SET draft=:draft WHERE id=:id"), {"id": conversation_id, "draft": draft})

    def chat_draft(self, conversation_id):
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT draft FROM conversations WHERE id=:id"), {"id": conversation_id}).scalar() or ""

    def tasks(self, limit=100, offset=0):
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM tasks WHERE deleted_at IS NULL ORDER BY id DESC LIMIT :limit OFFSET :offset"), {"limit": limit, "offset": offset}).mappings()
            return [{**dict(row), "schedule": get_schedule(conn, row["id"])} for row in rows]

    def pending(self, limit=100, offset=0):
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(text("SELECT * FROM pending_actions WHERE status='pending' ORDER BY id DESC LIMIT :limit OFFSET :offset"), {"limit": limit, "offset": offset}).mappings()]

    @staticmethod
    def validate(actions):
        if not isinstance(actions, list) or not 1 <= len(actions) <= 20:
            raise ValueError("A proposal needs between 1 and 20 actions.")
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError("Each proposed action must be an object.")
            if action.get("kind") not in ("create", "update", "delete", "complete_occurrence"):
                raise ValueError("Unknown task action.")
            if action["kind"] != "create" and (type(action.get("task_id")) is not int or type(action.get("version")) is not int):
                raise ValueError("Select an exact task and version.")
            if action["kind"] == "complete_occurrence" and type(action.get("occurrence_id")) is not int:
                raise ValueError("Select an exact occurrence.")
            if action["kind"] not in ("delete", "complete_occurrence"):
                values = action.get("values", {})
                required = {"title", "description", "status", "priority", "due_date"}
                if not isinstance(values, dict) or not required <= set(values) or set(values) - required - {"schedule"}:
                    raise ValueError("Review all task fields before confirming.")
                if not isinstance(values["title"], str) or not 1 <= len(values["title"].strip()) <= 200:
                    raise ValueError("Enter a title of 1–200 characters.")
                if not isinstance(values["description"], str) or len(values["description"]) > 10000:
                    raise ValueError("Keep the description under 10,000 characters.")
                if values["status"] not in ("pending", "in_progress", "done") or values["priority"] not in ("low", "normal", "high"):
                    raise ValueError("Choose a valid status and priority.")
                if values["due_date"] is not None:
                    try:
                        parsed = date.fromisoformat(values["due_date"])
                        if parsed.isoformat() != values["due_date"]:
                            raise ValueError()
                    except (TypeError, ValueError):
                        raise ValueError("Use YYYY-MM-DD for the due date, or leave it empty.")
                if "schedule" in values:
                    validate_schedule(values["schedule"], values["due_date"])

    def propose(self, actions):
        self.validate(actions)
        with self.engine.begin() as conn:
            return conn.execute(text("INSERT INTO pending_actions(payload,revision,status,created_at) VALUES(:payload,1,'pending',:now)"),
                {"payload": json.dumps(actions), "now": utc_now()}).lastrowid

    def revise(self, pending_id, revision, actions):
        self.validate(actions)
        with self.engine.begin() as conn:
            result = conn.execute(text("UPDATE pending_actions SET payload=:payload,revision=revision+1 WHERE id=:id AND revision=:revision AND status='pending'"),
                {"id": pending_id, "revision": revision, "payload": json.dumps(actions)})
            if result.rowcount != 1:
                raise ValueError("This draft changed. Reload it before reviewing again.")

    def discard(self, pending_id, revision):
        with self.engine.begin() as conn:
            result = conn.execute(text("UPDATE pending_actions SET status='discarded' WHERE id=:id AND revision=:revision AND status='pending'"),
                                  {"id": pending_id, "revision": revision})
            if result.rowcount != 1:
                raise ValueError("This draft changed. Reload it first.")

    def confirm(self, pending_id, revision):
        """Call only from explicit Confirm. All actions + audit commit together."""
        with self.engine.begin() as conn:
            # Claim this revision before any task writes; also serializes SQLite writers.
            claimed = conn.execute(text("UPDATE pending_actions SET status='applied' WHERE id=:id AND revision=:revision AND status='pending'"),
                                   {"id": pending_id, "revision": revision})
            if claimed.rowcount != 1:
                raise ValueError("This proposal was already applied or changed. Reload the draft.")
            actions = json.loads(conn.execute(text("SELECT payload FROM pending_actions WHERE id=:id"), {"id": pending_id}).scalar_one())
            self.validate(actions)
            ids = []
            for action in actions:
                now, before = utc_now(), None
                kind = action["kind"]
                if kind != "create":
                    row = conn.execute(text("SELECT * FROM tasks WHERE id=:id AND deleted_at IS NULL AND version=:version"),
                                       {"id": action["task_id"], "version": action["version"]}).mappings().first()
                    if row is None:
                        raise ValueError("A task changed or was removed. Discard this draft, select the current saved task, and start a new edit.")
                    before = dict(row)
                    before["schedule"] = get_schedule(conn, action["task_id"])
                if kind == "complete_occurrence":
                    occurrence = conn.execute(text("SELECT o.* FROM task_occurrences o JOIN task_schedules s ON s.task_id=o.task_id AND s.revision=o.schedule_revision WHERE o.id=:id AND o.task_id=:task AND o.completed_at IS NULL AND o.cancelled_at IS NULL"), {"id": action["occurrence_id"], "task": action["task_id"]}).mappings().first()
                    if occurrence is None:
                        raise ValueError("This occurrence changed or is already complete. Refresh and review it again.")
                    conn.execute(text("UPDATE task_occurrences SET completed_at=:now WHERE id=:id"), {"now": now, "id": occurrence["id"]})
                    after_occurrence = {**dict(occurrence), "completed_at": now}
                    conn.execute(text("INSERT INTO audit_events(pending_id,action,task_id,before_json,after_json,created_at) VALUES(:pending,:action,:task,:before,:after,:now)"),
                        dict(pending=pending_id, action=kind, task=action["task_id"], before=json.dumps(dict(occurrence)), after=json.dumps(after_occurrence), now=now))
                    ids.append(action["task_id"])
                    continue
                if kind == "create":
                    task_id = conn.execute(text("INSERT INTO tasks(title,description,status,priority,due_date,created_at,updated_at,version) VALUES(:title,:description,:status,:priority,:due_date,:now,:now,1)"),
                                           {**action["values"], "now": now}).lastrowid
                else:
                    task_id = action["task_id"]
                    if kind == "delete":
                        conn.execute(text("UPDATE tasks SET deleted_at=:now,updated_at=:now,version=version+1 WHERE id=:id"), {"id": task_id, "now": now})
                        conn.execute(text("UPDATE task_occurrences SET cancelled_at=:now WHERE task_id=:id AND completed_at IS NULL AND cancelled_at IS NULL"), {"id": task_id, "now": now})
                    else:
                        conn.execute(text("UPDATE tasks SET title=:title,description=:description,status=:status,priority=:priority,due_date=:due_date,updated_at=:now,version=version+1 WHERE id=:id"),
                                     {**action["values"], "id": task_id, "now": now})
                if kind != "delete":
                    values = action["values"]
                    schedule = values.get("schedule", get_schedule(conn, task_id))
                    validate_schedule(schedule, values["due_date"])
                    save_schedule(conn, task_id, schedule, values["due_date"], now,
                                  reset=bool(before and before["due_date"] != values["due_date"]))
                after = dict(conn.execute(text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}).mappings().one())
                after["schedule"] = get_schedule(conn, task_id)
                conn.execute(text("INSERT INTO audit_events(pending_id,action,task_id,before_json,after_json,created_at) VALUES(:pending,:action,:task,:before,:after,:now)"),
                             dict(pending=pending_id, action=kind, task=task_id, before=json.dumps(before), after=json.dumps(after), now=now))
                ids.append(task_id)
            return ids
