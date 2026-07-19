"""SPK-01 — Published workflow version immutable.

Kanıt: (a) uygulama rolünün UPDATE'i DB tarafından reddedilir (grant yok),
(b) owner'ın UPDATE'i bile trigger ile engellenir, (c) v2 ayrı kayıt olur ve
v1'in içeriği + hash'i bit düzeyinde değişmez.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_actor_context, set_tenant_context
from spike_runtime.definition import content_hash, load_fixture

from .conftest import T0
from .flow_helpers import publish_v1


def test_published_version_is_immutable(
    app_sf: sessionmaker[Session],
    admin_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)

    def read_v1() -> tuple[str, str]:
        with app_sf() as s, s.begin():
            set_tenant_context(s, tenant_a)
            row = s.execute(
                text("SELECT definition, content_hash FROM spike_workflow_versions WHERE id = :id"),
                {"id": str(v1.id)},
            ).one()
            return json.dumps(row[0], sort_keys=True), str(row[1])

    definition_before, hash_before = read_v1()
    assert hash_before == v1.content_hash

    # (a) Uygulama rolü ham SQL ile bile UPDATE çalıştıramaz (grant yok).
    with pytest.raises(ProgrammingError), app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        s.execute(  # psycopg InsufficientPrivilege bekleniyor
            text("UPDATE spike_workflow_versions SET definition = '{}'::jsonb WHERE id = :id"),
            {"id": str(v1.id)},
        )

    # (a2) Tablo sahibi (admin) bile UPDATE edemez — BEFORE UPDATE trigger'ı.
    with pytest.raises(DBAPIError, match="immutable"), admin_sf() as s, s.begin():
        s.execute(
            text("UPDATE spike_workflow_versions SET version_no = 99 WHERE id = :id"),
            {"id": str(v1.id)},
        )

    # (b) Yeni düzenleme = YENİ version kaydı (v2); v1'e dokunulmaz.
    actor = uuid.uuid4()
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        set_actor_context(s, str(actor))
        v2 = rt.publish_version(
            s,
            tenant_id=tenant_a,
            workflow_key="purchase-request",
            version_no=2,
            definition=load_fixture("purchase_request_v2.json"),
            actor_id=actor,
            request_id="req-publish-v2",
            now=T0,
        )
    assert v2.id != v1.id
    assert v2.content_hash != v1.content_hash

    # (c) v1 içeriği ve hash'i bit düzeyinde AYNI; hash yeniden hesaplansa da tutuyor.
    definition_after, hash_after = read_v1()
    assert definition_after == definition_before
    assert hash_after == hash_before
    assert content_hash(json.loads(definition_after)) == hash_before

    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant_a)
        total = s.execute(
            text("SELECT count(*) FROM spike_workflow_versions WHERE workflow_key = :k"),
            {"k": "purchase-request"},
        ).scalar_one()
    assert total == 2, "v2 ayrı satır olmalı; v1 üzerine yazılmamalı"
