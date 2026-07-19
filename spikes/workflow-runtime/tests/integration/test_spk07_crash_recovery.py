"""SPK-07 — Worker ZORLA öldürülünce süreç kaybolmaz; duplicate de oluşmaz.

Gerçek subprocess + zorla öldürme: Windows'ta `Process.kill()` = TerminateProcess
(SIGKILL eşdeğeri; graceful shutdown DEĞİL).

(a) event outbox'a yazıldı, hiç dispatch edilmedi → restart sonrası işlenir.
(b) claim edildi (lease yazıldı), işlenmeden crash → lease dolunca YENİDEN alınır,
    tek side effect ile tamamlanır.
"""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from .conftest import T0, SpikeDatabase
from .flow_helpers import approve_all, publish_v1, scoped_count, start_and_submit

WORKER_CMD = [sys.executable, "-m", "spike_runtime.worker_main"]


def _worker_url(database: SpikeDatabase) -> str:
    return database.worker_url


def _pending_notification_count(worker_sf: sessionmaker[Session]) -> int:
    with worker_sf() as s, s.begin():
        value = s.execute(
            text(
                "SELECT count(*) FROM spike_outbox_events "
                "WHERE event_type = 'notification.requested.v1' AND status = 'pending'"
            )
        ).scalar_one()
    return int(value)


def _run_worker_once(database: SpikeDatabase, *, worker_id: str) -> None:
    subprocess.run(
        [*WORKER_CMD, "--db-url", _worker_url(database), "--worker-id", worker_id],
        check=True,
        timeout=60,
        capture_output=True,
    )


def test_a_undispatched_event_survives_and_completes(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    database: SpikeDatabase,
    tenant_a: uuid.UUID,
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
    approve_all(app_sf, flow, T0)  # notification.requested outbox'ta, worker YOK

    assert _pending_notification_count(worker_sf) == 1
    _run_worker_once(database, worker_id="restarted-worker")
    assert _pending_notification_count(worker_sf) == 0
    assert (
        scoped_count(app_sf, tenant_a, "spike_notifications", instance_id=str(flow.instance_id))
        == 1
    )


def test_b_sigkill_mid_processing_then_recovery_without_duplicates(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    database: SpikeDatabase,
    tenant_a: uuid.UUID,
    tmp_path: Path,
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)
    flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
    approve_all(app_sf, flow, T0)

    marker = tmp_path / "claimed.marker"
    proc = subprocess.Popen(
        [
            *WORKER_CMD,
            "--db-url",
            _worker_url(database),
            "--worker-id",
            "doomed-worker",
            "--lease-seconds",
            "1",
            "--crash-window-seconds",
            "120",
            "--marker-file",
            str(marker),
            "--max-passes",
            "1",
        ],
    )
    try:
        deadline = time.monotonic() + 60
        while not marker.exists():
            assert time.monotonic() < deadline, "worker claim marker'ı üretmedi"
            assert proc.poll() is None, "worker beklenmedik şekilde erken çıktı"
            time.sleep(0.05)
        # Claim COMMIT edildi; işleme başlamadan ZORLA öldür (TerminateProcess).
        proc.kill()
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()

    # Crash sonrası durum: event hâlâ pending (KAYIP DEĞİL), lease yazılı,
    # side effect üretilmemiş.
    with worker_sf() as s, s.begin():
        row = s.execute(
            text(
                "SELECT status, claimed_by, claim_expires_at FROM spike_outbox_events "
                "WHERE event_type = 'notification.requested.v1'"
            )
        ).one()
    assert row[0] == "pending"
    assert row[1] == "doomed-worker"
    assert row[2] is not None
    assert scoped_count(app_sf, tenant_a, "spike_notifications") == 0

    time.sleep(1.2)  # lease (1 sn) dolsun — süresi dolan claim yeniden alınabilir
    _run_worker_once(database, worker_id="recovery-worker")

    assert _pending_notification_count(worker_sf) == 0, "süreç asılı kalmamalı"
    assert (
        scoped_count(app_sf, tenant_a, "spike_notifications", instance_id=str(flow.instance_id))
        == 1
    ), "restart sonrası TEK side effect (duplicate YOK)"

    # İkinci restart de duplicate üretmez (inbox koruması).
    _run_worker_once(database, worker_id="second-restart")
    assert scoped_count(app_sf, tenant_a, "spike_notifications") == 1
