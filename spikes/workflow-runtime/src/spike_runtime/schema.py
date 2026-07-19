"""Spike'a özel PostgreSQL şeması — PRODUCTION MIGRATION DEĞİLDİR.

Production Alembic history'sine (0001/0002) dokunmaz; tüm tablolar `spike_` önekiyle
Testcontainers içindeki geçici veritabanında kurulur.

Tasarım (production'a taşınacak kararlar için kanıt üretir):
- Her tenant tablosunda `tenant_id` + RLS **ENABLE + FORCE**.
- Roller: `spike_app` (API benzeri) ve `spike_worker` (dispatcher) — ikisi de
  NOSUPERUSER + **NOBYPASSRLS**. Worker'a yalnız kuyruk tablolarında
  (outbox/timers/inbox) kuyruk-geneli policy verilir; business tablolarında worker
  da tenant-scoped'tur.
- Published version immutability üç bağımsız katmanla: (1) kod yolunda UPDATE yok,
  (2) rollere UPDATE grant'ı verilmez, (3) BEFORE UPDATE/DELETE trigger'ı owner'ı
  bile engeller. Audit ve approval_decisions da append-only trigger'lıdır.
- Optimistic concurrency: `spike_instances.version`, `spike_approval_steps.version`.
- Duplicate approval koruması DB düzeyinde: `spike_approval_decisions.step_id UNIQUE`.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

APP_ROLE = "spike_app"
WORKER_ROLE = "spike_worker"

TENANT_TABLES = (
    "spike_workflow_versions",
    "spike_instances",
    "spike_node_executions",
    "spike_approval_steps",
    "spike_approval_decisions",
    "spike_outbox_events",
    "spike_processed_events",
    "spike_timers",
    "spike_notifications",
    "spike_audit_events",
)

# Worker'ın tenant context'i OLMADAN kuyruk yönetimi yapabildiği tablolar.
QUEUE_TABLES = ("spike_outbox_events", "spike_processed_events", "spike_timers")

_DDL = """
CREATE TABLE spike_workflow_versions (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    workflow_key  TEXT NOT NULL,
    version_no    INT  NOT NULL,
    definition    JSONB NOT NULL,
    content_hash  TEXT NOT NULL,
    published_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, workflow_key, version_no)
);

CREATE TABLE spike_instances (
    id                   UUID PRIMARY KEY,
    tenant_id            UUID NOT NULL,
    workflow_version_id  UUID NOT NULL REFERENCES spike_workflow_versions (id),
    status               TEXT NOT NULL CHECK (status IN
        ('running','waiting','completed','rejected','cancelled','failed')),
    current_node_id      TEXT NOT NULL,
    context              JSONB NOT NULL DEFAULT '{}'::jsonb,
    version              INT NOT NULL DEFAULT 1,
    created_at           TIMESTAMPTZ NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_spike_instances_tenant_status
    ON spike_instances (tenant_id, status, created_at);

CREATE TABLE spike_node_executions (
    id           UUID PRIMARY KEY,
    tenant_id    UUID NOT NULL,
    instance_id  UUID NOT NULL REFERENCES spike_instances (id),
    node_id      TEXT NOT NULL,
    node_type    TEXT NOT NULL,
    detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
    executed_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_spike_node_exec_tenant_instance
    ON spike_node_executions (tenant_id, instance_id, executed_at);

CREATE TABLE spike_approval_steps (
    id           UUID PRIMARY KEY,
    tenant_id    UUID NOT NULL,
    instance_id  UUID NOT NULL REFERENCES spike_instances (id),
    step_index   INT NOT NULL,
    approver_role TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN
        ('pending','active','approved','rejected','cancelled')),
    version      INT NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL,
    UNIQUE (instance_id, step_index)
);

CREATE TABLE spike_approval_decisions (
    id               UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    step_id          UUID NOT NULL UNIQUE REFERENCES spike_approval_steps (id),
    instance_id      UUID NOT NULL,
    actor_id         UUID NOT NULL,
    decision         TEXT NOT NULL CHECK (decision IN ('approved','rejected')),
    idempotency_key  TEXT NOT NULL,
    decided_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE spike_outbox_events (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    event_id          UUID NOT NULL UNIQUE,
    event_type        TEXT NOT NULL,
    payload           JSONB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending','processed','failed')),
    attempt           INT NOT NULL DEFAULT 0,
    available_at      TIMESTAMPTZ NOT NULL,
    claimed_by        TEXT,
    claim_expires_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL,
    processed_at      TIMESTAMPTZ
);
CREATE INDEX ix_spike_outbox_dispatch
    ON spike_outbox_events (status, available_at, id);

CREATE TABLE spike_processed_events (
    event_id     UUID NOT NULL,
    consumer     TEXT NOT NULL,
    tenant_id    UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (event_id, consumer)
);

CREATE TABLE spike_timers (
    id           UUID PRIMARY KEY,
    tenant_id    UUID NOT NULL,
    instance_id  UUID NOT NULL,
    purpose      TEXT NOT NULL,
    fire_at      TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','fired','cancelled')),
    fired_at     TIMESTAMPTZ,
    fired_by     TEXT,
    created_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_spike_timers_due ON spike_timers (status, fire_at);

CREATE TABLE spike_notifications (
    id              UUID PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    instance_id     UUID NOT NULL,
    recipient_role  TEXT NOT NULL,
    message_key     TEXT NOT NULL,
    source_event_id UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE spike_audit_events (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    event_id      UUID NOT NULL,
    actor_type    TEXT NOT NULL,
    actor_id      TEXT NOT NULL,
    action        TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id   TEXT NOT NULL,
    occurred_at   TIMESTAMPTZ NOT NULL,
    request_id    TEXT NOT NULL,
    reason        TEXT,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE FUNCTION spike_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only/immutable tablo: % üzerinde % yasak',
        TG_TABLE_NAME, TG_OP;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_versions_immutable
    BEFORE UPDATE OR DELETE ON spike_workflow_versions
    FOR EACH ROW EXECUTE FUNCTION spike_block_mutation();
CREATE TRIGGER trg_audit_append_only
    BEFORE UPDATE OR DELETE ON spike_audit_events
    FOR EACH ROW EXECUTE FUNCTION spike_block_mutation();
CREATE TRIGGER trg_decisions_immutable
    BEFORE UPDATE OR DELETE ON spike_approval_decisions
    FOR EACH ROW EXECUTE FUNCTION spike_block_mutation();
"""


def create_roles(admin_conn: Connection, *, app_password: str, worker_password: str) -> None:
    """İki spike rolü — ikisi de NOSUPERUSER + NOBYPASSRLS (SPK-10 kanıtının parçası).

    NOT: CREATE ROLE bir utility komutudur; PASSWORD bind parametresi KABUL ETMEZ.
    Parola literal olarak, tek tırnak escape'iyle gömülür. Bu YALNIZ izole
    Testcontainers ortamının sahte parolasıdır — gerçek secret değildir.
    """
    for role, pw in ((APP_ROLE, app_password), (WORKER_ROLE, worker_password)):
        literal_pw = "'" + pw.replace("'", "''") + "'"
        admin_conn.execute(
            text(
                f"CREATE ROLE {role} LOGIN PASSWORD {literal_pw} "
                f"NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        )


def create_schema(admin_conn: Connection) -> None:
    admin_conn.execute(text(_DDL))
    _apply_grants(admin_conn)
    _apply_rls(admin_conn)


def _apply_grants(conn: Connection) -> None:
    both = f"{APP_ROLE}, {WORKER_ROLE}"
    grants = [
        # Published versions ve decisions: UPDATE/DELETE grant'ı BİLEREK YOK.
        f"GRANT SELECT, INSERT ON spike_workflow_versions TO {both}",
        f"GRANT SELECT, INSERT ON spike_approval_decisions TO {both}",
        f"GRANT SELECT, INSERT ON spike_node_executions TO {both}",
        f"GRANT SELECT, INSERT ON spike_notifications TO {both}",
        f"GRANT SELECT, INSERT ON spike_audit_events TO {both}",
        f"GRANT SELECT, INSERT ON spike_processed_events TO {both}",
        f"GRANT SELECT, INSERT, UPDATE ON spike_instances TO {both}",
        f"GRANT SELECT, INSERT, UPDATE ON spike_approval_steps TO {both}",
        f"GRANT SELECT, INSERT, UPDATE ON spike_outbox_events TO {both}",
        f"GRANT SELECT, INSERT, UPDATE ON spike_timers TO {both}",
        f"GRANT USAGE, SELECT ON SEQUENCE spike_outbox_events_id_seq TO {both}",
    ]
    for stmt in grants:
        conn.execute(text(stmt))


def _apply_rls(conn: Connection) -> None:
    for table in TENANT_TABLES:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        # Metin karşılaştırması: boş/NULL context güvenli RED üretir, hata değil
        # (production 0001 migration'ındaki kanıtlanmış pattern).
        conn.execute(
            text(
                f"""
                CREATE POLICY p_tenant_scope ON {table}
                USING (tenant_id::text = current_setting('app.current_tenant_id', true))
                WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))
                """
            )
        )
    for table in QUEUE_TABLES:
        # Dispatcher kuyruk altyapısını tenant'lar arası yönetir; business
        # tablolarında worker da tenant-scoped kalır (SPK-10).
        conn.execute(
            text(
                f"""
                CREATE POLICY p_worker_queue ON {table}
                FOR ALL TO {WORKER_ROLE}
                USING (true) WITH CHECK (true)
                """
            )
        )
