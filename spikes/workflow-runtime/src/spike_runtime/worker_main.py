"""Crash-recovery testleri için GERÇEK subprocess worker entrypoint'i.

Testler bu process'i başlatır, tam işlem ortasında zorla öldürür (Windows'ta
`TerminateProcess` — SIGKILL eşdeğeri, graceful shutdown DEĞİL) ve yeniden
başlatarak sürecin kayıpsız + duplicate'siz tamamlandığını kanıtlar.

Fake clock: `--clock-at` verilirse tüm turlar o sabit UTC anıyla çalışır
(timer'ların restart sonrası "zaman ilerletilmiş" senaryosu için).
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spike_runtime.dispatcher import claim_events, mark_failed_attempt, process_claimed, run_pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="spike outbox/timer worker (GEÇİCİ)")
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--worker-id", default="spike-worker-proc")
    parser.add_argument("--clock-at", default=None, help="ISO UTC fake clock (opsiyonel)")
    parser.add_argument("--lease-seconds", type=float, default=2.0)
    parser.add_argument("--max-passes", type=int, default=1, help="0 = sınırsız döngü")
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument(
        "--crash-window-seconds",
        type=float,
        default=0.0,
        help="claim COMMIT edildikten sonra, işleme başlamadan önce bekleme "
        "(test bu pencerede process'i öldürür)",
    )
    parser.add_argument(
        "--marker-file",
        default=None,
        help="ilk claim commit edildiğinde dokunulan dosya (test senkronizasyonu)",
    )
    args = parser.parse_args(argv)

    fixed_clock = datetime.fromisoformat(args.clock_at).astimezone(UTC) if args.clock_at else None
    engine = create_engine(args.db_url)
    session_factory = sessionmaker(bind=engine)

    passes = 0
    try:
        while args.max_passes == 0 or passes < args.max_passes:
            passes += 1
            now = fixed_clock or datetime.now(UTC)
            if args.crash_window_seconds > 0:
                # Crash senaryosu: claim'i AYRI transaction'da commit'le,
                # sonra işlemeden önce pencere aç (test burada öldürür).
                with session_factory() as session, session.begin():
                    claimed = claim_events(
                        session,
                        worker_id=args.worker_id,
                        now=now,
                        lease_seconds=args.lease_seconds,
                    )
                if claimed and args.marker_file:
                    Path(args.marker_file).touch()
                if claimed:
                    time.sleep(args.crash_window_seconds)
                for event in claimed:
                    try:
                        with session_factory() as session, session.begin():
                            process_claimed(session, event, now=now)
                    except Exception as exc:  # worker tek event hatasıyla ölmez
                        with session_factory() as session, session.begin():
                            mark_failed_attempt(session, event, now=now, error=repr(exc))
            else:
                run_pass(
                    session_factory,
                    worker_id=args.worker_id,
                    now=now,
                    lease_seconds=args.lease_seconds,
                )
            if args.max_passes == 0 or passes < args.max_passes:
                time.sleep(args.poll_interval)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
