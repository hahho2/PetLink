"""Optional inclusive end date for recurring schedules."""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = depends_on = None


def upgrade():
    op.add_column("task_schedules", sa.Column("end_date", sa.Text))


def downgrade():
    raise RuntimeError("Restore a backup rather than removing recurrence end dates.")
