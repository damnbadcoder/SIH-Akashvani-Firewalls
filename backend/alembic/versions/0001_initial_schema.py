"""Initial schema: users, sessions, files, previews, deliverables, chat_messages

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-12 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("user_type", sa.String(length=100), nullable=False, server_default="Organisation"),
        sa.Column("organisation", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("is_organisation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("source_links_json", sa.Text(), nullable=True),
        sa.Column("grounding_md", sa.Text(), nullable=True),
        sa.Column("grounding_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # 3. Files table
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=False),
        sa.Column("file_format", sa.String(length=50), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("extracted_markdown", sa.Text(), nullable=True),
        sa.Column("extracted_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_files_session_id", "files", ["session_id"])

    # 4. Previews table (Preview.md and Preview_edited.md)
    op.create_table(
        "previews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("output_type", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("original_preview_path", sa.String(length=512), nullable=True),
        sa.Column("original_preview_content", sa.Text(), nullable=False),
        sa.Column("edited_preview_path", sa.String(length=512), nullable=True),
        sa.Column("edited_preview_content", sa.Text(), nullable=True),
        sa.Column("is_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_organisation", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sensitive_flags_json", sa.Text(), nullable=True),
        sa.Column("citations_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_previews_session_id", "previews", ["session_id"])

    # 5. Deliverables table
    op.create_table(
        "deliverables",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("output_type", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("parameters_json", sa.Text(), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=True),
        sa.Column("verification_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_deliverables_session_id", "deliverables", ["session_id"])

    # 6. Chat Messages table
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("deliverables")
    op.drop_table("previews")
    op.drop_table("files")
    op.drop_table("sessions")
    op.drop_table("users")
