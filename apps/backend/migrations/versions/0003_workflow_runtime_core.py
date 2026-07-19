"""workflow runtime core schema with RLS

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-19

ADDITIVE migration (Epic E09) — 0001/0002 IMMUTABLE kalır, dokunulmaz.

Workflow runtime core tabloları (hepsi 'workflow_runtime_' önekli, module ownership):
  definitions, definition_versions, instances, tasks, events, outbox, inbox, timers.

Kanıt: docs/architecture/workflow-runtime-spike-results.md (12/12 PASS, ADR-004).

Roller (0001 ile aynı ayrım):
  - flowpilot_migrator : DDL, tabloların sahibi.
  - flowpilot_app      : DML; NOSUPERUSER, NOBYPASSRLS.

Güvenlik:
  - Tüm tenant tablolarında RLS ENABLE + FORCE. FORCE, owner (migrator) üzerinden
    sessiz bypass'ı engeller.
  - Transaction-local context: app.current_tenant_id (set_config(..., true)).
    Context yoksa erişim DEFAULT DENY (metin karşılaştırması; boş context güvenli red).
  - Published version + append-only event + terminal decision immutability, koda ek
    olarak BEFORE UPDATE/DELETE trigger'ı ile DB düzeyinde de zorlanır.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "flowpilot_app"

TENANT_TABLES = (
    "workflow_runtime_definitions",
    "workflow_runtime_definition_versions",
    "workflow_runtime_instances",
    "workflow_runtime_tasks",
    "workflow_runtime_events",
    "workflow_runtime_outbox",
    "workflow_runtime_inbox",
    "workflow_runtime_timers",
)


def upgrade() -> None:
    _create_tables()
    _grant_app_role()
    _enable_rls()
    _create_immutability_triggers()


def _create_tables() -> None:
    op.create_table(
        "workflow_runtime_definitions",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("definition_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_definitions"),
        sa.UniqueConstraint(
            "tenant_id", "definition_key", name="uq_workflow_runtime_definitions_tenant_id"
        ),
    )

    op.create_table(
        "workflow_runtime_definition_versions",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("definition_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("definition", JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_definition_versions"),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            ["workflow_runtime_definitions.id"],
            name="fk_wr_definition_versions_definition_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "definition_id",
            "version_no",
            name="uq_workflow_runtime_definition_versions_tenant_id",
        ),
    )

    op.create_table(
        "workflow_runtime_instances",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("definition_version_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_node_id", sa.String(length=200), nullable=False),
        sa.Column("context", JSONB(), server_default="{}", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','waiting','completed','rejected','cancelled','failed')",
            name="ck_workflow_runtime_instances_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_instances"),
        sa.ForeignKeyConstraint(
            ["definition_version_id"],
            ["workflow_runtime_definition_versions.id"],
            name="fk_wr_instances_definition_version_id",
        ),
    )
    op.create_index(
        "ix_workflow_runtime_instances_tenant_status",
        "workflow_runtime_instances",
        ["tenant_id", "status", "created_at"],
    )

    op.create_table(
        "workflow_runtime_tasks",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("node_id", sa.String(length=200), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("approver_role", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decided_by_user_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','active','approved','rejected','changes_requested','cancelled')",
            name="ck_workflow_runtime_tasks_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_tasks"),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["workflow_runtime_instances.id"],
            name="fk_wr_tasks_instance_id",
        ),
        sa.UniqueConstraint(
            "instance_id", "node_id", "step_index", name="uq_workflow_runtime_tasks_instance_id"
        ),
    )

    op.create_table(
        "workflow_runtime_events",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("node_id", sa.String(length=200), nullable=True),
        sa.Column("actor_type", sa.String(length=32), server_default="system", nullable=False),
        sa.Column("detail", JSONB(), server_default="{}", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_events"),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["workflow_runtime_instances.id"],
            name="fk_wr_events_instance_id",
        ),
    )
    op.create_index(
        "ix_workflow_runtime_events_tenant_instance",
        "workflow_runtime_events",
        ["tenant_id", "instance_id", "occurred_at"],
    )

    op.create_table(
        "workflow_runtime_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("event_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','processed','failed')",
            name="ck_workflow_runtime_outbox_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_outbox"),
        sa.UniqueConstraint("event_id", name="uq_workflow_runtime_outbox_event_id"),
    )
    op.create_index(
        "ix_workflow_runtime_outbox_status",
        "workflow_runtime_outbox",
        ["status", "available_at", "id"],
    )

    op.create_table(
        "workflow_runtime_inbox",
        sa.Column("event_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("consumer", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "consumer", name="pk_workflow_runtime_inbox"),
    )

    op.create_table(
        "workflow_runtime_timers",
        sa.Column("id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("fire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fired_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','fired','cancelled')",
            name="ck_workflow_runtime_timers_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runtime_timers"),
    )
    op.create_index(
        "ix_workflow_runtime_timers_due", "workflow_runtime_timers", ["status", "fire_at"]
    )


def _grant_app_role() -> None:
    # Published versions, events, inbox, decisions: append-only → yalnız SELECT+INSERT.
    for table in (
        "workflow_runtime_definitions",
        "workflow_runtime_definition_versions",
        "workflow_runtime_events",
        "workflow_runtime_inbox",
    ):
        op.execute(f"GRANT SELECT, INSERT ON {table} TO {APP_ROLE}")
    # Mutable aggregate'ler + kuyruk: UPDATE gerekir (optimistic CAS, lease, claim).
    for table in (
        "workflow_runtime_instances",
        "workflow_runtime_tasks",
        "workflow_runtime_outbox",
        "workflow_runtime_timers",
    ):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(
        f"GRANT USAGE, SELECT ON SEQUENCE workflow_runtime_outbox_id_seq TO {APP_ROLE}"
    )


def _enable_rls() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # Metin karşılaştırması: boş/NULL context güvenle REDDEDER (0001 ile aynı desen).
        op.execute(
            f"""
            CREATE POLICY p_workflow_runtime_tenant_scope ON {table}
            USING (tenant_id::text = current_setting('app.current_tenant_id', true))
            WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
            """
        )


def _create_immutability_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION workflow_runtime_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'append-only/immutable tablo: % uzerinde % yasak',
                TG_TABLE_NAME, TG_OP;
        END
        $$ LANGUAGE plpgsql
        """
    )
    for table in (
        "workflow_runtime_definition_versions",
        "workflow_runtime_events",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION workflow_runtime_block_mutation()
            """
        )


def downgrade() -> None:
    for table in (
        "workflow_runtime_definition_versions",
        "workflow_runtime_events",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS workflow_runtime_block_mutation()")
    # Tabloları düşürmek policy, grant ve index'leri de kaldırır (FK ters sırada).
    op.drop_table("workflow_runtime_timers")
    op.drop_table("workflow_runtime_inbox")
    op.drop_table("workflow_runtime_outbox")
    op.drop_table("workflow_runtime_events")
    op.drop_table("workflow_runtime_tasks")
    op.drop_table("workflow_runtime_instances")
    op.drop_table("workflow_runtime_definition_versions")
    op.drop_table("workflow_runtime_definitions")
