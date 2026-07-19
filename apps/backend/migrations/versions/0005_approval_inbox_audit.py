"""approval role assignments, decisions, audit + task assignee

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-19

ADDITIVE migration — 0001/0002/0003/0004 IMMUTABLE kalır.

- workflow_runtime_tasks.assigned_user_id (nullable) — task oluşturulurken assignee
  SABİTLENİR (owner #5).
- approval_role_assignments — tenant + role_key için TEK aktif assignee
  (partial unique index WHERE status='active').
- approval_decisions — append-only; task başına tek terminal karar (unique task_id) +
  tenant/idempotency_key unique.
- audit_entries — append-only (SELECT+INSERT grant + BEFORE UPDATE/DELETE trigger).

Güvenlik: tüm tenant tablolarında RLS ENABLE + FORCE + tenant policy. Missing context →
DEFAULT DENY. flowpilot_app NOSUPERUSER + NOBYPASSRLS. Cross-module FK YOK (ASM-0012).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"
TENANT_TABLES = ("approval_role_assignments", "approval_decisions", "audit_entries")


def upgrade() -> None:
    # --- workflow_runtime_tasks: assignee kolonu (0003 tablosuna ADDITIVE) ---
    op.add_column(
        "workflow_runtime_tasks",
        sa.Column("assigned_user_id", PgUUID(as_uuid=True), nullable=True),
    )

    # --- approval_role_assignments ---
    op.create_table(
        "approval_role_assignments",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("assigned_user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role_key IN ('team_manager','finance','general_manager')",
            name="ck_approval_role_assignments_role_key_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked')", name="ck_approval_role_assignments_status_valid"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_role_assignments"),
    )
    op.create_index(
        "ix_approval_role_assignments_tenant",
        "approval_role_assignments",
        ["tenant_id", "role_key"],
    )
    # Tenant + role için TEK aktif assignee (partial unique).
    op.execute(
        "CREATE UNIQUE INDEX uq_approval_role_assignments_active "
        "ON approval_role_assignments (tenant_id, role_key) WHERE status = 'active'"
    )

    # --- approval_decisions (append-only) ---
    op.create_table(
        "approval_decisions",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("task_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve','reject')", name="ck_approval_decisions_decision_valid"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_decisions"),
        sa.UniqueConstraint("task_id", name="uq_approval_decisions_task_id"),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_approval_decisions_tenant_id"
        ),
    )

    # --- audit_entries (append-only) ---
    op.create_table(
        "audit_entries",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("role_key", sa.String(length=64), nullable=True),
        sa.Column("task_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        # Deterministik timeline sırası (aynı occurred_at'te insertion order korunur).
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_entries"),
    )
    op.create_index(
        "ix_audit_entries_tenant_aggregate",
        "audit_entries",
        ["tenant_id", "aggregate_id", "occurred_at"],
    )

    _grant_app_role()
    _enable_rls()
    _audit_append_only_trigger()


def _grant_app_role() -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON approval_role_assignments TO {APP_ROLE}")
    # approval_decisions + audit_entries append-only → UPDATE/DELETE grant YOK.
    op.execute(f"GRANT SELECT, INSERT ON approval_decisions TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON audit_entries TO {APP_ROLE}")


def _enable_rls() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY p_{table}_tenant_scope ON {table}
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
            """
        )


def _audit_append_only_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION audit_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'append-only tablo: % uzerinde % yasak', TG_TABLE_NAME, TG_OP;
        END
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("audit_entries", "approval_decisions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION audit_block_mutation()
            """
        )


def downgrade() -> None:
    for table in ("audit_entries", "approval_decisions"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS audit_block_mutation()")
    op.drop_table("audit_entries")
    op.drop_table("approval_decisions")
    op.execute("DROP INDEX IF EXISTS uq_approval_role_assignments_active")
    op.drop_table("approval_role_assignments")
    op.drop_column("workflow_runtime_tasks", "assigned_user_id")
