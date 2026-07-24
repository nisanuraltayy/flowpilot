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

    python -m flowpilot.worker --serve --tenant <uuid> [--tenant <uuid> ...]
        PRODUCTION servis modu: açık tenant allowlist'i üzerinde sürekli dispatch.
        Tenant'lar `--tenant` (tekrarlanabilir) veya `WORKER_TENANT_IDS` (virgülle
        ayrılmış) ile verilir; CLI verilmişse CLI geçerlidir. Hiç tenant yoksa
        kontrollü hata verir (sessizce boş çalışmaz).

        Sıra STABİL ve deterministiktir: allowlist'in ilk görülme sırası korunur ve
        HER sweep aynı sırayı kullanır (rotasyon YOKTUR). Adalet, her tenant'ın sweep
        başına tam bir pass ve aynı `limit` ile işlenmesinden gelir.

        Bir tenant'ın pass'i hata verirse loglanır, döngü diğer tenant'larla DEVAM
        eder ve o tenant SONRAKİ sweep'te aynı konumunda yeniden denenir.

        Sweep sonunda `--interval` beklenir; verilmezse `WORKER_POLL_INTERVAL_SECONDS`,
        o da yoksa güvenli default kullanılır (minimum 0.1 sn; busy-spin yok).
        SIGTERM/SIGINT'te mevcut tenant pass'inden sonra yeni tenant başlatılmaz.

        Worker cross-tenant KEŞİF YAPMAZ: `flowpilot_app` NOBYPASSRLS'tir ve her
        tenant kendi RLS context'inde işlenir.

Kurallar (ADR-003/006/007, .claude/rules): iş mantığı YOK — yalnız application
sınırını (`WorkflowRuntimeService.run_dispatch_pass`) çağırır. BYPASSRLS rolü
kullanmaz (flowpilot_app). Secret/token loglamaz. In-memory timer yoktur.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import sys
import time
from collections.abc import Callable, Sequence
from types import FrameType
from uuid import UUID

from flowpilot.config.settings import Settings, get_settings
from flowpilot.worker.wiring import build_runtime

CHECK_OK_MESSAGE = "flowpilot.worker check ok"
_LOGGER = logging.getLogger("flowpilot.worker")

# Açık tenant allowlist'i. Worker HİÇBİR ayrıcalıklı cross-tenant sorgu yapmaz:
# `flowpilot_app` NOBYPASSRLS'tir ve repository'de güvenli global tenant registry
# YOKTUR. Bu yüzden servis modunda işlenecek tenant'lar AÇIKÇA yapılandırılır.
_TENANT_ENV_VAR = "WORKER_TENANT_IDS"

# Servis modu poll interval sözleşmesi. Secret DEĞİLDİR.
_INTERVAL_ENV_VAR = "WORKER_POLL_INTERVAL_SECONDS"
# Turlar arası en küçük bekleme: busy-spin YASAK.
_MIN_POLL_INTERVAL_SECONDS = 0.1
# CLI ve environment yoksa kullanılan mevcut güvenli default (davranış değişmedi).
_DEFAULT_POLL_INTERVAL_SECONDS = 1.0


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
    mode.add_argument(
        "--serve",
        action="store_true",
        help=(
            "Production servis modu: açık tenant allowlist'i üzerinde STABİL sırayla "
            f"sürekli dispatch. Tenant'lar --tenant (tekrarlanabilir) veya {_TENANT_ENV_VAR} "
            "ile verilir. Her sweep aynı sırayı kullanır; SIGTERM/SIGINT'te graceful durur."
        ),
    )
    parser.add_argument(
        "--tenant",
        action="append",
        default=None,
        metavar="UUID",
        help=(
            "Tenant UUID (dispatch scope). --run-once/--run için TEK değer; "
            "--serve için tekrarlanabilir."
        ),
    )
    parser.add_argument("--worker-id", type=str, default="workflow-runtime-worker")
    parser.add_argument("--max-passes", type=int, default=1)
    # default=None: CLI'da AÇIKÇA verilip verilmediği ayırt edilebilsin (environment
    # fallback'i yalnız verilmediğinde devreye girer). Çözülmüş default ayrı helper'da.
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help=(
            f"Turlar arası bekleme (saniye). Verilmezse --serve icin {_INTERVAL_ENV_VAR}, "
            f"o da yoksa {_DEFAULT_POLL_INTERVAL_SECONDS} kullanılır."
        ),
    )
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


def parse_tenant_allowlist(values: Sequence[str]) -> list[UUID]:
    """Ham tenant değerlerini UUID listesine çevirir (sıra korunur, tekrarlar atılır).

    Geçersiz değer `ValueError` yükseltir; çağıran taraf kontrollü hataya çevirir.
    """
    seen: set[UUID] = set()
    tenants: list[UUID] = []
    for raw in values:
        candidate = raw.strip()
        if not candidate:
            continue
        tenant_id = UUID(candidate)  # geçersizse ValueError
        if tenant_id not in seen:
            seen.add(tenant_id)
            tenants.append(tenant_id)
    return tenants


class IntervalError(ValueError):
    """Geçersiz poll interval. Mesaj yalnız değişken adı + hata KATEGORİSİ taşır."""


def _validate_interval(value: float) -> float:
    """Sonlu ve minimum eşiğin üstünde bir interval döndürür.

    0, negatif, minimum altı, NaN ve infinity REDDEDİLİR. Hata mesajı geçersiz
    DEĞERİ tekrar etmez; yalnız değişken adı ve kategori bildirilir.
    """
    if not math.isfinite(value):
        raise IntervalError(f"{_INTERVAL_ENV_VAR} sonlu bir sayı olmalıdır")
    if value < _MIN_POLL_INTERVAL_SECONDS:
        raise IntervalError(
            f"{_INTERVAL_ENV_VAR} en az {_MIN_POLL_INTERVAL_SECONDS} saniye olmalıdır"
        )
    return value


def resolve_poll_interval(cli_value: float | None, env_value: str | None) -> float:
    """Servis modu poll interval'i: CLI > environment > güvenli default.

    CLI'da `--interval` AÇIKÇA verilmişse o kullanılır (argparse default'u `None`
    olduğu için "verildi mi" ayırt edilebilir). Verilmemişse `WORKER_POLL_INTERVAL_SECONDS`
    okunur. İkisi de yoksa mevcut güvenli default kullanılır. Tüm yollar doğrulanır.
    """
    if cli_value is not None:
        return _validate_interval(cli_value)

    raw = (env_value or "").strip()
    if not raw:
        return _DEFAULT_POLL_INTERVAL_SECONDS

    try:
        parsed = float(raw)
    except ValueError as exc:
        raise IntervalError(f"{_INTERVAL_ENV_VAR} sayısal bir değer olmalıdır") from exc
    return _validate_interval(parsed)


def resolve_serve_tenants(cli_values: Sequence[str] | None, env_value: str | None) -> list[UUID]:
    """Servis modu tenant allowlist'i: CLI verilmişse CLI, aksi hâlde environment.

    CLI ve environment BİRLEŞTİRİLMEZ — hangi kaynağın geçerli olduğu belirsiz kalmasın.
    """
    if cli_values:
        return parse_tenant_allowlist(cli_values)
    raw = (env_value or "").split(",")
    return parse_tenant_allowlist(raw)


def _serve_loop(
    *,
    tenant_ids: Sequence[UUID],
    dispatch: Callable[[UUID], object],
    stop: _GracefulStop,
    interval: float,
    max_cycles: int | None = None,
) -> int:
    """Tenant'lar üzerinde STABİL sıralı sürekli dispatch döngüsü.

    Sıra: allowlist'in İLK GÖRÜLME sırası korunur ve HER sweep aynı sırayı kullanır
    (rotasyon YOKTUR). Sweep sırasında tenant listesi değişmez.

    Adalet: her tenant sweep başına TAM BİR pass alır ve hepsi aynı `limit` ile
    işlenir; yoğun bir tenant diğerini aç bırakamaz.

    Hata izolasyonu: bir tenant'ın pass'i hata verirse loglanır ve döngü DİĞER
    tenant'larla devam eder; tek tenant'ın hatası worker'ı düşürmez, aynı sweep içinde
    tekrar denenmez ve tenant SONRAKİ sweep'te aynı konumunda yeniden denenir.

    `max_cycles` yalnız test/kontrollü çalıştırma içindir; None → durdurulana kadar sürer.
    """
    if not tenant_ids:
        return 0

    # Sweep sırasında listenin değişmemesi için tek seferlik anlık görüntü.
    sweep_order = tuple(tenant_ids)
    cycles = 0
    while not stop.stopping and (max_cycles is None or cycles < max_cycles):
        for tenant_id in sweep_order:
            if stop.stopping:
                break
            try:
                dispatch(tenant_id)
            except Exception as exc:
                # Tek tenant hatası worker'ı ÖLDÜRMEZ; secret/PII loglanmaz.
                _log(
                    "worker.tenant_failed",
                    tenant_id=tenant_id,
                    error_type=type(exc).__name__,
                )
        cycles += 1
        if not stop.stopping and (max_cycles is None or cycles < max_cycles):
            _sleep_interruptibly(interval, stop)
    return cycles


def _run_serve(
    settings: Settings,
    *,
    tenant_ids: Sequence[UUID],
    worker_id: str,
    interval: float,
    limit: int,
) -> int:
    """Servis modu: sinyal kaydı + runtime wiring + adil döngü. Tur sayısını döner."""
    stop = _GracefulStop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop.request)

    wiring = build_runtime(settings)
    _log("worker.serve_started", tenant_count=len(tenant_ids), worker_id=worker_id)
    try:
        cycles = _serve_loop(
            tenant_ids=tenant_ids,
            dispatch=lambda tenant_id: wiring.service.run_dispatch_pass(
                tenant_id=tenant_id, worker_id=worker_id, limit=limit
            ),
            stop=stop,
            interval=interval,
        )
    finally:
        wiring.dispose()
    _log("worker.serve_stopped", completed_cycles=cycles)
    return cycles


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

    if args.serve:
        try:
            tenant_ids = resolve_serve_tenants(args.tenant, os.environ.get(_TENANT_ENV_VAR))
        except ValueError:
            parser.error(f"--tenant/{_TENANT_ENV_VAR} değerleri geçerli UUID olmalıdır")
        if not tenant_ids:
            # Sessizce boş çalışan bir servis YASAK: yapılandırma eksikse kontrollü hata.
            parser.error(
                "--serve için en az bir tenant gerekli: --tenant <uuid> (tekrarlanabilir) "
                f"veya {_TENANT_ENV_VAR}=<uuid[,uuid...]>"
            )
        try:
            interval = resolve_poll_interval(args.interval, os.environ.get(_INTERVAL_ENV_VAR))
        except IntervalError as exc:
            parser.error(str(exc))
        _run_serve(
            settings,
            tenant_ids=tenant_ids,
            worker_id=args.worker_id,
            interval=interval,
            limit=args.limit,
        )
        return 0

    tenants = args.tenant or []
    if not tenants:
        parser.error("--run-once/--run için --tenant zorunludur")
    if len(tenants) > 1:
        parser.error("--run-once/--run tek --tenant kabul eder (çoklu tenant için --serve)")
    try:
        tenant_id = UUID(tenants[0])
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
    # --run interval davranışı DEĞİŞMEDİ: CLI değeri, verilmemişse mevcut default.
    # Environment fallback'i bilinçli olarak YALNIZ --serve içindir.
    _run_dispatch(
        settings,
        tenant_id=tenant_id,
        worker_id=args.worker_id,
        passes=args.max_passes,
        interval=(args.interval if args.interval is not None else _DEFAULT_POLL_INTERVAL_SECONDS),
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
