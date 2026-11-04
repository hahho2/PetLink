"""Readable local notification statements with explicit acknowledgement."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
from sqlalchemy.exc import SQLAlchemyError
from .ui_theme import stylesheet


class NotificationWindow(QWidget):
    changed = Signal()
    tasks_requested = Signal()

    def __init__(self, database):
        super().__init__()
        self.database = database
        self._limit = 100
        self.setObjectName("chat")
        self.setWindowTitle("PetLink — Notifications")
        self.resize(420, 430)
        self.setStyleSheet(stylesheet())
        layout = QVBoxLayout(self)
        heading = QLabel("From your pet")
        heading.setObjectName("title")
        layout.addWidget(heading)
        self.items = QListWidget()
        self.items.setAccessibleName("Task notifications")
        layout.addWidget(self.items)
        self.more = QPushButton("Load older notifications")
        self.more.clicked.connect(self.load_more)
        layout.addWidget(self.more)
        self.statement = QPlainTextEdit()
        self.statement.setReadOnly(True)
        self.statement.setAccessibleName("Full notification statement")
        layout.addWidget(self.statement)
        self.read = QPushButton("Mark selected as read")
        self.read.clicked.connect(self.mark_read)
        layout.addWidget(self.read)
        tasks = QPushButton("Open Tasks & Pending")
        tasks.clicked.connect(self.tasks_requested.emit)
        layout.addWidget(tasks)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.items.currentItemChanged.connect(self.select)

    def refresh(self):
        try:
            self.items.clear()
            rows = self.database.notifications(limit=self._limit + 1)
            self.more.setVisible(len(rows) > self._limit)
            for row in rows[:self._limit]:
                item = QListWidgetItem(("Unread · " if row["read_at"] is None else "Read · ") + row["statement"].split(" — ")[0])
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.items.addItem(item)
            self.status.setText(f"Showing the latest {self.items.count()} notifications." if self.items.count() else "No task notifications yet.")
            if self.items.count():
                self.items.setCurrentRow(0)
            self.select()
        except SQLAlchemyError:
            self.status.setText("Could not load notifications. Close and reopen to retry.")

    def select(self, *args):
        item = self.items.currentItem()
        row = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.statement.setPlainText(row["statement"] if row else "")
        self.read.setEnabled(row is not None and row["read_at"] is None)

    def load_more(self):
        self._limit += 100
        self.refresh()

    def mark_read(self):
        item = self.items.currentItem()
        if item:
            try:
                self.database.read_notification(item.data(Qt.ItemDataRole.UserRole)["id"])
                self.refresh()
                self.changed.emit()
            except SQLAlchemyError:
                self.status.setText("Could not mark this alert as read. Try again.")

    def closeEvent(self, event):
        self.hide()
        event.ignore()
