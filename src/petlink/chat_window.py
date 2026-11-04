"""Local chat UI, bounded history, and background model requests."""
from __future__ import annotations

from ipaddress import ip_address
from threading import Event, Thread
import time
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy.exc import SQLAlchemyError

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .models import ChatMessage, ModelConfig, OpenAICompatibleProvider
from .ui_theme import stylesheet

SYSTEM = ChatMessage("system", "You are PetLink, a work and productivity assistant. "
    "Discuss tasks, goals, study and planning. Do not claim to have created, edited, "
    "scheduled or saved anything: task execution is not implemented. Offer drafts only. "
    "Ask a focused question when the user's intent is ambiguous.")


def local_config(address, model):
    """This milestone permits loopback servers only; hosted setup comes later."""
    parsed = urlsplit(address.strip())
    try:
        local = parsed.hostname == "localhost" or ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = False
    if (not local or parsed.scheme not in ("http", "https") or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") not in ("", "/v1")):
        raise ValueError("Use a local address such as http://127.0.0.1:11434 or http://localhost:1234.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid server port.") from exc
    if not model.strip():
        raise ValueError("Enter the name of a model installed in your local server.")
    return ModelConfig(urlunsplit((parsed.scheme, parsed.netloc, "", "", "")),
                       model.strip(), timeout_seconds=25, max_tokens=1024)


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


def run_request(signals, job, cancel, provider, history=None):
    """Daemon worker; Qt's queued signals are the only route back to widgets."""
    try:
        if history is None:
            outcome = "healthy" if provider.health_check() else "error"
            detail = "Local server is reachable." if outcome == "healthy" else "Cannot reach the server. Start it, then test again."
        else:
            start, flush = time.monotonic(), time.monotonic()
            pending, length = "", 0
            for chunk in provider.stream(history):
                if cancel.is_set():
                    break
                if time.monotonic() - start > 90:
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
    except Exception:
        try:
            signals.finished.emit(job, "cancelled" if cancel.is_set() else "error",
                "Response stopped." if cancel.is_set() else
                "The model did not finish. Check the server and model name, then retry.")
        except RuntimeError:
            pass


class ChatWindow(QWidget):
    activity = Signal(str)
    tasks_requested = Signal()

    def __init__(self, *, provider_factory=OpenAICompatibleProvider, database=None):
        super().__init__()
        self.setObjectName("chat")
        self.setWindowTitle("PetLink — Chat")
        self.resize(460, 700)
        self.setMinimumSize(360, 560)
        self.setStyleSheet(stylesheet())
        self.provider_factory = provider_factory
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
        self._reply_label = None
        self._retry_text = None
        self._signals = RequestSignals(self)
        self._signals.chunk.connect(self._on_chunk)
        self._signals.finished.connect(self._on_finished)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self.stop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        self.title = QLabel("Chat with Ishu")
        self.title.setObjectName("title")
        header.addWidget(self.title, 1)
        hide = QPushButton("Hide")
        hide.clicked.connect(self.close)
        header.addWidget(hide)
        layout.addLayout(header)
        note = QLabel("A little company for your workday.")
        note.setObjectName("muted")
        layout.addWidget(note)

        connection = QGroupBox("Local model")
        form = QFormLayout(connection)
        self.address = QLineEdit("http://127.0.0.1:11434")
        self.address.setAccessibleName("Local server address")
        self.model = QLineEdit()
        self.model.setPlaceholderText("Your installed model name")
        self.model.setAccessibleName("Model name")
        form.addRow("Server", self.address)
        form.addRow("Model", self.model)
        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(self.test_connection)
        connection_actions = QHBoxLayout()
        connection_actions.addWidget(self.test_button)
        self.tasks_button = QPushButton("Tasks & Pending")
        self.tasks_button.setEnabled(database is not None)
        self.tasks_button.clicked.connect(self.tasks_requested.emit)
        connection_actions.addWidget(self.tasks_button)
        form.addRow(connection_actions)
        layout.addWidget(connection)
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
        self.status = QLabel("Chat and drafts are saved on this laptop." if database else "No model connected · session preview")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(38)
        self.status.setAccessibleName("Chat status")
        layout.addWidget(self.status)
        self.composer = Composer()
        self.composer.setPlaceholderText("Plan a focused work session…")
        self.composer.setAccessibleName("Message")
        self.composer.setFixedHeight(88)
        self.composer.textChanged.connect(self._typing)
        self.composer.send_requested.connect(self.send)
        layout.addWidget(self.composer)
        actions = QHBoxLayout()
        hint = QLabel("Enter to send · Shift+Enter for a new line")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        actions.addWidget(hint, 1)
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

    def _bubble(self, speaker, text):
        frame = QFrame()
        frame.setObjectName("bubble")
        content = QVBoxLayout(frame)
        content.setContentsMargins(14, 12, 14, 12)
        name = QLabel(speaker)
        name.setObjectName("speaker")
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        label.setAccessibleName(speaker + " message")
        content.addWidget(name)
        content.addWidget(label)
        self.message_layout.insertWidget(self.message_layout.count() - 1, frame)
        # Bound transcript widgets as well as the context sent to the model.
        if self.message_layout.count() > 61:
            old = self.message_layout.takeAt(0)
            old.widget().deleteLater()
        return label

    def _typing(self):
        self._draft_timer.start(400)
        if not self._busy:
            self.send_button.setEnabled(not self.voice_active and bool(self.composer.toPlainText().strip()))
            self.activity.emit("typing")

    def _set_busy(self, busy):
        self._busy = busy
        self.address.setEnabled(not busy)
        self.model.setEnabled(not busy)
        self.test_button.setEnabled(not busy)
        self.retry_button.setEnabled(not busy)
        self.send_button.setText("Stop" if busy else "Send")
        self.send_button.setEnabled(busy or bool(self.composer.toPlainText().strip()))

    def _send_or_stop(self):
        self.stop() if self._busy else self.send()

    def _provider(self):
        try:
            return self.provider_factory(local_config(self.address.text(), self.model.text()))
        except ValueError as error:
            self.status.setText(str(error))
            self.model.setFocus() if not self.model.text().strip() else self.address.setFocus()
            return None

    def _start(self, provider, history=None):
        self._job += 1
        self._cancel = Event()
        self._set_busy(True)
        self._deadline.start(90000)
        Thread(target=run_request, args=(self._signals, self._job, self._cancel, provider, history), daemon=True).start()

    def test_connection(self):
        if self._busy or self.voice_active:
            return
        provider = self._provider()
        if provider:
            self._reply_label = None
            self.status.setText("Checking local server…")
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
        self.history = self.history[-16:]
        while sum(len(m.content) for m in self.history) > 24000:
            self.history.pop(0)
        self._reply_label = self._bubble("PetLink", "Thinking…")
        self.status.setText("Thinking · your local model is preparing a reply")
        self.activity.emit("thinking")
        self._start(provider, [SYSTEM, *self.history])
        self.composer.setFocus()
        self._scroll_bottom()

    def stop(self):
        if self._busy:
            self._cancel.set()
            self.status.setText("Stopping… waiting for the local server to release the request.")
            self.send_button.setEnabled(False)

    def _scroll_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _on_chunk(self, job, text):
        if job != self._job or self._cancel.is_set():
            return
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.maximum() - bar.value() < 40
        self._reply += text
        self._reply_label.setText(self._reply)
        if at_bottom:
            self._scroll_bottom()

    def _on_finished(self, job, outcome, detail):
        if job != self._job:
            return
        self._deadline.stop()
        if self._cancel.is_set():
            outcome, detail = "cancelled", "Response stopped."
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
                detail = "The model returned no text. Check the model, then retry."
            self.retry_button.setVisible(self._retry_text is not None)
        self.status.setText(detail if persisted else "Reply is visible but could not be saved. Use Retry save.")
        self._set_busy(False)
        self.activity.emit("finished")

    def closeEvent(self, event):
        self._save_draft()
        self.hide()
        event.ignore()

    def shutdown(self):
        self._cancel.set()
        self._deadline.stop()
        self._draft_timer.stop()
        self._save_draft()


class ReminderSignals(QObject):
    ready = Signal(int, int, str, bool)


class CompanionController(QObject):
    """Keep the pet alive when chat is hidden; own the app's chat lifecycle."""
    def __init__(self, pet, *, chat=None, database=None):
        super().__init__(pet)
        self.pet = pet
        self.chat = chat if chat is not None else ChatWindow(database=database)
        self.tasks = None
        self.database = database
        self.notifications = None
        self._notification_running = False
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
            self.tasks.confirmed.connect(lambda: pet.react("task_completed"))
            self.tasks.confirmed.connect(self.check_notifications)
            self.chat.tasks_requested.connect(self.show_tasks)
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
        QApplication.instance().aboutToQuit.connect(self.chat.shutdown)
        QApplication.instance().aboutToQuit.connect(self.voice.shutdown)

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
        self.chat.test_button.setEnabled(not busy and not self.chat._busy)
        self.chat.send_button.setEnabled(not busy and (self.chat._busy or bool(self.chat.composer.toPlainText().strip())))
        self.pet.controls.mic.setEnabled(not busy or self.voice.recording)
        self.pet.controls.mic.setToolTip("Stop recording" if self.voice.recording else ("Transcribing locally…" if busy else "Start voice input"))
        self.pet.controls.mic.setStyleSheet("background:#A94764;" if self.voice.recording else "")
        if not self.chat._busy:
            self.pet.react(("microphone_on" if self.voice.recording else "thinking") if busy else "finished")

    def check_notifications(self):
        if self.database is None or self._notification_running or self._notification_closed:
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
        if not success:
            self.pet.controls.message("Task notifications could not be checked. Open Tasks to retry.")
            return
        self.pet.set_notification_count(unread)
        if added:
            self.pet.controls.message(statement.split(" — ")[0][:30] + "\nTask alert · tap the bell to read.")
            if not self.chat._busy and not self.voice.active:
                self.pet.react("reminder")
                QTimer.singleShot(1800, self._settle_notice)

    def stop_notifications(self):
        self._notification_closed = True
        if hasattr(self, "notification_timer"):
            self.notification_timer.stop()
        if self._notification_worker and self._notification_worker.is_alive():
            self._notification_worker.join(timeout=3)

    def _settle_notice(self):
        if not self.chat._busy and not self.voice.active and self.pet.state.value == "happy":
            self.pet.react("finished")

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
        if not self.chat._busy:
            self.pet.react("chat_opened")
