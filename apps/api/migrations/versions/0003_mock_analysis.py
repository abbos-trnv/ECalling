"""Immutable transcript/analysis results and pipeline settings snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "processing_runs",
        sa.Column("pipeline_profile", sa.String(30), nullable=False, server_default="preprocess"),
    )
    op.add_column(
        "processing_runs",
        sa.Column("provider_settings", JSONB(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("processing_runs.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("asr_provider", sa.String(50), nullable=False),
        sa.Column("asr_model", sa.String(100), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("payload_jsonb", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("id", "run_id", name="uq_transcript_run"),
    )
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("processing_runs.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("transcript_id", sa.Uuid(), nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("scorecard_snapshot", JSONB(), nullable=False),
        sa.Column("payload_jsonb", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id", "run_id"], ["transcripts.id", "transcripts.run_id"]
        ),
    )
    op.execute("""CREATE FUNCTION forbid_result_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Published results are immutable' USING ERRCODE='23514'; END; $$""")
    for table in ("transcripts", "analysis_runs"):
        op.execute(
            f"CREATE TRIGGER immutable_result BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_result_update()"
        )


def downgrade():
    op.drop_table("analysis_runs")
    op.drop_table("transcripts")
    op.execute("DROP FUNCTION forbid_result_update()")
    op.drop_column("processing_runs", "provider_settings")
    op.drop_column("processing_runs", "pipeline_profile")
