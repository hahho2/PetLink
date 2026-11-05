"""Keep an unfinished task clarification separate from ordinary chat."""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("task_context", sa.Text, nullable=False, server_default="{}"))


def downgrade():
    raise RuntimeError("Restore a backup rather than removing unfinished task context.")
