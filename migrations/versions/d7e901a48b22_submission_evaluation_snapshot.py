"""Snapshot trusted judging contracts alongside submitted source.

Revision ID: d7e901a48b22
Revises: c869d03eecf9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d7e901a48b22"
down_revision = "c869d03eecf9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column(
            "evaluation", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.alter_column("submissions", "evaluation", server_default=None)


def downgrade() -> None:
    op.drop_column("submissions", "evaluation")
