"""Initial local persistence. This revision is frozen; extend with new revisions."""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    op.create_table("conversations", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.Text, nullable=False), sa.Column("draft", sa.Text, nullable=False, server_default=""))
    op.create_table("messages", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.Text, nullable=False), sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False), sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')"),
        sa.CheckConstraint("status IN ('complete','incomplete')"))
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "id"])
    op.create_table("tasks", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False), sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False), sa.Column("priority", sa.Text, nullable=False),
        sa.Column("due_date", sa.Text), sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False), sa.Column("deleted_at", sa.Text),
        sa.Column("version", sa.Integer, nullable=False),
        sa.CheckConstraint("status IN ('pending','in_progress','done')"),
        sa.CheckConstraint("priority IN ('low','normal','high')"))
    op.create_index("ix_tasks_active", "tasks", ["deleted_at", "id"])
    op.create_table("pending_actions", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payload", sa.Text, nullable=False), sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False), sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("status IN ('pending','applied','discarded')"))
    op.create_table("audit_events", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("pending_id", sa.Integer, sa.ForeignKey("pending_actions.id"), nullable=False),
        sa.Column("action", sa.Text, nullable=False), sa.Column("task_id", sa.Integer, nullable=False),
        sa.Column("before_json", sa.Text), sa.Column("after_json", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False))


def downgrade():
    raise RuntimeError("Automatic destructive downgrades are not supported; restore a local backup instead.")
