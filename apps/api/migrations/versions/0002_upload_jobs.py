"""Audio assets, processing runs and a durable PostgreSQL queue."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_employee_company", "employees", ["id", "company_id"])
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=True),
        sa.Column("filename_safe", sa.String(200), nullable=False),
        sa.Column("object_key", sa.String(300), nullable=False, unique=True),
        sa.Column("audio_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("audio_format", sa.String(10), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["employee_id", "company_id"], ["employees.id", "employees.company_id"]
        ),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_call_idempotency"),
        sa.CheckConstraint("size_bytes > 0 AND duration_ms > 0", name="ck_call_audio_positive"),
        sa.CheckConstraint(
            "status IN ('queued','processing','awaiting_analysis','completed','failed')",
            name="ck_call_status",
        ),
    )
    op.create_index("ix_calls_company_created", "calls", ["company_id", "created_at", "id"])
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "call_id", sa.Uuid(), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("failure_code", sa.String(60), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('queued','processing','awaiting_analysis','completed','failed')",
            name="ck_run_status",
        ),
    )
    op.create_index("ix_runs_call", "processing_runs", ["call_id", "created_at", "id"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("processing_runs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('queued','processing','completed','failed')", name="ck_job_status"
        ),
        sa.CheckConstraint("attempt >= 0 AND max_attempts > 0", name="ck_job_attempts"),
    )
    op.create_index("ix_jobs_poll", "jobs", ["status", "available_at", "lease_until"])


def downgrade():
    op.drop_table("jobs")
    op.drop_table("processing_runs")
    op.drop_table("calls")
    op.drop_constraint("uq_employee_company", "employees", type_="unique")
