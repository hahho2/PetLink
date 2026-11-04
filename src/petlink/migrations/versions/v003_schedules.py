"""Confirmed schedules, separate task occurrences and timed notification keys."""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = depends_on = None


def upgrade():
    op.create_table("task_schedules", sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("frequency", sa.Text, nullable=False), sa.Column("reminder_time", sa.Text),
        sa.Column("timezone", sa.Text, nullable=False), sa.Column("revision", sa.Integer, nullable=False),
        sa.CheckConstraint("frequency IN ('none','daily','weekly')"))
    op.create_table("task_occurrences", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("schedule_revision", sa.Integer, nullable=False), sa.Column("scheduled_date", sa.Text, nullable=False),
        sa.Column("reminder_at", sa.Text, nullable=False), sa.Column("completed_at", sa.Text), sa.Column("cancelled_at", sa.Text),
        sa.UniqueConstraint("task_id", "schedule_revision", "scheduled_date", name="uq_task_occurrence"))
    op.create_index("ix_occurrences_due", "task_occurrences", ["cancelled_at", "completed_at", "reminder_at"])
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("event_key", sa.Text))
        batch.drop_constraint("uq_notification_due", type_="unique")
        batch.create_unique_constraint("uq_notification_event", ["event_key"])
    op.execute("UPDATE notifications SET event_key='due:' || task_id || ':' || due_date")


def downgrade():
    raise RuntimeError("Restore a backup rather than removing schedules and completion history.")
