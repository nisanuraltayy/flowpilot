"""Worker composition root — entrypoint.

Modlar:

    python -m flowpilot.worker --check
        Paket importunu ve ayar yüklemesini doğrular; worker loop BAŞLATMAZ. Exit 0.

    python -m flowpilot.worker --run-once --tenant <uuid> [--worker-id NAME]
        Verilen tenant için TEK dispatch turu çalıştırır (timer ateşle → outbox
        claim → idempotent işle), sonra çıkar.

    python -m flowpilot.worker --run --tenant <uuid> --max-passes N [--interval S]
        KONTROLLÜ döngü: en çok N tur, turlar arası S saniye. SIGTERM/SIGINT'te
        graceful durur. `--max-passes 0` sınırsız değildir → reddedilir (sonsuz
        busy loop YASAK; kontrollü bir üst sınır zorunludur).

Kurallar (ADR-003/006/007, .claude/rules): iş mantığı YOK — yalnız application
sınırını (`WorkflowRuntimeService.run_dispatch_pass`) çağırır. BYPASSRLS rolü
kullanmaz (flowpilot_app). Secret/token loglamaz. In-memory timer yoktur.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from collections.abc import Sequence
from types import FrameType
from uuid import UUID

from flowpilot.config.settings import Settings, get_settings
from flowpilot.worker.wiring import build_runtime

CHECK_OK_MESSAGE = "flowpilot.worker check ok"
_LOGGER = logging.getLogger("flowpilot.worker")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowpilot.worker",
        description="FlowPilot worker composition root.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Import + ayar doğrula, çık. Worker loop BAŞLATMAZ.",
    )
    mode.add_argument(
        "--run-once",
        action="store_true",
        help="Tek dispatch turu çalıştır (--tenant zorunlu).",
    )
    mode.add_argument(
        "--run",
        action="store_true",
        help="Kontrollü döngü (--tenant ve --max-passes zorunlu).",
    )
    parser.add_argument("--tenant", type=str, default=None, help="Tenant UUID (dispatch scope).")
    parser.add_argument("--worker-id", type=str, default="workflow-runtime-worker")
    parser.add_argument("--max-passes", type=int, default=1)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def run_check(settings: Settings) -> str:
    """Doğrulama mesajını üretir. Yan etkisi yoktur."""
    return f"{CHECK_OK_MESSAGE} (env={settings.app_environment}, log_level={settings.log_level})"


class _GracefulStop:
    """SIGTERM/SIGINT'te set edilen kontrollü durdurma bayrağı."""

    def __init__(self) -> None:
        self.stopping = False

    def request(self, signum: int, frame: FrameType | None) -> None:
        self.stopping = True


def _log(action: str, **fields: object) -> None:
    # Yalnız correlation alanları; secret/token/kişisel veri LOGLANMAZ.
    _LOGGER.info(json.dumps({"action": action, **{k: str(v) for k, v in fields.items()}}))


def _run_dispatch(
    settings: Settings, *, tenant_id: UUID, worker_id: str, passes: int, interval: float, limit: int
) -> int:
    stop = _GracefulStop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop.request)

    wiring = build_runtime(settings)
    completed = 0
    try:
        for index in range(passes):
            if stop.stopping:
                _log("worker.stop_requested", tenant_id=tenant_id, completed_passes=completed)
                break
            stats = wiring.service.run_dispatch_pass(
                tenant_id=tenant_id, worker_id=worker_id, limit=limit
            )
            completed += 1
            _log(
                "worker.pass",
                tenant_id=tenant_id,
                pass_index=index,
                fired_timers=stats.fired_timers,
                processed=stats.processed,
                duplicate=stats.duplicate,
                retried=stats.retried,
                failed=stats.failed,
            )
            if index + 1 < passes and not stop.stopping:
                _sleep_interruptibly(interval, stop)
    finally:
        wiring.dispose()
    return completed


def _sleep_interruptibly(seconds: float, stop: _GracefulStop) -> None:
    deadline = seconds
    step = 0.05
    waited = 0.0
    while waited < deadline and not stop.stopping:
        time.sleep(min(step, deadline - waited))
        waited += step


def main(argv: Sequence[str] | None = None) -> int:
    """Entrypoint. Başarılıysa 0 döner; argparse hatalı argümanda 2 ile çıkar."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.check:
        print(run_check(settings))  # CLI çıktısı: worker check sonucu
        return 0

    if args.tenant is None:
        parser.error("--run-once/--run için --tenant zorunludur")
    try:
        tenant_id = UUID(args.tenant)
    except ValueError:
        parser.error("--tenant geçerli bir UUID olmalıdır")

    if args.run_once:
        _run_dispatch(
            settings,
            tenant_id=tenant_id,
            worker_id=args.worker_id,
            passes=1,
            interval=0.0,
            limit=args.limit,
        )
        return 0

    # --run: kontrollü döngü; sonsuz busy loop YASAK.
    if args.max_passes < 1:
        parser.error("--run için --max-passes >= 1 olmalıdır (sonsuz loop yasak)")
    _run_dispatch(
        settings,
        tenant_id=tenant_id,
        worker_id=args.worker_id,
        passes=args.max_passes,
        interval=args.interval,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
