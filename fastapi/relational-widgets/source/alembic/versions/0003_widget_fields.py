import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "widgets",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("widgets", sa.Column("note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("widgets", "note")
    op.drop_column("widgets", "enabled")
