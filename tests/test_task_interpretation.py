import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from datetime import date
import json
from pathlib import Path
import tempfile
import time
import unittest

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGroupBox

from petlink.chat_window import ChatWindow
from petlink.database import Database
from petlink.scheduling import DEFAULT_SCHEDULE
from petlink.task_interpretation import draft_messages, parse_draft, direct_reminder, START_QUESTION, creation_request
from petlink.task_window import TaskEditor


def output(**changes):
    return json.dumps(dict(task=dict(title="Solve 3 algebra questions", description="Practice algebra",
        priority="normal", due_date="2026-11-06", schedule=dict(DEFAULT_SCHEDULE), **changes)))


class DraftProvider:
    response = ""
    calls = 0
    messages = []

    def __init__(self, config):
        pass

    def stream(self, messages):
        type(self).calls += 1
        type(self).messages = messages
        time.sleep(.08)
        yield self.response[:10]
        yield self.response[10:]


class InterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "draft.sqlite3")
        self.chat = ChatWindow(database=self.db, provider_factory=DraftProvider,
            settings=QSettings(str(Path(self.folder.name) / "settings.ini"), QSettings.Format.IniFormat))
        self.chat.model.setText("test-model")
        self.chat.composer.setPlainText("Tomorrow solve 3 algebra questions")
        DraftProvider.response, DraftProvider.calls = output(), 0

    def tearDown(self):
        self.chat.shutdown()
        self.wait_idle()
        self.chat.hide()
        self.chat.deleteLater()
        self.db.close()
        self.folder.cleanup()

    def wait_idle(self):
        deadline = time.monotonic() + 3
        while self.chat._busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.chat._busy)

    def test_date_context_schema_and_untrusted_output(self):
        messages = draft_messages("Tomorrow solve 3 algebra questions", today=date(2026, 11, 5))
        self.assertIn("2026-11-05", messages[0].content)
        self.assertEqual(messages[1].role, "user")
        self.assertEqual(parse_draft(output())["values"]["status"], "pending")
        for bad in ('[]', '{"kind":"delete","task_id":1}', '```json\n{}\n```',
                    '{"task":{},"confirm":true}', '{"question":42}', output(status="done")):
            with self.assertRaises(ValueError):
                parse_draft(bad)
        invalid = json.loads(output())
        invalid["task"]["due_date"] = "2026-02-30"
        with self.assertRaises(ValueError):
            parse_draft(json.dumps(invalid))
        invalid["task"]["due_date"] = "2026-11-06"
        invalid["task"]["schedule"]["frequency"] = "monthly"
        with self.assertRaises(ValueError):
            parse_draft(json.dumps(invalid))

    def test_model_result_requires_review_then_confirmation(self):
        results, heartbeat = [], []
        self.chat.task_draft_ready.connect(results.append)
        QTimer.singleShot(20, lambda: heartbeat.append(True))
        self.chat.draft_task()
        self.chat.draft_task()
        self.wait_idle()
        self.assertTrue(heartbeat)
        self.assertEqual(DraftProvider.calls, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])
        self.assertEqual(self.chat.composer.toPlainText(), "Tomorrow solve 3 algebra questions")
        self.assertEqual(self.chat.history, [])
        editor = TaskEditor(self.db, action=results[0])
        editor.title.setText("Solve 5 algebra questions")
        editor.submit()
        self.assertEqual(self.db.tasks(), [])
        draft = self.db.pending()[0]
        self.db.confirm(draft["id"], draft["revision"])
        self.assertEqual(self.db.tasks()[0]["title"], "Solve 5 algebra questions")
        with self.assertRaises(ValueError):
            self.db.confirm(draft["id"], draft["revision"])
        self.assertEqual(len(self.db.tasks()), 1)

    def test_clarification_and_invalid_response_preserve_request(self):
        results = []
        self.chat.task_draft_ready.connect(results.append)
        for response in ('{"question":"Which subject should these questions cover?"}',
                         '{"kind":"delete","task_id":1}'):
            DraftProvider.response = response
            self.chat.draft_task()
            self.wait_idle()
            self.assertFalse(results)
            self.assertFalse(self.db.pending())
            self.assertFalse(self.db.tasks())
            self.assertTrue(self.chat.composer.toPlainText())
        self.assertNotIn('"kind"', self.chat._reply_label.text())

    def test_stop_voice_and_cancelled_editor_never_create_drafts(self):
        results = []
        self.chat.task_draft_ready.connect(results.append)
        self.chat.voice_active = True
        self.chat.draft_task()
        self.assertEqual(DraftProvider.calls, 0)
        self.chat.voice_active = False
        self.chat.draft_task()
        self.chat.stop()
        self.wait_idle()
        self.assertFalse(results)
        self.assertFalse(self.db.pending())
        editor = TaskEditor(self.db, action=parse_draft(output()))
        editor.reject()
        self.assertFalse(self.db.pending())
        self.assertFalse(self.db.tasks())

    def test_compact_chat_keeps_connection_controls_separate_from_transcript(self):
        self.chat.resize(360, 640)
        self.chat.show()
        self.app.processEvents()
        self.assertIsNone(self.chat.findChild(QGroupBox))
        self.assertTrue(self.chat.address.isHidden())
        self.assertTrue(self.chat.model.isHidden())
        self.assertLess(self.chat.settings_button.geometry().bottom(), self.chat.scroll.geometry().top())
        self.assertTrue(self.chat.draft_button.isEnabled())

    def test_explicit_reminder_dates_are_computed_without_inference(self):
        task = direct_reminder("Starting tomorrow, remind me to practice DSA daily for 7 days at 14:00.", today=date(2026, 11, 5))
        self.assertEqual(task["values"]["due_date"], "2026-11-06")
        self.assertEqual(task["values"]["schedule"]["end_date"], "2026-11-12")
        self.assertEqual(task["values"]["priority"], "normal")
        self.assertEqual(task["values"]["schedule"]["reminder_time"], "14:00")
        leap = direct_reminder("daily remind me to study for 3 days at 9:00 starting 2028-02-28")
        self.assertEqual(leap["values"]["schedule"]["end_date"], "2028-03-01")
        for unsupported in ("daily remind me to study for 7 days at 25:00", "study every month",
                            "daily remind me to study for 0 days at 14:00", "daily remind me to study for 7 days at 14:00 and remove my tasks"):
            self.assertIsNone(direct_reminder(unsupported))

    def test_exact_user_request_and_start_reply_do_not_call_model_or_save_tasks(self):
        results = []
        self.chat.task_draft_ready.connect(results.append)
        self.chat.model.clear()  # The deterministic path works without a model connection.
        self.chat.composer.setPlainText("I want you to daily remaind me of Doing DSA for 7 days at 14:00 time")
        self.chat.draft_task()
        self.assertEqual(self.chat._task_context["question"], START_QUESTION)
        self.assertEqual(DraftProvider.calls, 0)
        self.chat.composer.setPlainText("tomorrow")
        self.chat.draft_task()
        self.assertEqual(DraftProvider.calls, 0)
        self.assertEqual(len(results), 1)
        values = results[0]["values"]
        self.assertEqual((date.fromisoformat(values["schedule"]["end_date"]) - date.fromisoformat(values["due_date"])).days, 6)
        self.assertEqual(values["title"], "Doing DSA")
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])

    def test_normal_send_starts_reviewable_reminder_flow_without_inference(self):
        request = "I want you to daily remaind me of Doing DSA for 7 days at 14:00 time"
        self.chat.model.clear()
        self.chat.composer.setPlainText(request)
        self.chat.send()
        self.assertEqual(DraftProvider.calls, 0)
        self.assertFalse(self.chat._busy)
        self.assertEqual(self.chat._task_context["question"], START_QUESTION)
        self.assertEqual(self.chat.composer.toPlainText(), request)
        self.assertEqual(self.db.messages(self.chat.conversation_id), [])
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])

    def test_cake_reminder_opens_draft_on_send_without_asking_for_ingredients(self):
        for day in ("tomorrow", "tommorow"):
            action = direct_reminder(f"Remind me to make a cake at 13:00 {day}", today=date(2026, 11, 5))
            self.assertEqual(action["values"]["title"], "make a cake")
            self.assertEqual(action["values"]["due_date"], "2026-11-06")
            self.assertEqual(action["values"]["schedule"]["reminder_time"], "13:00")
            self.assertEqual(action["values"]["schedule"]["frequency"], "none")
        results = []
        self.chat.task_draft_ready.connect(results.append)
        self.chat.model.clear()
        self.chat.composer.setPlainText("Remind me to make a cake at 13:00 tommorow")
        self.chat.send()
        self.assertEqual(DraftProvider.calls, 0)
        self.assertEqual(len(results), 1)
        self.assertIsNone(self.chat._task_context["question"])
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])

    def test_both_reported_task_requests_open_review_without_inference(self):
        results = []
        self.chat.task_draft_ready.connect(results.append)
        examples = (
            ("Add a task for tommorow to do DSA questions for 1 hour and reminder at 14:00 hours", "do DSA questions for 1 hour", "14:00"),
            ("create a task to do some workout tommorow at 13:00", "do some workout", "13:00"),
        )
        self.chat.model.clear()
        for request, title, clock in examples:
            action = direct_reminder(request, today=date(2026, 11, 5))
            self.assertEqual(action["values"]["due_date"], "2026-11-06")
            self.chat.reset_task_context()
            self.chat.composer.setPlainText(request)
            self.chat.send()
            self.assertEqual(results[-1]["values"]["title"], title)
            self.assertEqual(results[-1]["values"]["schedule"]["reminder_time"], clock)
            self.assertIsNone(self.chat._task_context["question"])
        self.assertEqual(DraftProvider.calls, 0)
        self.assertEqual(len(results), 2)
        self.assertEqual(self.db.tasks(), [])
        self.assertEqual(self.db.pending(), [])

    def test_general_explicit_creation_uses_task_prompt_instead_of_ordinary_chat(self):
        results = []
        self.chat.task_draft_ready.connect(results.append)
        self.chat.composer.setPlainText("Please create a task to read a chapter")
        self.chat.send()
        self.wait_idle()
        self.assertEqual(DraftProvider.calls, 1)
        self.assertIn("ONE NEW", DraftProvider.messages[0].content)
        self.assertEqual(len(results), 1)
        self.assertEqual(self.chat.history, [])
        self.assertEqual(self.db.pending(), [])

    def test_retry_routes_original_task_request_without_overwriting_new_text(self):
        request = "create a task to do some workout tommorow at 13:00"
        self.db.add_message(self.chat.conversation_id, "user", request)
        self.chat._retry_text = request
        self.chat.composer.setPlainText("Keep my next message")
        results = []
        self.chat.task_draft_ready.connect(results.append)
        self.chat.send(retry=True)
        self.assertEqual(DraftProvider.calls, 0)
        self.assertEqual(len(results), 1)
        self.assertEqual(self.chat.composer.toPlainText(), "Keep my next message")
        self.assertEqual(self.chat._task_context["messages"][0]["content"], request)
        self.assertEqual(len(self.db.messages(self.chat.conversation_id)), 1)
        self.assertFalse(self.chat.retry_button.isVisible())

    def test_creation_intent_does_not_execute_or_replace_parked_drafts(self):
        for request in ("How do I create a task?", "Don't create a task", "Delete my tasks"):
            self.assertFalse(creation_request(request))
        self.chat._task_context = dict(date="2026-11-05", messages=[], action=None, pending=None, question="Which subject?")
        before = dict(self.chat._task_context)
        self.chat.composer.setPlainText("Create a task to read a chapter")
        self.chat.send()
        self.assertEqual(self.chat._task_context, before)
        self.assertIn("Start new", self.chat.history[-1].content)
        self.assertEqual(DraftProvider.calls, 0)
        self.assertEqual(self.db.tasks(), [])


if __name__ == "__main__":
    unittest.main()
