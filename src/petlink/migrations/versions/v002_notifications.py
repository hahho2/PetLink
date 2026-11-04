"""Persistent task alerts, separate from task records."""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = depends_on = None


def upgrade():
    op.create_table("notifications", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("due_date", sa.Text, nullable=False), sa.Column("statement", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False), sa.Column("read_at", sa.Text),
        sa.UniqueConstraint("task_id", "due_date", name="uq_notification_due"))
    op.create_index("ix_notifications_unread", "notifications", ["read_at", "id"])


def downgrade():
    raise RuntimeError("Restore a backup rather than deleting notification history.")
