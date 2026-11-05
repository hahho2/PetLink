"""Local chat UI, bounded history, and background model requests."""
from __future__ import annotations

from threading import Event, Thread
from copy import deepcopy
from datetime import datetime
import json
import time
from zoneinfo import ZoneInfo
from sqlalchemy.exc import SQLAlchemyError

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QSettings
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QSystemTrayIcon, QMenu, QVBoxLayout, QWidget, QLayout,
)

from .models import ChatMessage, ModelError, create_provider
from .model_settings import (CredentialStore, ModelSettings, PROVIDERS,
    connection_config, load_connection, local_config, save_connection_details)
from .ui_theme import stylesheet, COLORS

SYSTEM = ChatMessage("system", "You are PetLink, a work and productivity assistant. "
    "Discuss tasks, goals, study and planning. Keep replies to 1–3 short sentences "
    "unless the user asks for detail. Do not invent activities or expand a simple reminder into a study plan. "
    "Normal chat cannot save or schedule anything. For a task/reminder request, point to "
    "Draft task from message, then Review draft and Confirm changes. Never claim you saved it. "
    "Ask one focused question only when an essential detail is missing.")


class Composer(QPlainTextEdit):
    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._composing = False

    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                and not self._composing):
            self.send_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class RequestSignals(QObject):
    chunk = Signal(int, str)
    finished = Signal(int, str, str)  # job, outcome, safe user-facing detail


def request_budget(provider):
    return max(90, getattr(getattr(provider, "config", None), "timeout_seconds", 25) + 60)


def run_request(signals, job, cancel, provider, history=None):
    """Daemon worker; Qt's queued signals are the only route back to widgets."""
    try:
        if history is None:
            outcome = "healthy" if provider.health_check() else "error"
            detail = "Model service is reachable." if outcome == "healthy" else "Cannot reach the service. Check connection settings, then test again."
        else:
            start, flush = time.monotonic(), time.monotonic()
            pending, length = "", 0
            for chunk in provider.stream(history):
                if cancel.is_set():
                    break
                if time.monotonic() - start > request_budget(provider):
                    raise TimeoutError()
                if not isinstance(chunk, str):
                    raise ValueError("Invalid text")
                pending += chunk
                length += len(chunk)
                if length > 16000:
                    raise ValueError("Response too long")
                if time.monotonic() - flush >= .05:
                    signals.chunk.emit(job, pending)
                    pending, flush = "", time.monotonic()
            if pending and not cancel.is_set():
                signals.chunk.emit(job, pending)
            outcome = "cancelled" if cancel.is_set() else "complete"
            detail = "Response stopped." if cancel.is_set() else "Ready."
        signals.finished.emit(job, outcome, detail)
    except Exception as error:
        try:
            cause = error.__cause__
            timed_out = isinstance(error, TimeoutError) or isinstance(cause, TimeoutError)
            detail = ("The model did not finish before the time limit. A local model may still be loading or thinking. "
                      "For Ollama, try Skip extended thinking in Model settings, then retry.") if timed_out else (
                      "The model did not finish. " + str(error) if isinstance(error, ModelError) else
                      "The model did not finish. Check the server and model name, then retry.")
            signals.finished.emit(job, "cancelled" if cancel.is_set() else "error",
                "Response stopped." if cancel.is_set() else detail)
        except RuntimeError:
            pass


class ChatWindow(QWidget):
    activity = Signal(str)
    tasks_requested = Signal()
    voice_requested = Signal()
    task_draft_ready = Signal(object)

    def __init__(self, *, provider_factory=None, database=None, settings=None):
        super().__init__()
        self.setObjectName("chat")
        self.setWindowTitle("PetLink — Chat")
        self.resize(560, 740)
        self.setMinimumSize(360, 560)
        self.setStyleSheet(stylesheet())
        self.provider_factory = provider_factory
        self.settings = settings if settings is not None else QSettings("PetLink", "Companion")
        geometry = self.settings.value("chat/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.credentials = CredentialStore()
        try:
            self.connection = load_connection(self.settings, self.credentials)
        except OSError:
            self.connection = dict(provider="local", address=PROVIDERS["local"][1], model="", consent=False, key="")
        self.database = database
        self.conversation_id = database.conversation() if database is not None else None
        self._pending_save = None
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.timeout.connect(self._save_draft)
        self.history = []
        self._job = 0
        self._busy = False
        self.voice_active = False
        self._cancel = Event()
        self._reply = ""
        self._request_kind = "chat"
        self._task_context = {}
        self._task_input = None
        self._reply_label = None
        self._retry_text = None
        self._connection_health = None
        self._signals = RequestSignals(self)
        self._signals.chunk.connect(self._on_chunk)
        self._signals.finished.connect(self._on_finished)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self.stop)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        self.title = QLabel("Chat with Ishu")
        self.title.setObjectName("title")
        self.avatar = QLabel()
        from .expressions import notification_icon
        self.avatar.setPixmap(notification_icon("anime_azure").pixmap(36,36))
        header.addWidget(self.avatar)
        header.addWidget(self.title, 1)
        hide = QPushButton("Hide")
        hide.clicked.connect(self.close)
        header.addWidget(hide)
        layout.addLayout(header)
        note = QLabel("Your local productivity assistant")
        note.setObjectName("muted")
        layout.addWidget(note)

        self.address = QLineEdit(self.connection["address"], self)
        self.model = QLineEdit(self.connection["model"], self)
        self.address.hide()
        self.model.hide()
        for field in (self.address, self.model):
            field.editingFinished.connect(self._save_model_details)
        toolbar = QHBoxLayout()
        self.connection_note = QLabel()
        self.connection_note.setObjectName("muted")
        self.connection_note.setWordWrap(True)
        toolbar.addWidget(self.connection_note, 1)
        self.settings_button = QPushButton("Settings")
        self.settings_button.setAccessibleName("AI Model Settings")
        self.settings_button.clicked.connect(self.model_settings)
        toolbar.addWidget(self.settings_button)
        self.tasks_button = QPushButton("Pending Tasks")
        self.tasks_button.setEnabled(database is not None)
        self.tasks_button.clicked.connect(self.tasks_requested.emit)
        toolbar.addWidget(self.tasks_button)
        layout.addLayout(toolbar)
        self.test_button = QPushButton("Test connection", self)
        self.test_button.hide()
        self.test_button.clicked.connect(self.test_connection)
        self._connection_label()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.messages = QWidget()
        self.messages.setObjectName("messages")
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(0, 0, 8, 0)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.messages)
        layout.addWidget(self.scroll, 1)
        self.welcome = self._bubble("PetLink", "What would you like to work on?\n\nDiscuss a plan with your local model, or open Tasks & Pending to review and confirm a task.")
        from .chat_widgets import Feedback
        self.feedback = Feedback("Chat and drafts are saved on this laptop." if database else "No model connected · session preview")
        self.status = self.feedback.full
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(38)
        self.status.setAccessibleName("Chat status")
        layout.addWidget(self.feedback)
        self.composer = Composer()
        self.composer.setPlaceholderText("Plan a focused work session…")
        self.composer.setAccessibleName("Message")
        self.composer.setFixedHeight(88)
        self.composer.textChanged.connect(self._typing)
        self.composer.send_requested.connect(self.send)
        layout.addWidget(self.composer)
        self.draft_button = QPushButton("Draft task from message")
        self.draft_button.setToolTip("Interpret this message as one new task, then review the fields. Nothing becomes a task until you confirm it.")
        self.draft_button.setEnabled(False)
        self.draft_button.clicked.connect(self.draft_task)
        self.new_task_button = QPushButton("Start new")
        self.new_task_button.setToolTip("Start a separate task request. Saved pending drafts are kept.")
        self.new_task_button.clicked.connect(self.reset_task_context)
        draft_actions = QHBoxLayout()
        draft_actions.addWidget(self.draft_button, 1)
        draft_actions.addWidget(self.new_task_button)
        layout.addLayout(draft_actions)
        self.task_context_note = QLabel()
        self.task_context_note.setTextFormat(Qt.TextFormat.PlainText)
        self.task_context_note.setWordWrap(True)
        self.task_context_note.setAccessibleName("Current task follow-up")
        layout.addWidget(self.task_context_note)
        self._update_task_context_label()
        actions = QHBoxLayout()
        hint = QLabel("Enter to send · Shift+Enter for a new line")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        actions.addWidget(hint, 1)
        self.mic_button = QPushButton("Mic")
        self.mic_button.setAccessibleName("Start or stop voice input")
        self.mic_button.clicked.connect(self.voice_requested.emit)
        actions.addWidget(self.mic_button)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self.retry_last)
        actions.addWidget(self.retry_button)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primary")
        self.send_button.setMinimumWidth(72)
        self.send_button.clicked.connect(self._send_or_stop)
        self.send_button.setEnabled(False)
        actions.addWidget(self.send_button)
        layout.addLayout(actions)
        for button in self.findChildren(QPushButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        if self.database is not None:
            self._restore()

    def _restore(self):
        records = self.database.messages(self.conversation_id)
        if records:
            self.welcome.parentWidget().hide()
            self.welcome = None
        for record in records:
            content = record["content"]
            if record["status"] == "incomplete":
                content += "\n[Response incomplete]"
            self._bubble("You" if record["role"] == "user" else "PetLink", content)
            if record["status"] == "complete":
                self.history.append(ChatMessage(record["role"], record["content"]))
        self.history = self.history[-16:]
        if self.history and self.history[-1].role == "user":
            self._retry_text = self.history[-1].content
            self.retry_button.setVisible(True)
        self.composer.setPlainText(self.database.chat_draft(self.conversation_id))
        from .task_interpretation import validate_context
        try:
            self._task_context = validate_context(self.database.task_context(self.conversation_id))
            self._update_task_context_label()
        except (ValueError, TypeError, RecursionError, SQLAlchemyError):
            self.status.setText("Could not load task follow-up context. Enter a complete new request; saved drafts are unchanged.")
        self._scroll_bottom()

    def _save_draft(self):
        if self.database is not None:
            try:
                self.database.save_chat_draft(self.conversation_id, self.composer.toPlainText())
            except SQLAlchemyError:
                self.status.setText("Could not save the typed draft. Keep this window open and try again.")

    def retry_last(self):
        if self._pending_save:
            content, status = self._pending_save
            if self._save_reply(content, status):
                self.status.setText("Reply saved locally.")
        else:
            self.send(retry=True)

    def _save_reply(self, content, status):
        if self.database is None:
            return True
        try:
            self.database.add_message(self.conversation_id, "assistant", content, status)
            self._pending_save = None
            self.retry_button.setText("Retry")
            self.retry_button.setVisible(False)
            return True
        except SQLAlchemyError:
            self._pending_save = (content, status)
            self.retry_button.setText("Retry save")
            self.retry_button.setVisible(True)
            return False

    def set_pet_name(self, name):
        self.title.setText("Chat with " + name)
        from .expressions import notification_icon
        kind = {"Ishu":"anime_azure","Coral":"anime_coral","Lola":"animal_cat"}[name]
        self.avatar.setPixmap(notification_icon(kind).pixmap(36,36))

    def _bubble(self, speaker, text):
        from .chat_widgets import MessageBubble
        frame = MessageBubble(speaker, text)
        label = frame.text
        self.message_layout.insertWidget(self.message_layout.count() - 1, frame,0,
            Qt.AlignmentFlag.AlignRight if speaker == "You" else Qt.AlignmentFlag.AlignLeft)
        # Bound transcript widgets as well as the context sent to the model.
        if self.message_layout.count() > 61:
            old = self.message_layout.takeAt(0)
            old.widget().deleteLater()
        return label

    def _typing(self):
        self._draft_timer.start(400)
        self._update_draft_button()
        if not self._busy:
            self.send_button.setEnabled(not self.voice_active and bool(self.composer.toPlainText().strip()))
            if not self.voice_active:
                self.activity.emit("typing")

    def _set_busy(self, busy):
        self._busy = busy
        self.mic_button.setEnabled(not busy and not self.voice_active)
        self._update_draft_button()
        self.address.setEnabled(not busy)
        self.model.setEnabled(not busy)
        self.settings_button.setEnabled(not busy and not self.voice_active)
        self.test_button.setEnabled(not busy)
        self.retry_button.setEnabled(not busy)
        self.send_button.setText("Stop" if busy else "Send")
        self.send_button.setEnabled(busy or bool(self.composer.toPlainText().strip()))

    def _send_or_stop(self):
        self.stop() if self._busy else self.send()

    def _provider(self):
        try:
            values = self._model_values()
            config = connection_config(values)
            if not self._save_model_details():
                return None
            if self.provider_factory is not None:
                return self.provider_factory(config)
            return create_provider("ollama" if values["provider"] == "local" else values["provider"], config)
        except ValueError as error:
            self.status.setText(str(error))
            self.activity.emit("confused")
            self.model.setFocus() if not self.model.text().strip() else self.address.setFocus()
            return None

    def _model_values(self):
        values = {**self.connection, "address": self.address.text().strip(), "model": self.model.text().strip()}
        if values["provider"] == "local":
            self.settings.sync()
            values["skip_thinking"] = self.settings.value("models/local/skip_thinking",
                values.get("skip_thinking", False), type=bool)
        return values

    def _save_model_details(self):
        values = self._model_values()
        try:
            save_connection_details(self.settings, values)
        except ValueError:
            return False  # An incomplete edit must not erase the last valid connection.
        except OSError:
            self.status.setText("Could not remember model details. Your fields are still here; try again.")
            return False
        thinking_changed = self.connection.get("skip_thinking") != values.get("skip_thinking")
        self.connection = values
        if thinking_changed:
            self._connection_label()
        return True

    def _connection_label(self):
        provider = self.connection["provider"]
        cloud = provider != "local"
        state = "Connected" if self._connection_health else "Configured" if self.connection.get("model") else "Choose a model"
        model = self.connection.get("model", "")
        self.connection_note.setText(f"{state} · {model}\n" + ("Cloud chat enabled · messages leave this laptop" if cloud else
            ("Local · thinking skipped" if self.connection.get("skip_thinking") else "Local · model default thinking")))
        self.connection_note.setStyleSheet(f"color:{COLORS['success']};" if self._connection_health else "")
        self.address.setReadOnly(cloud)
        self.address.setAccessibleName("Model server address")

    def model_settings(self):
        if self._busy or self.voice_active:
            return
        current = self._model_values()
        dialog = ModelSettings(self.settings, current, self, store=self.credentials)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self._connection_health = None
            self.connection = dialog.connection
            self.address.setText(self.connection["address"])
            self.model.setText(self.connection["model"])
            self._connection_label()
            self.status.setText("Model settings saved. Test connection before sending.")

    def _start(self, provider, history=None, *, kind="chat"):
        self._job += 1
        self._request_kind = kind
        self._cancel = Event()
        self._set_busy(True)
        self._deadline.start(int(request_budget(provider) * 1000))
        Thread(target=run_request, args=(self._signals, self._job, self._cancel, provider, history), daemon=True).start()

    def _update_draft_button(self):
        self.draft_button.setEnabled(self.database is not None and not self._busy
            and not self.voice_active and not self._pending_save
            and bool(self.composer.toPlainText().strip()))
        self.new_task_button.setEnabled(bool(self._task_context) and not self._busy and not self.voice_active)

    def _update_task_context_label(self):
        context = self._task_context
        self.draft_button.setText("Continue task draft" if context else "Draft task from message")
        detail = context.get("question") or (context.get("action") or {}).get("values", {}).get("title", "")
        self.task_context_note.setText("Task follow-up: " + detail[:100] + ("…" if len(detail) > 100 else "") if context else "")
        self.task_context_note.setToolTip(detail)
        self.task_context_note.setVisible(bool(context))
        self._update_draft_button()

    def reset_task_context(self):
        if self.database is None or self._busy or self.voice_active:
            return
        try:
            self.database.save_task_context(self.conversation_id, {})
        except SQLAlchemyError:
            self.status.setText("Could not reset task follow-up. Your request is still here; retry.")
            return
        self._task_context = {}
        self._update_task_context_label()
        self.status.setText("Ready for a separate task request. Saved pending drafts are unchanged.")

    def _current_task_pending(self):
        reference = self._task_context.get("pending")
        if reference is None:
            return None
        pending = self.database.pending_by_id(reference["id"])
        if not pending or pending["status"] != "pending" or pending["revision"] != reference["revision"]:
            raise ValueError("This pending draft was changed, confirmed or discarded. Start new, or edit it in Tasks & Pending.")
        return pending

    def attach_task_pending(self, reference):
        """Track the exact fields and revision the user reviewed, including manual edits."""
        try:
            pending = self.database.pending_by_id(reference["id"])
            if not pending or pending["status"] != "pending" or pending["revision"] != reference["revision"]:
                raise ValueError("The pending draft changed. Open Tasks & Pending to review it.")
            from .task_interpretation import validate_context
            actions = json.loads(pending["payload"])
            if len(actions) != 1:
                raise ValueError("Only one new task can have a follow-up here.")
            context = validate_context({**self._task_context, "action": actions[0], "pending": reference, "question": None})
            self.database.save_task_context(self.conversation_id, context)
        except (ValueError, TypeError, SQLAlchemyError):
            self.status.setText("The pending draft is saved, but follow-up context could not be updated. Use Tasks & Pending to review it.")
            return
        self._task_context = context
        self._update_task_context_label()

    def draft_task(self, *, request=None):
        if self.database is None or self._busy or self.voice_active or self._pending_save:
            return
        text = (self.composer.toPlainText() if request is None else request).strip()
        if not text or len(text) > 6000:
            self.status.setText("Describe one new task in under 6,000 characters.")
            return
        try:
            self._current_task_pending()
        except (ValueError, SQLAlchemyError) as exc:
            self.status.setText(str(exc) if isinstance(exc, ValueError) else "Could not check the pending draft. Retry before continuing.")
            return
        from .task_interpretation import draft_messages, direct_reminder
        from .scheduling import DEFAULT_SCHEDULE
        context = deepcopy(self._task_context) or dict(date=datetime.now(ZoneInfo(DEFAULT_SCHEDULE["timezone"])).date().isoformat(),
            messages=[], action=None, pending=None, question=None)
        if len(context["messages"]) >= 12 or sum(len(m["content"]) for m in context["messages"]) + len(text) + 500 > 24000:
            self.status.setText("This task follow-up is full. Review the current draft or start a new task request.")
            return
        self._task_input = (text, context)
        self._reply = ""
        self._reply_label = self._bubble("PetLink", "Preparing a task draft for review…")
        direct = direct_reminder(text, context=context)
        if direct is not None:
            self._reply = json.dumps({"question": direct} if isinstance(direct, str)
                                     else {"task": {k: v for k, v in direct["values"].items() if k != "status"}})
            self._finish_task("complete", "")
            return
        provider = self._provider()
        if provider is None:
            self._reply_label.setText("Model settings need attention. Your task request is still here.")
            return
        self.status.setText("Drafting one new task · your original message stays editable.")
        self.activity.emit("thinking")
        self._start(provider, draft_messages(text, context=context), kind="task")

    def test_connection(self):
        if self._busy or self.voice_active:
            return
        provider = self._provider()
        if provider:
            self._reply_label = None
            self.status.setText("Checking model service…")
            self._start(provider)

    def send(self, *, retry=False):
        if self._busy or self.voice_active:
            return
        if self._pending_save:
            self.status.setText("Use Retry save to save the previous reply before sending another message.")
            return
        text = self._retry_text if retry else self.composer.toPlainText().strip()
        if not text:
            return
        if len(text) > 6000:
            self.status.setText("Please keep each message under 6,000 characters.")
            return
        from .schedule_queries import task_query, overview_reply
        kind = task_query(text)
        if kind is not None:
            try:
                reply = overview_reply(self.database, kind)
            except SQLAlchemyError:
                self.status.setText("Could not read your saved tasks. Your question is still here; try again or open Tasks & Pending.")
                return
            self._local_reply(text, reply, "Read from this laptop's saved records. No model call needed.", retry=retry)
            return
        from .task_interpretation import direct_reminder, creation_request
        if creation_request(text) or direct_reminder(text) is not None:
            if self.database is not None and not self._task_context:
                self.draft_task(request=text)
            else:
                self._reminder_guidance(text, retry=retry)
            return
        provider = self._provider()
        if provider is None:
            return
        if self.database is not None and not retry:
            try:
                self.database.add_message(self.conversation_id, "user", text)
            except SQLAlchemyError:
                self.status.setText("Could not save your message. Nothing was sent; your text is still here.")
                return
        if self.welcome is not None:
            self.welcome.parentWidget().hide()
            self.welcome = None
        self.retry_button.setVisible(False)
        self._retry_text = text
        self._reply = ""
        if not retry:
            self.history.append(ChatMessage("user", text))
            self._bubble("You", text)
            self.composer.clear()
        self._trim_history()
        self._reply_label = self._bubble("PetLink", "Thinking…")
        self.status.setText("Thinking · your selected model is preparing a reply")
        self.activity.emit("thinking")
        self._start(provider, [SYSTEM, *self.history])
        self.composer.setFocus()
        self._scroll_bottom()

    def _trim_history(self):
        local = self.connection["provider"] == "local"
        self.history = self.history[-(8 if local else 16):]
        while sum(len(m.content) for m in self.history) > (8000 if local else 24000):
            self.history.pop(0)

    def _reminder_guidance(self, text, *, retry=False):
        """Normal Send offers the explicit task flow; it never schedules anything."""
        detail = ("Choose Start new, then Draft task from message" if self._task_context
                  else "Choose Draft task from message")
        reply = detail + " to review this reminder. Check its date and time, review the fields, and confirm it in Tasks & Pending. No reminder has been saved yet."
        self._local_reply(text, reply, "Your request is ready to draft.", keep_text=True, retry=retry)

    def _local_reply(self, text, reply, status, *, keep_text=False, retry=False):
        if self.database is not None and not retry:
            try:
                self.database.add_message(self.conversation_id, "user", text)
            except SQLAlchemyError:
                self.status.setText("Could not save your message. Your request is still here; retry.")
                return
        if self.welcome is not None:
            self.welcome.parentWidget().hide()
            self.welcome = None
        if not retry:
            self._bubble("You", text)
            self.history.append(ChatMessage("user", text))
            if not keep_text:
                self.composer.clear()
        self._reply_label = self._bubble("PetLink", reply)
        self.history.append(ChatMessage("assistant", reply))
        self._trim_history()
        saved = self._save_reply(reply, "complete")
        self._retry_text = None
        self.status.setText(status if saved else "Could not save the reply. Use Retry save.")
        self._save_draft()
        self._update_draft_button()
        self.activity.emit("finished")
        self._scroll_bottom()

    def stop(self):
        if self._busy:
            self._cancel.set()
            self.status.setText("Stopping… waiting for the model service to release the request.")
            self.send_button.setEnabled(False)

    def _scroll_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _on_chunk(self, job, text):
        if job != self._job or self._cancel.is_set():
            return
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.maximum() - bar.value() < 40
        self._reply += text
        if self._request_kind == "task":
            return
        self._reply_label.setText(self._reply)
        if at_bottom:
            self._scroll_bottom()

    def _on_finished(self, job, outcome, detail):
        if job != self._job:
            return
        self._deadline.stop()
        self._connection_health = outcome in ("complete", "healthy")
        self._connection_label()
        if self._cancel.is_set():
            outcome, detail = "cancelled", "Response stopped."
        if self._request_kind == "task":
            self._finish_task(outcome, detail)
            return
        persisted = True
        if outcome == "complete" and self._reply.strip():
            self.history.append(ChatMessage("assistant", self._reply))
            persisted = self._save_reply(self._reply, "complete")
            self._retry_text = None
        elif outcome in ("error", "cancelled") or (outcome == "complete" and not self._reply.strip()):
            if self._reply_label:
                self._reply_label.setText((self._reply + "\n\n" if self._reply else "") + "[Response incomplete]")
                if self._reply:
                    persisted = self._save_reply(self._reply, "incomplete")
            if outcome == "complete":
                detail = "The model returned no answer text. For Ollama thinking models, enable Skip extended thinking in Model settings, then retry."
            self.retry_button.setVisible(self._retry_text is not None)
        self.status.setText(detail if persisted else "Reply is visible but could not be saved. Use Retry save.")
        self._set_busy(False)
        self.activity.emit("confused" if outcome == "error" else "finished")

    def _finish_task(self, outcome, detail):
        self._request_kind = "chat"
        self._set_busy(False)
        if outcome != "complete":
            self._reply_label.setText("Task draft stopped. No task or pending action was saved.")
            self.status.setText(detail)
            self.activity.emit("confused" if outcome == "error" else "finished")
            return
        from .task_interpretation import parse_draft
        try:
            text, context = self._task_input
            result = parse_draft(self._reply, current=context.get("action"))
        except (ValueError, TypeError, RecursionError):
            self._reply_label.setText("Could not interpret a valid task draft. No task was saved.")
            self.status.setText("Edit your request and try Draft task again, or use Tasks & Pending → New task.")
            self.activity.emit("confused")
            return
        try:
            self._current_task_pending()
            context["messages"] += [dict(role="user", content=text),
                dict(role="assistant", content=result if isinstance(result, str) else "Draft fields prepared for review.")]
            context["question"] = result if isinstance(result, str) else None
            if not isinstance(result, str):
                context["action"] = result
            from .task_interpretation import validate_context
            validate_context(context)
            self.database.save_task_context(self.conversation_id, context)
        except (ValueError, SQLAlchemyError) as exc:
            self._reply_label.setText("Task follow-up was not updated. Your message is still here.")
            self.status.setText(str(exc) if isinstance(exc, ValueError) else "Could not save task follow-up context. Retry; no task was changed.")
            self.activity.emit("confused")
            return
        self._task_context = context
        self._update_task_context_label()
        self._retry_text = None
        self.retry_button.setVisible(False)
        self.activity.emit("finished")
        if isinstance(result, str):
            self._reply_label.setText(result)
            self.status.setText("Replace the message with your answer, then choose Continue task draft. No task is active yet.")
        else:
            self._reply_label.setText("Task draft ready. Review the fields before saving a pending draft, then confirm it in Tasks & Pending.")
            self.status.setText("Your message is unchanged. No active task has been created.")
            self.task_draft_ready.emit(result)

    def closeEvent(self, event):
        self.settings.setValue("chat/geometry", self.saveGeometry())
        self._save_model_details()
        self._save_draft()
        self.hide()
        event.ignore()

    def shutdown(self):
        self.settings.setValue("chat/geometry", self.saveGeometry())
        self._cancel.set()
        self._deadline.stop()
        self._draft_timer.stop()
        self._save_model_details()
        self._save_draft()


class ReminderSignals(QObject):
    ready = Signal(int, int, str, bool)


class CompanionController(QObject):
    """Keep the pet alive when chat is hidden; own the app's chat lifecycle."""
    def __init__(self, pet, *, chat=None, database=None):
        super().__init__(pet)
        self.pet = pet
        self.chat = chat if chat is not None else ChatWindow(database=database, settings=pet.settings)
        self.tasks = None
        self.database = database
        self.notifications = None
        self._notification_running = False
        self._notification_recheck = False
        self._notification_closed = False
        self._notification_worker = None
        self._reminder_signals = ReminderSignals(self)
        self._reminder_signals.ready.connect(self._notifications_ready)
        pet.controls.bell.setEnabled(database is not None)
        from .voice_input import VoiceInput
        self.voice = VoiceInput(pet.settings, self)
        self.voice.busy.connect(self._voice_busy)
        self.voice.status.connect(pet.controls.message)
        self.voice.text.connect(self._voice_text)
        pet.controls.voice_requested.connect(self.voice_command)
        pet.voice_setup_requested.connect(self.voice_setup)
        pet.controls.submit.connect(self.quick_send)
        pet.controls.draft_changed.connect(self._quick_draft)
        self.chat.composer.textChanged.connect(self._sync_quick_draft)
        self._sync_quick_draft()
        if database is not None:
            from .task_window import TaskWindow
            from .notification_window import NotificationWindow
            self.tasks = TaskWindow(database)
            self.tasks.confirmed.connect(lambda: pet.react("task_confirmed") if not self.chat._busy and not self.voice.active else None)
            self.tasks.confirmed.connect(self.check_notifications)
            self.chat.tasks_requested.connect(self.show_tasks)
            self.chat.task_draft_ready.connect(self.review_model_draft)
            self.notifications = NotificationWindow(database)
            self.notifications.changed.connect(self.check_notifications)
            self.notifications.tasks_requested.connect(self.show_tasks)
            pet.controls.notification_requested.connect(self.show_notifications)
            self.notification_timer = QTimer(self)
            self.notification_timer.timeout.connect(self.check_notifications)
            self.notification_timer.start(60000)
            QApplication.instance().aboutToQuit.connect(self.stop_notifications)
            QTimer.singleShot(0, self.check_notifications)
        self._update_name(pet.pet_kind)
        pet.clicked.connect(pet.controls.toggle_editor)
        pet.double_clicked.connect(self.show_chat)
        pet.chat_requested.connect(self.show_chat)
        pet.pet_kind_changed.connect(self._update_name)
        self.chat.activity.connect(pet.react)
        self.chat.voice_requested.connect(self.voice_command)
        from .companion_ui import install
        install(self)
        QApplication.instance().aboutToQuit.connect(self.chat.shutdown)
        QApplication.instance().aboutToQuit.connect(self.voice.shutdown)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray_menu = QMenu(pet)
            self.pet_action = self.tray_menu.addAction("Hide pet", self.toggle_pet)
            self.tray_menu.addAction("Open chat", self.show_chat)
            task_action = self.tray_menu.addAction("Tasks & Pending", self.show_tasks)
            task_action.setEnabled(self.tasks is not None)
            self.notification_action = self.tray_menu.addAction("Notifications", self.show_notifications)
            self.notification_action.setEnabled(self.notifications is not None)
            self.tray_menu.addAction("Voice setup", self.voice_setup)
            self.tray_menu.addSeparator()
            self.tray_menu.addAction("Exit PetLink", pet.close)
            self.tray_menu.aboutToShow.connect(self._sync_tray)
            self.tray.setContextMenu(self.tray_menu)
            self.tray.activated.connect(self._tray_activated)
            pet.pet_kind_changed.connect(self._tray_icon)
            pet.hide_requested.connect(self.toggle_pet)
            pet.tray_available = True
            self._tray_icon(pet.pet_kind)
            self._sync_tray()
            self.tray.show()
            QApplication.instance().aboutToQuit.connect(self.tray.hide)

    def _tray_icon(self, kind):
        from .character_art import paint_character
        from PySide6.QtCore import QPointF
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(64 / 240, 64 / 260)
        paint_character(painter, kind.value, "idle", 0, QPointF(), 0, 0,
                        False, 100, 100, reduced=True)
        painter.end()
        self.tray.setIcon(QIcon(pixmap))
        self._sync_tray()

    def _sync_tray(self):
        if self.tray is None:
            return
        name = {"anime_azure": "Ishu", "anime_coral": "Coral", "animal_cat": "Lola"}[self.pet.pet_kind.value]
        unread = self.pet._notification_count
        self.tray.setToolTip(f"PetLink · {name} · {unread} unread task notification(s)")
        self.notification_action.setText(f"Notifications ({unread} unread)")
        self.pet_action.setText("Hide pet" if self.pet.isVisible() else "Show pet")
        self.pet_action.setEnabled(not self.voice.active)

    def toggle_pet(self):
        if self.tray is None:
            return
        if self.voice.active:
            self.pet.controls.message("Finish voice input before hiding the pet.")
            return
        if self.pet.isVisible():
            self.pet._click_timer.stop()
            self.pet.hide()
        else:
            self.pet.show()
            self.pet.raise_()
        self._sync_tray()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.pet.show()
            self.pet.raise_()
            self.show_chat()
            self._sync_tray()

    def _quick_draft(self, text):
        if text != self.chat.composer.toPlainText():
            self.chat.composer.setPlainText(text)

    def _sync_quick_draft(self):
        text = self.chat.composer.toPlainText()
        if text != self.pet.controls.input.text():
            self.pet.controls.input.blockSignals(True)
            self.pet.controls.input.setText(text)
            self.pet.controls.input.blockSignals(False)

    def quick_send(self, text):
        if self.chat._busy or self.voice.active:
            self.pet.controls.message("Wait for the current response or voice input to finish.")
            return
        self._quick_draft(text)
        self.show_chat()
        self.chat.send()

    def _voice_text(self, text):
        existing = self.chat.composer.toPlainText().strip()
        combined = (existing + " " + text).strip() if existing else text
        if len(combined) > 6000:
            self.chat.composer.setPlainText(combined)
            self.show_chat()
            self.pet.controls.message("Transcript is long. Review and shorten it in chat before sending.")
        else:
            self.pet.controls.show_text(combined)
            self.pet.controls.message("Review voice text before sending.")

    def voice_command(self):
        if self.chat._busy:
            self.pet.controls.message("Finish or stop the model reply before using voice.")
            return
        self.voice.toggle(self.pet)

    def voice_setup(self):
        if self.voice.active:
            self.pet.controls.message("Finish voice input before changing its setup.")
        else:
            self.voice.configure(self.pet)

    def _voice_busy(self, busy):
        self.chat.voice_active = busy
        self.chat.mic_button.setText("Stop mic" if self.voice.recording else ("Transcribing…" if busy else "Mic"))
        self.chat.mic_button.setEnabled(not self.chat._busy and (not busy or self.voice.recording))
        self.chat._update_draft_button()
        self.chat.test_button.setEnabled(not busy and not self.chat._busy)
        self.chat.settings_button.setEnabled(not busy and not self.chat._busy)
        self.chat.send_button.setEnabled(not busy and (self.chat._busy or bool(self.chat.composer.toPlainText().strip())))
        self.pet.controls.mic.setEnabled(not busy or self.voice.recording)
        self.pet.controls.mic.setToolTip("Stop recording" if self.voice.recording else ("Transcribing locally…" if busy else "Start voice input"))
        self.pet.controls.mic.setStyleSheet("background:#A94764;" if self.voice.recording else "")
        self._sync_tray()
        if not self.chat._busy:
            self.pet.react(("microphone_on" if self.voice.recording else "thinking") if busy else "finished")

    def check_notifications(self):
        if self.database is None or self._notification_closed:
            return
        if self._notification_running:
            self._notification_recheck = True
            return
        self._notification_running = True
        database, signals = self.database, self._reminder_signals
        def work():
            try:
                added = database.check_due_notifications() + database.poll_reminders()
                unread = database.unread_notifications()
                latest = database.notifications(limit=1) if added else []
                result = (added, unread, latest[0]["statement"] if latest else "", True)
            except (SQLAlchemyError, ValueError):
                result = (0, 0, "", False)
            try:
                signals.ready.emit(*result)
            except RuntimeError:
                pass
        self._notification_worker = Thread(target=work, daemon=True)
        self._notification_worker.start()

    def _notifications_ready(self, added, unread, statement, success):
        self._notification_running = False
        if self._notification_closed:
            return
        if self._notification_recheck:
            self._notification_recheck = False
            QTimer.singleShot(0, self.check_notifications)
        if not success:
            self.pet.controls.message("Task notifications could not be checked. Open Tasks to retry.")
            return
        self.pet.set_notification_count(unread)
        self._sync_tray()
        if self.notifications is not None and self.notifications.isVisible():
            self.notifications.refresh()
        if added:
            self.pet.controls.message(statement.split(" — ")[0][:30] + "\nTask alert · tap the bell to read.")
            if not self.chat._busy and not self.voice.active:
                self.pet.react("reminder")

    def stop_notifications(self):
        self._notification_closed = True
        if hasattr(self, "notification_timer"):
            self.notification_timer.stop()
        if self._notification_worker and self._notification_worker.is_alive():
            self._notification_worker.join(timeout=3)

    def show_notifications(self):
        if self.notifications is not None:
            self.notifications.refresh()
            self.notifications.show()
            self.notifications.raise_()
            self.notifications.activateWindow()

    def show_tasks(self):
        if self.tasks is not None:
            self.tasks.refresh()
            self.tasks.show()
            self.tasks.raise_()
            self.tasks.activateWindow()

    def review_model_draft(self, action):
        from .companion_ui import show_draft
        show_draft(self,action)

    def _edit_model_draft(self, action):
        if self.tasks is not None:
            try:
                pending = self.chat._current_task_pending()
            except (ValueError, SQLAlchemyError):
                self.chat.status.setText("The pending draft changed. Review it in Tasks & Pending before continuing.")
                return
            self.show_tasks()
            reference = self.tasks._open_editor(action, pending)
            if reference or pending:
                self.chat.attach_task_pending(reference or dict(id=pending["id"], revision=pending["revision"]))

    def _update_name(self, kind):
        names = {"anime_azure": "Ishu", "anime_coral": "Coral", "animal_cat": "Lola"}
        self.chat.set_pet_name(names[kind.value])

    def toggle_chat(self):
        self.chat.hide() if self.chat.isVisible() else self.show_chat()

    def show_chat(self):
        if not self.chat.isVisible():
            area = self.pet.screen().availableGeometry()
            x = self.pet.x() + self.pet.width()
            if x + self.chat.width() > area.right():
                x = self.pet.x() - self.chat.width()
            self.chat.move(max(area.left(), min(x, area.right() - self.chat.width())),
                           max(area.top(), min(self.pet.y(), area.bottom() - self.chat.height())))
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()
        self.chat.composer.setFocus()
        if not self.chat._busy and not self.voice.active:
            self.pet.react("chat_opened")
