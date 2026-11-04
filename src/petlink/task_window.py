"""Manual task drafts: review before any change reaches the task table."""
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget)
from sqlalchemy.exc import SQLAlchemyError

from .ui_theme import stylesheet
from .scheduling import DEFAULT_SCHEDULE

FIELDS = ("title", "description", "status", "priority", "due_date", "schedule")
DEFAULTS = dict(title="", description="", status="pending", priority="normal", due_date=None)


def summary(actions):
    parts = []
    for action in actions:
        if action["kind"] == "complete_occurrence":
            parts.append(f"Complete occurrence: {action.get('label', '')}\nOnly this occurrence is completed; the repeating task continues.")
        elif action["kind"] == "delete":
            parts.append(f"Remove task #{action['task_id']}: {action.get('label', '')}\nThe local record and audit are retained; it leaves the active list.")
        else:
            values = action["values"]
            parts.append(f"{action['kind'].title()} task: {values['title']}\n"
                f"Status: {values['status'].replace('_', ' ')} · Priority: {values['priority']}\n"
                f"Due: {values['due_date'] or 'Not set'}\n{values['description']}")
            schedule = values.get("schedule")
            if schedule:
                parts[-1] += f"\nRepeat: {schedule['frequency']}\nReminder: {schedule['reminder_time'] or ('00:00 on each occurrence' if schedule['frequency'] != 'none' else 'None')} · {schedule['timezone']}"
                if schedule["frequency"] != "none":
                    parts[-1] += "\nConfirming authorizes future occurrences. Setting the whole task Done stops the series."
            if values["status"] == "done":
                parts[-1] += "\nThe whole task/series is Done; future reminders stop."
    return "\n\n".join(parts)


class TaskEditor(QDialog):
    def __init__(self, database, *, action=None, pending=None, parent=None):
        super().__init__(parent)
        self.setObjectName("chat")
        self.database, self.pending = database, pending
        self.action = action or {"kind": "create"}
        values = self.action.get("values", DEFAULTS)
        self.setWindowTitle("Review task draft")
        self.setStyleSheet(stylesheet())
        self.resize(460, 620)
        layout = QVBoxLayout(self)
        note = QLabel("This is a draft. Review it before confirming a saved task.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.title = QLineEdit(values["title"])
        self.title.setMaxLength(200)
        self.description = QPlainTextEdit(values["description"])
        self.description.setMaximumHeight(110)
        self.status = QComboBox()
        for label, value in (("Pending", "pending"), ("In progress", "in_progress"), ("Done", "done")):
            self.status.addItem(label, value)
        self.status.setCurrentIndex(self.status.findData(values["status"]))
        self.priority = QComboBox()
        self.priority.addItems(["low", "normal", "high"])
        self.priority.setCurrentText(values["priority"])
        self.due = QLineEdit(values["due_date"] or "")
        self.due.setPlaceholderText("YYYY-MM-DD, or leave empty")
        schedule = values.get("schedule", DEFAULT_SCHEDULE)
        self.frequency = QComboBox()
        for label, value in (("Does not repeat", "none"), ("Every day", "daily"), ("Every week", "weekly")):
            self.frequency.addItem(label, value)
        self.frequency.setCurrentIndex(self.frequency.findData(schedule["frequency"]))
        self.reminder_time = QLineEdit(schedule["reminder_time"] or "")
        self.reminder_time.setPlaceholderText("HH:MM (24-hour), e.g. 18:30")
        self.timezone = QLineEdit(schedule["timezone"])
        self.timezone.setPlaceholderText("Asia/Kolkata or UTC")
        for label, control in (("Title", self.title), ("Description", self.description),
                               ("Status", self.status), ("Priority", self.priority), ("Due/start date", self.due),
                               ("Repeat", self.frequency), ("Remind at", self.reminder_time), ("Timezone", self.timezone)):
            control.setAccessibleName(label)
            form.addRow(label, control)
        layout.addLayout(form)
        schedule_note = QLabel("Repeats are anchored to the start date. Blank time on a repeat means midnight. Reminders run while PetLink is open.")
        schedule_note.setWordWrap(True)
        layout.addWidget(schedule_note)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        review = QPushButton("Review draft")
        review.setObjectName("primary")
        review.clicked.connect(self.submit)
        actions.addWidget(cancel)
        actions.addWidget(review)
        layout.addLayout(actions)

    def submit(self):
        action = {**self.action, "values": dict(title=self.title.text().strip(),
            description=self.description.toPlainText(), status=self.status.currentData(),
            priority=self.priority.currentText(), due_date=self.due.text().strip() or None,
            schedule=dict(frequency=self.frequency.currentData(), reminder_time=self.reminder_time.text().strip() or None,
                          timezone=self.timezone.text().strip()))}
        try:
            if self.pending:
                self.database.revise(self.pending["id"], self.pending["revision"], [action])
            else:
                self.database.propose([action])
        except (ValueError, SQLAlchemyError) as exc:
            self.error.setText(str(exc) if isinstance(exc, ValueError) else "Could not save the draft. Your fields are still here; try again.")
            self.title.setFocus()
            return
        self.accept()


class TaskWindow(QWidget):
    confirmed = Signal()

    def __init__(self, database):
        super().__init__()
        self.database = database
        self._limit = 100
        self._pending_limit = 100
        self._occurrence_limit = 100
        self.setObjectName("chat")
        self.setWindowTitle("PetLink — Tasks & Pending")
        self.setStyleSheet(stylesheet())
        self.resize(520, 690)
        self.setMinimumSize(390, 570)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        heading = QLabel("Tasks & Pending")
        heading.setObjectName("title")
        layout.addWidget(heading)
        note = QLabel("Task changes stay pending until you confirm their preview.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = QTabWidget()
        self.tasks = QListWidget()
        self.tasks.setAccessibleName("Saved tasks")
        self.pending = QListWidget()
        self.pending.setAccessibleName("Pending task drafts")
        self.tabs.addTab(self.tasks, "Tasks")
        self.tabs.addTab(self.pending, "Pending")
        self.occurrences = QListWidget()
        self.occurrences.setAccessibleName("Scheduled task occurrences")
        self.tabs.addTab(self.occurrences, "Occurrences")
        layout.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        for title, handler in (("New task", self.new_task), ("Edit", self.edit_task), ("Remove", self.delete_task), ("Refresh", self.refresh)):
            button = QPushButton(title)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        self.complete_occurrence_button = QPushButton("Complete selected occurrence")
        self.complete_occurrence_button.clicked.connect(self.complete_occurrence)
        layout.addWidget(self.complete_occurrence_button)
        self.more = QPushButton("Load more tasks")
        self.more.clicked.connect(self.load_more)
        layout.addWidget(self.more)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("Proposed changes")
        self.preview.setPlaceholderText("Select a pending draft to review the exact changes.")
        self.preview.setMaximumHeight(150)
        layout.addWidget(self.preview)
        actions = QHBoxLayout()
        self.edit = QPushButton("Edit draft")
        self.edit.clicked.connect(self.edit_draft)
        self.discard = QPushButton("Discard draft")
        self.discard.clicked.connect(self.discard_draft)
        self.confirm = QPushButton("Confirm changes")
        self.confirm.setObjectName("primary")
        self.confirm.clicked.connect(self.confirm_draft)
        for button in (self.edit, self.discard, self.confirm):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        self.feedback.setMinimumHeight(40)
        layout.addWidget(self.feedback)
        self.pending.currentItemChanged.connect(self.select_pending)
        self.tabs.currentChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        try:
            selected = self.selected(self.pending)
            self.tasks.clear()
            rows = self.database.tasks(limit=self._limit + 1)
            more_tasks = len(rows) > self._limit
            for task in rows[:self._limit]:
                schedule = task["schedule"]
                clock = schedule["reminder_time"] or ("00:00" if schedule["frequency"] != "none" else "Not set")
                item = QListWidgetItem(f"#{task['id']}  {task['title']}\n{task['status'].replace('_', ' ')} · {task['priority']} · Due: {task['due_date'] or 'Not set'}\nRepeat: {schedule['frequency']} · Reminder: {clock}")
                item.setData(Qt.ItemDataRole.UserRole, task)
                self.tasks.addItem(item)
            self.pending.clear()
            proposals = self.database.pending(limit=self._pending_limit + 1)
            more_pending = len(proposals) > self._pending_limit
            for pending in proposals[:self._pending_limit]:
                item = QListWidgetItem(summary(json.loads(pending["payload"])).split("\n")[0])
                item.setData(Qt.ItemDataRole.UserRole, pending)
                self.pending.addItem(item)
                if selected and pending["id"] == selected["id"]:
                    self.pending.setCurrentItem(item)
            self.tabs.setTabText(1, f"Pending ({min(len(proposals), self._pending_limit)}{'+' if more_pending else ''})")
            pending_tab = self.tabs.currentIndex() == 1
            self.occurrences.clear()
            occurrences = self.database.occurrences(limit=self._occurrence_limit + 1)
            for occurrence in occurrences[:self._occurrence_limit]:
                label = "Done" if occurrence["completed_at"] else "Pending"
                item = QListWidgetItem(f"{occurrence['title']} — {occurrence['scheduled_date']}\n{label} · {occurrence['local_time'] or '00:00'} · {occurrence['timezone']}")
                item.setData(Qt.ItemDataRole.UserRole, occurrence)
                self.occurrences.addItem(item)
            occurrence_tab = self.tabs.currentIndex() == 2
            self.complete_occurrence_button.setVisible(occurrence_tab)
            self.more.setText("Load more occurrences" if occurrence_tab else ("Load more drafts" if pending_tab else "Load more tasks"))
            self.more.setVisible(len(occurrences) > self._occurrence_limit if occurrence_tab else (more_pending if pending_tab else more_tasks))
            self.select_pending()
        except SQLAlchemyError:
            self.feedback.setText("Could not read the local database. Close other database tools and try again.")

    @staticmethod
    def selected(list_widget):
        item = list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_pending(self, *args):
        pending = self.selected(self.pending)
        actions = json.loads(pending["payload"]) if pending else []
        self.preview.setPlainText(summary(actions))
        self.confirm.setEnabled(bool(pending))
        self.discard.setEnabled(bool(pending))
        self.edit.setEnabled(len(actions) == 1 and actions[0]["kind"] in ("create", "update"))

    def _open_editor(self, action=None, pending=None):
        dialog = TaskEditor(self.database, action=action, pending=pending, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.tabs.setCurrentIndex(1)
            if self.pending.count():
                self.pending.setCurrentRow(0)
            self.feedback.setText("Draft saved locally. Review it, then confirm to change tasks.")

    def new_task(self):
        self._open_editor()

    def edit_task(self):
        task = self.selected(self.tasks)
        if task:
            self._open_editor(dict(kind="update", task_id=task["id"], version=task["version"], values={key: task[key] for key in FIELDS}))
        else:
            self.feedback.setText("Select a saved task to edit.")

    def delete_task(self):
        task = self.selected(self.tasks)
        if not task:
            self.feedback.setText("Select a saved task to remove.")
            return
        try:
            self.database.propose([dict(kind="delete", task_id=task["id"], version=task["version"], label=task["title"])])
            self.refresh()
            self.tabs.setCurrentIndex(1)
            self.pending.setCurrentRow(0)
            self.feedback.setText("Removal proposed. The task remains active until you confirm.")
        except (ValueError, SQLAlchemyError):
            self.feedback.setText("Could not save the removal draft. No task was removed.")

    def edit_draft(self):
        pending = self.selected(self.pending)
        if pending:
            actions = json.loads(pending["payload"])
            if len(actions) == 1 and actions[0]["kind"] in ("create", "update"):
                self._open_editor(actions[0], pending)

    def complete_occurrence(self):
        occurrence = self.selected(self.occurrences)
        if not occurrence or occurrence["completed_at"]:
            self.feedback.setText("Select a pending occurrence.")
            return
        try:
            self.database.propose([dict(kind="complete_occurrence", task_id=occurrence["task_id"],
                version=occurrence["task_version"], occurrence_id=occurrence["id"],
                label=f"{occurrence['title']} on {occurrence['scheduled_date']}")])
            self.refresh()
            self.tabs.setCurrentIndex(1)
            self.pending.setCurrentRow(0)
            self.feedback.setText("Completion proposed. Review and confirm this occurrence.")
        except (ValueError, SQLAlchemyError):
            self.feedback.setText("Could not save the completion draft. Refresh and try again.")

    def _apply_pending(self, confirm):
        pending = self.selected(self.pending)
        if not pending:
            return
        try:
            if confirm:
                self.database.confirm(pending["id"], pending["revision"])
            else:
                self.database.discard(pending["id"], pending["revision"])
            self.refresh()
            self.feedback.setText("Confirmed changes saved." if confirm else "Draft discarded. Saved tasks were not changed.")
            if confirm:
                self.confirmed.emit()
        except (ValueError, SQLAlchemyError) as exc:
            self.feedback.setText(str(exc) if isinstance(exc, ValueError) else "Could not save. The transaction was rolled back; review and retry.")

    def confirm_draft(self):
        self._apply_pending(True)

    def discard_draft(self):
        self._apply_pending(False)

    def load_more(self):
        if self.tabs.currentIndex() == 2:
            self._occurrence_limit += 100
        elif self.tabs.currentIndex() == 1:
            self._pending_limit += 100
        else:
            self._limit += 100
        self.refresh()

    def closeEvent(self, event):
        self.hide()
        event.ignore()
