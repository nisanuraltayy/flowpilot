"""Temel benchmark — performans ürünü DEĞİL; kaba büyüklük ölçümü.

Ölçümler monotonic clock ile yapılır (wall-clock değil) ve rapor için stdout'a
yazılır. Production kapasite iddiası YOKTUR: local Docker + Testcontainers +
tek makine ortamıdır.
"""

from __future__ import annotations

import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from spike_runtime.dispatcher import claim_events, run_pass

from .conftest import T0
from .flow_helpers import approve_step, publish_v1, start_and_submit

INSTANCE_COUNT = 100


def test_benchmark_and_report(
    app_sf: sessionmaker[Session],
    worker_sf: sessionmaker[Session],
    tenant_a: uuid.UUID,
) -> None:
    v1 = publish_v1(app_sf, tenant_a, T0)

    # 1) Tek instance başlatma + form gönderimi (uçtan uca komut süresi).
    single_start = time.perf_counter()
    warm = start_and_submit(app_sf, tenant_a, v1.id, 3_000_000, T0)
    single_ms = (time.perf_counter() - single_start) * 1000

    # 2) Tek approval transition.
    t = time.perf_counter()
    approve_step(app_sf, warm, 0, T0)
    approval_ms = (time.perf_counter() - t) * 1000

    # 3) INSTANCE_COUNT küçük instance uçtan uca (düşük bant → tek onay).
    durations: list[float] = []
    batch_start = time.perf_counter()
    for _ in range(INSTANCE_COUNT):
        t = time.perf_counter()
        flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
        approve_step(app_sf, flow, 0, T0)
        durations.append((time.perf_counter() - t) * 1000)
    batch_seconds = time.perf_counter() - batch_start

    # Kuyruğu worker ile boşalt (bildirim side effect'leri dahil).
    worker_start = time.perf_counter()
    total_processed = 0
    while True:
        stats = run_pass(worker_sf, worker_id="bench", now=datetime.now(UTC), limit=200)
        total_processed += stats["processed"]
        if stats["processed"] == 0 and stats["duplicate"] == 0:
            break
    worker_seconds = time.perf_counter() - worker_start

    # 4) Eşzamanlı claim: iki worker aynı kuyruğu SKIP LOCKED ile paylaşır.
    #    Yeni event'ler üret (her akış birden çok outbox event'i emit eder).
    for _ in range(20):
        flow = start_and_submit(app_sf, tenant_a, v1.id, 500_000, T0)
        approve_step(app_sf, flow, 0, T0)

    with worker_sf() as s, s.begin():
        pending_before = int(
            s.execute(
                text("SELECT count(*) FROM spike_outbox_events WHERE status = 'pending'")
            ).scalar_one()
        )
    assert pending_before >= 20

    def claim_batch(worker_id: str) -> int:
        with worker_sf() as s, s.begin():
            return len(claim_events(s, worker_id=worker_id, now=datetime.now(UTC), limit=1000))

    t = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(claim_batch, ["c1", "c2"]))
    concurrent_claim_ms = (time.perf_counter() - t) * 1000

    # SKIP LOCKED kanıtı: iki worker birlikte her pending event'i TAM BİR KEZ aldı;
    # hiçbir event iki worker tarafından da claim edilmedi.
    assert sum(counts) == pending_before, "her pending event tam bir kez claim edilmeli"

    p50 = statistics.median(durations)
    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
    print("\n=== SPIKE BENCHMARK (local Docker, Testcontainers PostgreSQL 17) ===")
    print(f"tek instance start+form_submit           : {single_ms:8.1f} ms")
    print(f"tek approval transition (komut siniri)   : {approval_ms:8.1f} ms")
    print(
        f"{INSTANCE_COUNT} instance uctan uca (start->onay)     : "
        f"{batch_seconds:8.2f} s  (p50 {p50:.1f} ms, p95 {p95:.1f} ms/instance)"
    )
    print(f"worker kuyruk bosaltma ({total_processed:3d} event)   : {worker_seconds:8.2f} s")
    print(
        f"eszamanli claim (2 worker, {pending_before:3d} event)  : "
        f"{concurrent_claim_ms:8.1f} ms  (c1={counts[0]}, c2={counts[1]})"
    )

    assert total_processed >= INSTANCE_COUNT, "her instance en az bir bildirim üretmeli"
