"""Presentation wiring; task writes still go through revision-checked services."""
import json
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from sqlalchemy.exc import SQLAlchemyError
from .chat_widgets import TaskDraftCard


def install(controller):
    controller.draft_card = None
    controller._modal_pet = False
    def refresh():
        chat, pet = controller.chat, controller.pet
        if chat.database is not None and chat.isVisible():
            try:
                count = len(chat.database.pending(limit=101))
                chat.tasks_button.setText(f"Pending Tasks ({min(count,100)}{'+' if count>100 else ''})" if count else "Pending Tasks")
            except SQLAlchemyError:
                pass
        if QApplication.activeModalWidget() is not None:
            if pet.isVisible():
                pet.hide()
                controller._modal_pet = True
            return
        if controller._modal_pet:
            pet.show()
            controller._modal_pet = False
        if not chat.isVisible() or not pet.isVisible():
            return
        area, bounds = chat.screen().availableGeometry(), chat.frameGeometry()
        if not bounds.intersects(pet.frameGeometry()):
            if chat.layout().contentsMargins().right() > 32:
                chat.layout().setContentsMargins(24,24,24,24)
            return
        y = max(area.top(), min(bounds.top(), area.bottom()-pet.height()))
        if bounds.right()+pet.width()+16 < area.right():
            pet.move(bounds.right()+16,y)
        elif bounds.left()-pet.width()-16 >= area.left():
            pet.move(bounds.left()-pet.width()-16,y)
        elif chat.width() > 800:
            chat.layout().setContentsMargins(24,24,256,24)
            pet.move(bounds.right()-pet.width()-8,bounds.top()+88)
    controller.ui_timer = QTimer(controller)
    controller.ui_timer.timeout.connect(refresh)
    controller.ui_timer.start(1000)
    controller.chat.destroyed.connect(controller.ui_timer.stop)


def show_draft(controller, action):
    if controller.tasks is None:
        return
    if controller.draft_card is not None:
        controller.draft_card.hide()
        controller.draft_card.deleteLater()
    card = controller.draft_card = TaskDraftCard(action)
    chat, db = controller.chat, controller.database
    chat.message_layout.insertWidget(chat.message_layout.count()-1,card)
    def apply(mode):
        if card.isHidden():
            return
        if chat._task_context.get("action") != action:
            chat.status.setText("This draft changed. Continue the current draft before confirming.")
            return
        try:
            pending = chat._current_task_pending()
            if mode == "edit":
                controller._edit_model_draft(action)
                card.hide()
                return
            if mode == "cancel":
                if pending:
                    db.discard(pending["id"],pending["revision"])
                chat.reset_task_context()
            else:
                if pending is None:
                    reference = dict(id=db.propose([action]), revision=1)
                else:
                    reference = dict(id=pending["id"],revision=pending["revision"])
                    if json.loads(pending["payload"]) != [action]:
                        db.revise(reference["id"],reference["revision"],[action])
                        reference["revision"] += 1
                chat.attach_task_pending(reference)
                if mode == "confirm":
                    db.confirm(reference["id"],reference["revision"])
                    chat.reset_task_context()
                    chat.status.setText("Confirmed task saved. Open Pending Tasks to view its status and schedule.")
                    controller.pet.react("task_confirmed")
                    controller.check_notifications()
                else:
                    chat.status.setText("Saved to Pending Tasks. Review and confirm when ready.")
            controller.tasks.refresh()
            card.hide()
        except (ValueError,SQLAlchemyError):
            chat.status.setText("Could not apply this draft. Open Pending Tasks to review its latest version.")
    card.edit_requested.connect(lambda:apply("edit"))
    card.confirm_requested.connect(lambda:apply("confirm"))
    card.pending_requested.connect(lambda:apply("pending"))
    card.cancel_requested.connect(lambda:apply("cancel"))
    chat._scroll_bottom()
