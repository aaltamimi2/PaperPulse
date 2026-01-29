"""Initial schema with papers, feeds, users, and profiles.

Revision ID: 001_initial
Revises:
Create Date: 2026-01-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, default=False),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column("immediate_alerts_enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Create research_profiles table
    op.create_table(
        "research_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create interest_categories table
    op.create_table(
        "interest_categorys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("profile_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", sa.ARRAY(sa.String()), nullable=False, default=[]),
        sa.Column("excluded_keywords", sa.ARRAY(sa.String()), nullable=False, default=[]),
        sa.Column("followed_authors", sa.ARRAY(sa.String()), nullable=False, default=[]),
        sa.Column("followed_journals", sa.ARRAY(sa.String()), nullable=False, default=[]),
        sa.Column("profile_embedding", Vector(768), nullable=True),
        sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight_semantic", sa.Float(), nullable=False, default=0.4),
        sa.Column("weight_keyword", sa.Float(), nullable=False, default=0.3),
        sa.Column("weight_author", sa.Float(), nullable=False, default=0.2),
        sa.Column("weight_novelty", sa.Float(), nullable=False, default=0.1),
        sa.Column("threshold_immediate", sa.Float(), nullable=False, default=0.8),
        sa.Column("threshold_weekly", sa.Float(), nullable=False, default=0.5),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["research_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create rss_feeds table
    op.create_table(
        "r_s_s_feeds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("journal_name", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_fetch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, default=0),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("feed_title", sa.String(512), nullable=True),
        sa.Column("feed_link", sa.String(2048), nullable=True),
        sa.Column("etag", sa.String(255), nullable=True),
        sa.Column("last_modified", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_r_s_s_feeds_url", "r_s_s_feeds", ["url"], unique=True)

    # Create papers table
    op.create_table(
        "papers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("doi", sa.String(255), nullable=True),
        sa.Column("arxiv_id", sa.String(50), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("authors", sa.ARRAY(sa.String()), nullable=False, default=[]),
        sa.Column("journal", sa.String(512), nullable=True),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_feed_id", sa.UUID(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_feed_id"], ["r_s_s_feeds.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_papers_doi", "papers", ["doi"], unique=True)
    op.create_index("ix_papers_arxiv_id", "papers", ["arxiv_id"], unique=True)
    op.create_index("ix_papers_content_hash", "papers", ["content_hash"])
    op.create_index("ix_papers_published_date", "papers", ["published_date"])


def downgrade() -> None:
    op.drop_table("papers")
    op.drop_table("r_s_s_feeds")
    op.drop_table("interest_categorys")
    op.drop_table("research_profiles")
    op.drop_table("users")
