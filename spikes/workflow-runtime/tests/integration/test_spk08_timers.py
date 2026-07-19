"""SPK-08 — Persisted timer: restart'tan sağ çıkar ve TAM BİR KEZ ateşlenir.

Timer veritabanında yaşar (in-memory scheduler YOK). Fake clock, worker
subprocess'ine `--clock-at` ile enjekte edilir.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime import engine as rt
from spike_runtime.db import set_tenant_context
from spike_runtime.dispatcher import fire_due_timers

from .conftest import T0, SpikeDatabase
from .flow_helpers import publish_v1, scoped_count, start_and_submit

FIRE_AT = T0 + timedelta(seconds=60)
AFTER_FIRE = T0 + timedelta(seconds=120)


def _schedule_reminder(
    app_sf: sessionmaker[Session], tenant: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    v1 = publish_v1(app_sf, tenant, T0)
    flow = start_and_submit(app_sf, tenant, v1.id, 3_000_000, T0)  # onayda bekliyor
    with app_sf() as s, s.begin():
        set_tenant_context(s, tenant)
        timer_id = rt.schedule_timer(
            s,
            tenant_id=tenant,
            instance_id=flow.instance_id,
            purpose="approval.reminder",
            fire_at=FIRE_AT,
            now=T0,
        )
    return flow.instance_id, timer_id


def _run_worker_at(database: SpikeDatabase, clock_at: str, worker_id: str) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "spike_runtime.worker_main",
            "--db-url",
            database.worker_url,
            "--worker-id",
            worker_id,
            "--clock-at",
            clock_at,
        ],
        check=True,
        timeout=60,
        capture_output=True,
    )


def test_timer_survives_restart_and_fires_exactly_once(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    database: SpikeDatabase,
    tenant_a: uuid.UUID,
) -> None:
    _instance_id, timer_id = _schedule_reminder(app_sf, tenant_a)

    # Vadesi gelmeden çalışan worker ateşlemez.
    _run_worker_at(database, T0.isoformat(), "early-worker")
    with worker_sf() as s, s.begin():
        status = s.execute(
            text("SELECT status FROM spike_timers WHERE id = :id"), {"id": str(timer_id)}
        ).scalar_one()
    assert status == "pending"

    # Worker "öldü" (process çıktı). Timer DB'DE yaşıyor. Zaman fake clock ile
    # ilerletilip YENİ worker başlatılır → tam bir kez ateşler + bildirim üretir.
    _run_worker_at(database, AFTER_FIRE.isoformat(), "restarted-worker")
    with worker_sf() as s, s.begin():
        row = s.execute(
            text("SELECT status, fired_at, fired_by FROM spike_timers WHERE id = :id"),
            {"id": str(timer_id)},
        ).one()
    assert row[0] == "fired"
    assert row[2] == "restarted-worker"
    delay_seconds = (row[1] - FIRE_AT).total_seconds()
    assert delay_seconds >= 0, "planlanandan önce ateşlenemez"

    reminders = scoped_count(
        app_sf, tenant_a, "spike_notifications", message_key="approval.reminder"
    )
    assert reminders == 1

    # Aynı fake saatle İKİNCİ restart: ikinci ateşleme YOK.
    _run_worker_at(database, AFTER_FIRE.isoformat(), "third-worker")
    assert (
        scoped_count(app_sf, tenant_a, "spike_notifications", message_key="approval.reminder") == 1
    )


def test_two_workers_cannot_claim_same_timer(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    _schedule_reminder(app_sf, tenant_a)

    with worker_sf() as s1, worker_sf() as s2, s1.begin():
        fired_1 = fire_due_timers(s1, worker_id="w1", now=AFTER_FIRE)
        assert fired_1 == 1
        with s2.begin():  # s1 commit etmeden — satır kilitli
            fired_2 = fire_due_timers(s2, worker_id="w2", now=AFTER_FIRE)
            assert fired_2 == 0, "SKIP LOCKED: aynı timer iki kez claim edilemez"

    with worker_sf() as s, s.begin():
        fired_total = s.execute(
            text("SELECT count(*) FROM spike_timers WHERE status = 'fired'")
        ).scalar_one()
    assert fired_total == 1
