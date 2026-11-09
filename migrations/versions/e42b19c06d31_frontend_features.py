"""Collections, account drafts, preferences, and avatar metadata.

Revision ID: e42b19c06d31
Revises: d7e901a48b22
"""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e42b19c06d31"
down_revision = "d7e901a48b22"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("custom_input", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("avatar_key", sa.String(36), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "preferences", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_table(
        "question_collections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "difficulty",
            sa.Enum(
                "easy",
                "medium",
                "hard",
                name="difficulty",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
    )
    op.create_table(
        "workspace_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("workspace", sa.String(36), nullable=False),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "language",
            sa.Enum(
                "python", "java", "cpp", name="language", native_enum=False, create_constraint=True
            ),
            nullable=False,
        ),
        sa.Column("source_code", sa.Text(), nullable=True),
        sa.Column("stdin", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "workspace", "language"),
        sa.CheckConstraint("revision > 0"),
        sa.CheckConstraint(
            "(workspace = 'playground' AND question_id IS NULL) OR "
            "(workspace <> 'playground' AND question_id IS NOT NULL)"
        ),
    )
    collections = sa.table(
        "question_collections",
        sa.column("id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("position", sa.Integer()),
        sa.column("difficulty", sa.String()),
    )
    op.bulk_insert(
        collections,
        [
            {
                "id": uuid5(NAMESPACE_URL, "lustcode:collection:" + slug),
                "created_at": datetime.now(UTC),
                "slug": slug,
                "name": name,
                "description": description,
                "position": i,
                "difficulty": level,
            }
            for i, (slug, name, description, level) in enumerate(
                [
                    ("foreplay", "Foreplay", "Published easy problems in catalog order.", "easy"),
                    (
                        "main-event",
                        "The main event",
                        "Published medium problems in catalog order.",
                        "medium",
                    ),
                    ("hardcore", "Hardcore", "Published hard problems in catalog order.", "hard"),
                ]
            )
        ],
    )
    for table in ("question_collections", "workspace_drafts"):
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.drop_column("submissions", "custom_input")
    op.drop_table("workspace_drafts")
    op.drop_table("question_collections")
    op.drop_column("users", "preferences")
    op.drop_column("users", "avatar_key")
