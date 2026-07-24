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

        Process-level heartbeat HER ZAMAN açıktır (kapatılamaz): yol
        `WORKER_HEARTBEAT_PATH` ile override edilir, verilmezse default
        `/tmp/flowpilot-worker-heartbeat.json` kullanılır; boş yol reddedilir.
        Heartbeat, yaşam döngüsünü JSON belge olarak yazar (status: starting →
        healthy/degraded → stopping → stopped; pid, started_at, updated_at,
        last_full_success_at, tenant_count, consecutive_failed_sweeps).
        Startup damgası yazılamazsa worker FAIL-FAST eder; sonraki yazım hataları
        loglanır ama dispatch'i DURDURMAZ (dosya bayatlar → healthcheck düşer).

    python -m flowpilot.worker --check-heartbeat
        Container healthcheck modu: heartbeat belgesini doğrular. Exit 0 YALNIZ
        `status == "healthy"` ve `last_full_success_at`,
        `WORKER_HEARTBEAT_MAX_AGE_SECONDS` içinde tazeyse. starting/degraded/
        stopping/stopped, eksik/bozuk/naive/gelecekteki damga → exit 1.
        Worker loop BAŞLATMAZ, database bağlantısı KURMAZ, dosyaya YAZMAZ.

Kurallar (ADR-003/006/007, .claude/rules): iş mantığı YOK — yalnız application
sınırını (`WorkflowRuntimeService.run_dispatch_pass`) çağırır. BYPASSRLS rolü
kullanmaz (flowpilot_app). Secret/token loglamaz. In-memory timer yoktur.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import os
import signal
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from uuid import UUID

from flowpilot.config.settings import Settings, get_settings
from flowpilot.shared.clock import SystemClock
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

# Process-level heartbeat: servis modu yaşam döngüsünü JSON belge olarak yazar;
# `--check-heartbeat` bu belgeyi doğrular. Secret DEĞİLDİR.
# Heartbeat KAPATILAMAZ: yol verilmezse default kullanılır; boş yol REDDEDİLİR.
_HEARTBEAT_PATH_ENV_VAR = "WORKER_HEARTBEAT_PATH"
_HEARTBEAT_MAX_AGE_ENV_VAR = "WORKER_HEARTBEAT_MAX_AGE_SECONDS"
# S108 istisna gerekçesi: sabit /tmp yolu SÖZLEŞMEDİR — container-local, non-root
# kullanıcının yazabildiği geçici yol; atomik yazım + 0o600 izinle korunur.
_DEFAULT_HEARTBEAT_PATH = "/tmp/flowpilot-worker-heartbeat.json"  # noqa: S108
_DEFAULT_HEARTBEAT_MAX_AGE_SECONDS = 60.0
_MIN_HEARTBEAT_MAX_AGE_SECONDS = 1.0
# Saat kayması toleransı: bu kadar saniyeden fazla GELECEKTEKİ damga reddedilir.
_HEARTBEAT_FUTURE_TOLERANCE_SECONDS = 5.0
# İzin verilen yaşam döngüsü durumları. Checker YALNIZ "healthy" için 0 döner.
_HEARTBEAT_STATUSES = frozenset({"starting", "healthy", "degraded", "stopping", "stopped"})


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
    mode.add_argument(
        "--check-heartbeat",
        action="store_true",
        help=(
            f"Heartbeat tazeliğini doğrula, çık (container healthcheck için). "
            f"{_HEARTBEAT_PATH_ENV_VAR} okunur; tazeyse 0, bayat/eksikse 1 döner. "
            "Worker loop BAŞLATMAZ, database bağlantısı KURMAZ."
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


class HeartbeatError(ValueError):
    """Geçersiz heartbeat yapılandırması/belgesi. Mesaj ham değer veya içerik TAŞIMAZ."""


def resolve_heartbeat_path(env_value: str | None) -> str:
    """Heartbeat dosya yolu. Heartbeat KAPATILAMAZ.

    Environment değişkeni yoksa default yol kullanılır. Değişken VAR ama boş/yalnız
    whitespace ise REDDEDİLİR — "boş değer = kapalı" sessiz davranışı yasaktır.
    """
    if env_value is None:
        return _DEFAULT_HEARTBEAT_PATH
    resolved = env_value.strip()
    if not resolved:
        raise HeartbeatError(
            f"{_HEARTBEAT_PATH_ENV_VAR} boş olamaz (heartbeat kapatılamaz): "
            "değişkeni kaldırın veya geçerli bir dosya yolu verin"
        )
    return resolved


def resolve_heartbeat_max_age(env_value: str | None) -> float:
    """Heartbeat tazelik eşiği (saniye). Doğrulanır; yoksa güvenli default."""
    raw = (env_value or "").strip()
    if not raw:
        return _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise HeartbeatError(f"{_HEARTBEAT_MAX_AGE_ENV_VAR} sayısal bir değer olmalıdır") from exc
    if not math.isfinite(parsed):
        raise HeartbeatError(f"{_HEARTBEAT_MAX_AGE_ENV_VAR} sonlu bir sayı olmalıdır")
    if parsed < _MIN_HEARTBEAT_MAX_AGE_SECONDS:
        raise HeartbeatError(
            f"{_HEARTBEAT_MAX_AGE_ENV_VAR} en az {_MIN_HEARTBEAT_MAX_AGE_SECONDS} saniye olmalıdır"
        )
    return parsed


def _format_utc(value: datetime) -> str:
    """UTC ISO-8601, `Z` sonekiyle (ör. 2026-07-24T16:00:05Z)."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _remove_quietly(path: Path) -> None:
    # Temizlik best-effort'tur; asıl hata çağırana zaten yükseltiliyor.
    with contextlib.suppress(OSError):
        path.unlink()


def write_heartbeat_document(path: str, document: dict[str, object]) -> None:
    """Heartbeat belgesini ATOMİK yazar.

    Aynı dizinde geçici dosya → UTF-8 JSON → flush → fsync → `os.replace`.
    POSIX'te dosya izni 0o600'dür. Hata hâlinde geçici dosya temizlenir; yarım
    veya truncate edilmiş JSON asla görünmez. Windows'ta da çalışır.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Geçici dosya HEDEFLE AYNI dizinde: `os.replace` yalnız aynı dosya sisteminde atomiktir.
    temporary = target.with_name(f"{target.name}.tmp")
    payload = json.dumps(document)
    # O_TRUNC + 0o600: yalnız süreç sahibi okur/yazar (POSIX'te; Windows mode'u yok sayar).
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)  # aynı dizin içinde atomik yer değiştirme
    except OSError:
        _remove_quietly(temporary)
        raise


class WorkerHeartbeat:
    """Worker yaşam döngüsü heartbeat'i — durum makinesi + JSON belge yazımı.

    Durumlar: starting → healthy/degraded (sweep başına) → stopping → stopped.

    Belgeye YALNIZ şunlar yazılır: status, pid, started_at, updated_at,
    last_full_success_at, tenant_count, consecutive_failed_sweeps.
    Tenant UUID/listesi, DSN, token, e-posta, raw exception, traceback veya
    environment içeriği ASLA yazılmaz.
    """

    def __init__(self, path: str, *, pid: int, tenant_count: int, started_at: datetime) -> None:
        self._path = path
        self._pid = pid
        self._tenant_count = tenant_count
        self._started_at = started_at
        self._last_full_success_at: datetime | None = None
        self._consecutive_failed_sweeps = 0

    def _document(self, status: str, now: datetime) -> dict[str, object]:
        return {
            "status": status,
            "pid": self._pid,
            "started_at": _format_utc(self._started_at),
            "updated_at": _format_utc(now),
            "last_full_success_at": (
                None
                if self._last_full_success_at is None
                else _format_utc(self._last_full_success_at)
            ),
            "tenant_count": self._tenant_count,
            "consecutive_failed_sweeps": self._consecutive_failed_sweeps,
        }

    def _write_best_effort(self, status: str, now: datetime) -> None:
        # Yazım hatası worker'ı ÖLDÜRMEZ ve busy-retry YAPILMAZ: dosya bayat kalır,
        # container healthcheck'i doğal olarak sağlıksıza döner. Yalnız hata TİPİ loglanır.
        try:
            write_heartbeat_document(self._path, self._document(status, now))
        except Exception as exc:
            _log("worker.heartbeat_write_failed", status=status, error_type=type(exc).__name__)

    def write_starting(self, *, now: datetime) -> None:
        """Startup damgası. Hata YÜKSELTİR — fail-fast kararı çağırana aittir."""
        write_heartbeat_document(self._path, self._document("starting", now))

    def record_sweep(self, failed_tenants: int, *, now: datetime) -> None:
        """Tamamlanmış bir sweep'in sonucunu işler ve damgayı yazar.

        Tam başarı (0 hata) → healthy; `last_full_success_at` güncellenir, sayaç
        sıfırlanır. Kısmi/tam hata → degraded; `last_full_success_at` ÖNCEKİ
        değerinde kalır, sayaç artar. Sürekli başarısız worker bu sayede yalnız
        "yeni dosya yazdığı için" healthy sayılamaz.
        """
        if failed_tenants == 0:
            self._last_full_success_at = now
            self._consecutive_failed_sweeps = 0
            status = "healthy"
        else:
            self._consecutive_failed_sweeps += 1
            status = "degraded"
        self._write_best_effort(status, now)

    def write_stopping(self, *, now: datetime) -> None:
        """Stop talebi işlendi; yeni tenant/sweep başlatılmayacak. Best-effort."""
        self._write_best_effort("stopping", now)

    def write_stopped(self, *, now: datetime) -> None:
        """Runtime dispose tamamlandı. Best-effort; business invariant'a dokunmaz."""
        self._write_best_effort("stopped", now)


def _parse_heartbeat_timestamp(value: object, field: str) -> datetime:
    """Alanın timezone-aware bir timestamp olduğunu doğrular; değeri TEKRAR ETMEZ."""
    if not isinstance(value, str):
        raise HeartbeatError(f"{field} alanı timestamp metni değil")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HeartbeatError(f"{field} alanı geçerli bir timestamp değil") from exc
    if parsed.tzinfo is None:
        raise HeartbeatError(f"{field} alanı timezone-aware değil (naive timestamp reddedilir)")
    return parsed


def _validate_heartbeat_document(path: str, *, max_age_seconds: float, now: datetime) -> float:
    """Checker doğrulaması. Başarıda son tam başarının yaşını (saniye) döner.

    Her ihlal `HeartbeatError` yükseltir; mesaj dosya içeriğini DÖKMEZ.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise HeartbeatError("dosya okunamadı (henüz yazılmamış olabilir)") from exc
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise HeartbeatError("dosya geçerli JSON değil") from exc
    if not isinstance(document, dict):
        raise HeartbeatError("kök öğe JSON object değil")

    status = document.get("status")
    if not isinstance(status, str) or status not in _HEARTBEAT_STATUSES:
        raise HeartbeatError("status alanı bilinmeyen veya eksik")

    pid = document.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise HeartbeatError("pid alanı pozitif integer değil")
    tenant_count = document.get("tenant_count")
    if isinstance(tenant_count, bool) or not isinstance(tenant_count, int | float):
        raise HeartbeatError("tenant_count alanı sayı değil")
    failed_sweeps = document.get("consecutive_failed_sweeps")
    if isinstance(failed_sweeps, bool) or not isinstance(failed_sweeps, int) or failed_sweeps < 0:
        raise HeartbeatError("consecutive_failed_sweeps alanı sıfır/pozitif integer değil")
    _parse_heartbeat_timestamp(document.get("started_at"), "started_at")
    _parse_heartbeat_timestamp(document.get("updated_at"), "updated_at")

    if status != "healthy":
        # starting/degraded/stopping/stopped healthy SAYILMAZ. `updated_at` taze olsa
        # bile sürekli degraded bir worker bu kontrolü geçemez.
        raise HeartbeatError(f"status healthy değil: {status}")

    last_success_raw = document.get("last_full_success_at")
    if last_success_raw is None:
        raise HeartbeatError("last_full_success_at eksik (hiç tam başarılı sweep yok)")
    last_success = _parse_heartbeat_timestamp(last_success_raw, "last_full_success_at")

    age = (now.astimezone(UTC) - last_success.astimezone(UTC)).total_seconds()
    if age < -_HEARTBEAT_FUTURE_TOLERANCE_SECONDS:
        raise HeartbeatError(
            "last_full_success_at izin verilenden fazla gelecekte (saat kayması şüphesi)"
        )
    if age > max_age_seconds:
        raise HeartbeatError(
            f"son tam başarı bayat: yaş {age:.1f}s > izin verilen {max_age_seconds:.1f}s"
        )
    return age


def check_heartbeat(path: str, *, max_age_seconds: float, now: datetime) -> tuple[int, str]:
    """`--check-heartbeat` sonucu: (exit_code, tek satırlık mesaj).

    0 YALNIZ şu durumda döner: dosya okunabilir + geçerli JSON object + alan
    tipleri doğru + `status == "healthy"` + `last_full_success_at` mevcut,
    timezone-aware, en fazla 5 sn gelecekte ve `max_age` içinde taze.
    Worker loop BAŞLATILMAZ, database bağlantısı KURULMAZ, dosyaya YAZILMAZ.
    """
    try:
        age = _validate_heartbeat_document(path, max_age_seconds=max_age_seconds, now=now)
    except HeartbeatError as exc:
        return 1, f"heartbeat sağlıksız: {exc}"
    return 0, (
        f"heartbeat sağlıklı: son tam başarı {age:.1f}s önce (izin verilen {max_age_seconds:.1f}s)"
    )


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
    record_sweep: Callable[[int], None] | None = None,
) -> int:
    """Tenant'lar üzerinde STABİL sıralı sürekli dispatch döngüsü.

    Sıra: allowlist'in İLK GÖRÜLME sırası korunur ve HER sweep aynı sırayı kullanır
    (rotasyon YOKTUR). Sweep sırasında tenant listesi değişmez.

    Adalet: her tenant sweep başına TAM BİR pass alır ve hepsi aynı `limit` ile
    işlenir; yoğun bir tenant diğerini aç bırakamaz.

    Hata izolasyonu: bir tenant'ın pass'i hata verirse loglanır ve döngü DİĞER
    tenant'larla devam eder; tek tenant'ın hatası worker'ı düşürmez, aynı sweep içinde
    tekrar denenmez ve tenant SONRAKİ sweep'te aynı konumunda yeniden denenir.

    Heartbeat: `record_sweep(failed_tenant_count)` yalnız TAMAMLANMIŞ sweep'ler için
    çağrılır. Stop ile yarıda kesilen sweep raporlanmaz — kesilen sweep "tam başarı"
    olarak sayılamaz. `record_sweep` hata yükseltmemekle yükümlüdür (WorkerHeartbeat
    yazım hatasını içeride loglar); izleme, işin kendisini durduramaz.

    `max_cycles` yalnız test/kontrollü çalıştırma içindir; None → durdurulana kadar sürer.
    """
    if not tenant_ids:
        return 0

    # Sweep sırasında listenin değişmemesi için tek seferlik anlık görüntü.
    sweep_order = tuple(tenant_ids)
    cycles = 0
    while not stop.stopping and (max_cycles is None or cycles < max_cycles):
        failed_tenants = 0
        sweep_completed = True
        for tenant_id in sweep_order:
            if stop.stopping:
                sweep_completed = False  # yarım sweep heartbeat'e RAPORLANMAZ
                break
            try:
                dispatch(tenant_id)
            except Exception as exc:
                # Tek tenant hatası worker'ı ÖLDÜRMEZ ve sonraki tenant'ları
                # ENGELLEMEZ; secret/PII loglanmaz.
                failed_tenants += 1
                _log(
                    "worker.tenant_failed",
                    tenant_id=tenant_id,
                    error_type=type(exc).__name__,
                )
        cycles += 1
        if record_sweep is not None and sweep_completed:
            record_sweep(failed_tenants)
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
    heartbeat_path: str,
) -> int:
    """Servis modu: sinyal kaydı + runtime wiring + yaşam döngülü heartbeat + döngü.

    Exit code döner. Lifecycle: wiring kurulduktan sonra `starting` yazılır (bu
    yazım BAŞARISIZSA fail-fast: loop hiç başlamaz, wiring dispose edilir, exit 1).
    Her tamamlanan sweep healthy/degraded üretir. Stop işlendiğinde `stopping`,
    dispose sonrası `stopped` best-effort yazılır — devam eden tenant transaction'ı
    zorla kesilmez, business invariant heartbeat'e bağlanmaz.
    """
    stop = _GracefulStop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop.request)

    clock = SystemClock()
    wiring = build_runtime(settings)
    heartbeat = WorkerHeartbeat(
        heartbeat_path,
        pid=os.getpid(),
        tenant_count=len(tenant_ids),
        started_at=clock.now(),
    )
    try:
        heartbeat.write_starting(now=clock.now())
    except Exception as exc:
        # Kontrollü fail-fast: healthcheck'in hiç çalışamayacağı bir worker sessizce
        # servise girmez. Raw exception/DSN/path içeriği YAZDIRILMAZ.
        wiring.dispose()
        _log("worker.heartbeat_startup_write_failed", error_type=type(exc).__name__)
        print(
            f"worker başlatılamadı: {_HEARTBEAT_PATH_ENV_VAR} yoluna heartbeat yazılamıyor",
            file=sys.stderr,
        )
        return 1

    _log("worker.serve_started", tenant_count=len(tenant_ids), worker_id=worker_id)
    try:
        cycles = _serve_loop(
            tenant_ids=tenant_ids,
            dispatch=lambda tenant_id: wiring.service.run_dispatch_pass(
                tenant_id=tenant_id, worker_id=worker_id, limit=limit
            ),
            stop=stop,
            interval=interval,
            record_sweep=lambda failed: heartbeat.record_sweep(failed, now=clock.now()),
        )
        # Stop işlendi; yeni tenant/sweep başlatılmayacak.
        heartbeat.write_stopping(now=clock.now())
    finally:
        wiring.dispose()
    heartbeat.write_stopped(now=clock.now())
    _log("worker.serve_stopped", completed_cycles=cycles)
    return 0


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

    if args.check_heartbeat:
        try:
            hb_path = resolve_heartbeat_path(os.environ.get(_HEARTBEAT_PATH_ENV_VAR))
            max_age = resolve_heartbeat_max_age(os.environ.get(_HEARTBEAT_MAX_AGE_ENV_VAR))
        except HeartbeatError as exc:
            parser.error(str(exc))
        exit_code, message = check_heartbeat(
            hb_path,
            max_age_seconds=max_age,
            now=SystemClock().now(),
        )
        print(message)  # CLI çıktısı: healthcheck sonucu (dosya içeriği/secret dökülmez)
        return exit_code

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
        try:
            hb_path = resolve_heartbeat_path(os.environ.get(_HEARTBEAT_PATH_ENV_VAR))
        except HeartbeatError as exc:
            parser.error(str(exc))
        return _run_serve(
            settings,
            tenant_ids=tenant_ids,
            worker_id=args.worker_id,
            interval=interval,
            limit=args.limit,
            heartbeat_path=hb_path,
        )

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
