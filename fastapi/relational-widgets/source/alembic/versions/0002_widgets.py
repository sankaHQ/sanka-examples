import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "widgets",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "parent_id", sa.Integer(), sa.ForeignKey("parents.id"), nullable=False
        ),
    )
    op.create_index("ix_widgets_parent_id", "widgets", ["parent_id"], unique=False)


def downgrade():
    op.drop_index("ix_widgets_parent_id", table_name="widgets")
    op.drop_table("widgets")
