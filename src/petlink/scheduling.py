"""Deterministic calendar recurrence and UTC reminder delivery."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import text

DEFAULT_SCHEDULE = dict(frequency="none", reminder_time=None, timezone="Asia/Kolkata")


def validate_schedule(schedule, due_date):
    if not isinstance(schedule, dict) or set(schedule) != set(DEFAULT_SCHEDULE):
        raise ValueError("Review frequency, reminder time and timezone.")
    if schedule["frequency"] not in ("none", "daily", "weekly"):
        raise ValueError("Choose no repeat, daily or weekly.")
    clock = schedule["reminder_time"]
    if clock is not None:
        try:
            if time.fromisoformat(clock).strftime("%H:%M") != clock:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Use HH:MM (24-hour) for the reminder, or leave it empty.")
    try:
        ZoneInfo(schedule["timezone"])
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        raise ValueError("Enter a timezone name such as Asia/Kolkata or UTC.")
    if (clock is not None or schedule["frequency"] != "none") and not due_date:
        raise ValueError("Set a due/start date for a reminder or recurring task.")


def reminder_utc(day, clock, zone):
    """First fold on autumn overlap; move spring-gap times to the next valid minute."""
    naive = datetime.combine(day, time.fromisoformat(clock or "00:00"))
    zone = ZoneInfo(zone)
    for minutes in range(1561):
        local = naive + timedelta(minutes=minutes)
        candidate = local.replace(tzinfo=zone, fold=0).astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None) == local:
            return candidate.isoformat(timespec="microseconds")
    raise ValueError("This local date/time does not exist. Choose another reminder time.")


def get_schedule(conn, task_id):
    row = conn.execute(text("SELECT * FROM task_schedules WHERE task_id=:id"), {"id": task_id}).mappings().first()
    return {key: row[key] for key in DEFAULT_SCHEDULE} if row else dict(DEFAULT_SCHEDULE)


def add_occurrence(conn, task_id, schedule, revision, day):
    conn.execute(text("INSERT OR IGNORE INTO task_occurrences(task_id,schedule_revision,scheduled_date,reminder_at) VALUES(:task,:revision,:day,:reminder)"),
        dict(task=task_id, revision=revision, day=day.isoformat(),
             reminder=reminder_utc(day, schedule["reminder_time"], schedule["timezone"])))


def save_schedule(conn, task_id, schedule, due_date, now, *, reset=False):
    old = conn.execute(text("SELECT * FROM task_schedules WHERE task_id=:id"), {"id": task_id}).mappings().first()
    same = old is not None and all(old[key] == schedule[key] for key in DEFAULT_SCHEDULE)
    if same and not reset:
        return
    revision = old["revision"] + 1 if old else 1
    conn.execute(text("UPDATE task_occurrences SET cancelled_at=:now WHERE task_id=:id AND completed_at IS NULL AND cancelled_at IS NULL"), {"id": task_id, "now": now})
    conn.execute(text("INSERT INTO task_schedules(task_id,frequency,reminder_time,timezone,revision) VALUES(:id,:frequency,:reminder_time,:timezone,:revision) ON CONFLICT(task_id) DO UPDATE SET frequency=excluded.frequency,reminder_time=excluded.reminder_time,timezone=excluded.timezone,revision=excluded.revision"),
        dict(id=task_id, revision=revision, **schedule))
    if due_date and (schedule["frequency"] != "none" or schedule["reminder_time"]):
        add_occurrence(conn, task_id, schedule, revision, date.fromisoformat(due_date))


def poll_schedules(conn, now):
    if now.tzinfo is None:
        raise ValueError("The reminder clock must include a timezone.")
    now = now.astimezone(timezone.utc)
    schedules = conn.execute(text("SELECT s.*,t.due_date FROM task_schedules s JOIN tasks t ON t.id=s.task_id WHERE t.deleted_at IS NULL AND t.status!='done' AND t.due_date IS NOT NULL AND (s.frequency!='none' OR s.reminder_time IS NOT NULL)")).mappings().all()
    for schedule in schedules:
        last = conn.execute(text("SELECT MAX(scheduled_date) FROM task_occurrences WHERE task_id=:id AND schedule_revision=:revision"),
            {"id": schedule["task_id"], "revision": schedule["revision"]}).scalar()
        day = date.fromisoformat(last or schedule["due_date"])
        step = 1 if schedule["frequency"] == "daily" else 7
        if last:
            if schedule["frequency"] == "none":
                continue
            try:
                day += timedelta(days=step)
            except OverflowError:
                continue
        today = now.astimezone(ZoneInfo(schedule["timezone"])).date()
        # Bounded catch-up retains progress across polls; no missing day is marked complete.
        for _ in range(100):
            if day > today:
                break
            add_occurrence(conn, schedule["task_id"], schedule, schedule["revision"], day)
            if schedule["frequency"] == "none":
                break
            try:
                day += timedelta(days=step)
            except OverflowError:
                break
    due = conn.execute(text("SELECT o.id,o.task_id,o.scheduled_date,t.title,s.timezone,s.reminder_time FROM task_occurrences o JOIN tasks t ON t.id=o.task_id JOIN task_schedules s ON s.task_id=t.id AND s.revision=o.schedule_revision WHERE o.cancelled_at IS NULL AND o.completed_at IS NULL AND o.reminder_at<=:now AND t.deleted_at IS NULL AND t.status!='done' AND NOT EXISTS(SELECT 1 FROM notifications n WHERE n.event_key='occurrence:' || o.id) ORDER BY o.reminder_at,o.id LIMIT 1000"), {"now": now.isoformat(timespec="microseconds")}).mappings()
    added = 0
    for occurrence in due:
        statement = f"{occurrence['title']} — reminder for {occurrence['scheduled_date']} {occurrence['reminder_time'] or '00:00'} ({occurrence['timezone']}). Review this occurrence in Tasks & Pending."
        result = conn.execute(text("INSERT OR IGNORE INTO notifications(task_id,due_date,statement,created_at,event_key) VALUES(:task,:day,:statement,:now,:key)"),
            dict(task=occurrence["task_id"], day=occurrence["scheduled_date"], statement=statement,
                 now=now.isoformat(timespec="microseconds"), key=f"occurrence:{occurrence['id']}"))
        added += result.rowcount
    return added
