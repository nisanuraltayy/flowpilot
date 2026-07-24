"""Worker entrypoint testleri.

`--check` gerçek worker döngüsünü başlatmaz; yalnız import ve ayar yüklemesini
doğrular. Network, Docker veya PostgreSQL GEREKTİRMEZ.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

import flowpilot.worker.__main__ as worker_main
from flowpilot.config.settings import Settings
from flowpilot.worker.__main__ import (
    _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS,
    _DEFAULT_HEARTBEAT_PATH,
    _DEFAULT_POLL_INTERVAL_SECONDS,
    _HEARTBEAT_MAX_AGE_ENV_VAR,
    _HEARTBEAT_PATH_ENV_VAR,
    CHECK_OK_MESSAGE,
    HeartbeatError,
    IntervalError,
    WorkerHeartbeat,
    _GracefulStop,
    _run_serve,
    _serve_loop,
    check_heartbeat,
    main,
    parse_tenant_allowlist,
    resolve_heartbeat_max_age,
    resolve_heartbeat_path,
    resolve_poll_interval,
    resolve_serve_tenants,
    write_heartbeat_document,
)

_T1 = "00000000-0000-0000-0000-000000000001"
_T2 = "00000000-0000-0000-0000-000000000002"
_T3 = "00000000-0000-0000-0000-000000000003"


def test_check_returns_exit_code_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--check"])

    assert exit_code == 0
    assert CHECK_OK_MESSAGE in capsys.readouterr().out


def test_check_reports_environment(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--check"])

    out = capsys.readouterr().out
    assert "env=" in out
    assert "log_level=" in out


def test_unknown_argument_fails_in_controlled_way(capsys: pytest.CaptureFixture[str]) -> None:
    # Geçerli --check ile birlikte bilinmeyen argüman: argparse SystemExit(2) ile
    # çıkar, kullanım mesajı yazar ve worker loop BAŞLATMAZ.
    with pytest.raises(SystemExit) as exc_info:
        main(["--check", "--run-forever"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "unrecognized arguments: --run-forever" in captured.err
    assert CHECK_OK_MESSAGE not in captured.out


def test_missing_mode_flag_fails_in_controlled_way(capsys: pytest.CaptureFixture[str]) -> None:
    # Mod seçilmeden çağrı kontrollü reddedilir
    # (--check / --run-once / --run / --serve birinden biri).
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert (
        "one of the arguments --check --run-once --run --serve --check-heartbeat is required"
        in captured.err
    )
    assert CHECK_OK_MESSAGE not in captured.out


def test_modes_are_mutually_exclusive(capsys: pytest.CaptureFixture[str]) -> None:
    # --serve mevcut modlarla birlikte kullanılamaz.
    with pytest.raises(SystemExit) as exc_info:
        main(["--check", "--serve"])

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_run_once_requires_tenant(capsys: pytest.CaptureFixture[str]) -> None:
    # --run-once --tenant olmadan: kontrollü hata, worker loop BAŞLATMAZ.
    with pytest.raises(SystemExit) as exc_info:
        main(["--run-once"])

    assert exc_info.value.code == 2
    assert "--tenant zorunludur" in capsys.readouterr().err


def test_run_rejects_unbounded_loop(capsys: pytest.CaptureFixture[str]) -> None:
    # Sonsuz busy loop YASAK: --run --max-passes 0 reddedilir.
    tenant = "00000000-0000-0000-0000-000000000001"
    with pytest.raises(SystemExit) as exc_info:
        main(["--run", "--tenant", tenant, "--max-passes", "0"])

    assert exc_info.value.code == 2
    assert "sonsuz loop yasak" in capsys.readouterr().err


def test_run_rejects_multiple_tenants(capsys: pytest.CaptureFixture[str]) -> None:
    # Mevcut tek-tenant semantiği korunur: --run/--run-once çoklu tenant KABUL ETMEZ.
    with pytest.raises(SystemExit) as exc_info:
        main(["--run-once", "--tenant", _T1, "--tenant", _T2])

    assert exc_info.value.code == 2
    assert "tek --tenant kabul eder" in capsys.readouterr().err


# ------------------------------------------------------- --serve: CLI sözleşmesi


def test_serve_requires_at_least_one_tenant(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sessizce boş çalışan servis YASAK: tenant yoksa kontrollü hata.
    monkeypatch.delenv("WORKER_TENANT_IDS", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["--serve"])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "--serve için en az bir tenant gerekli" in captured.err
    assert "WORKER_TENANT_IDS" in captured.err


def test_serve_rejects_invalid_tenant_uuid(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WORKER_TENANT_IDS", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main(["--serve", "--tenant", "not-a-uuid"])

    assert exc_info.value.code == 2
    assert "geçerli UUID olmalıdır" in capsys.readouterr().err


# --------------------------------------------------- tenant allowlist çözümlemesi


def test_allowlist_parses_and_deduplicates_preserving_order() -> None:
    tenants = parse_tenant_allowlist([_T2, _T1, _T2, "  ", _T1])

    assert tenants == [UUID(_T2), UUID(_T1)]


def test_allowlist_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError):
        parse_tenant_allowlist(["not-a-uuid"])


def test_serve_tenants_prefer_cli_over_environment() -> None:
    # CLI ve environment BİRLEŞTİRİLMEZ; CLI verilmişse CLI geçerlidir.
    resolved = resolve_serve_tenants([_T1], f"{_T2},{_T3}")

    assert resolved == [UUID(_T1)]


def test_serve_tenants_fall_back_to_environment() -> None:
    resolved = resolve_serve_tenants(None, f" {_T1} , {_T2} ")

    assert resolved == [UUID(_T1), UUID(_T2)]


def test_serve_tenants_empty_environment_yields_empty_list() -> None:
    assert resolve_serve_tenants(None, "") == []
    assert resolve_serve_tenants(None, None) == []


# ------------------------------------------------------ adil döngü / hata izolasyonu


def test_serve_loop_processes_every_tenant_each_cycle() -> None:
    seen: list[UUID] = []
    stop = _GracefulStop()

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2), UUID(_T3)],
        dispatch=seen.append,
        stop=stop,
        interval=0.0,
        max_cycles=2,
    )

    assert cycles == 2
    # Her tur her tenant TAM BİR KEZ işlenir (açlık yok).
    assert len(seen) == 6
    assert {seen.count(UUID(t)) for t in (_T1, _T2, _T3)} == {2}


def test_serve_loop_uses_stable_order_every_sweep() -> None:
    """Sıra STABİL: her sweep ilk görülme sırasını kullanır (rotasyon YOK)."""
    seen: list[UUID] = []
    order = [UUID(_T1), UUID(_T2), UUID(_T3)]

    _serve_loop(
        tenant_ids=order,
        dispatch=seen.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=3,
    )

    assert seen[0:3] == order  # sweep 1: A, B, C
    assert seen[3:6] == order  # sweep 2: A, B, C
    assert seen[6:9] == order  # sweep 3: A, B, C


def test_serve_loop_order_follows_first_seen_after_dedupe() -> None:
    """Duplicate'ler deterministik biçimde kaldırılır ve sweep sırası bunu izler."""
    tenants = parse_tenant_allowlist([_T3, _T1, _T3, _T2, _T1])
    seen: list[UUID] = []

    _serve_loop(
        tenant_ids=tenants,
        dispatch=seen.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    assert tenants == [UUID(_T3), UUID(_T1), UUID(_T2)]
    assert seen == tenants * 2


def test_serve_loop_keeps_stable_order_despite_failing_tenant() -> None:
    """Hatalı tenant sırayı bozmaz ve SONRAKİ sweep'te aynı konumda yeniden denenir."""
    attempted: list[UUID] = []
    failing = UUID(_T2)

    def dispatch(tenant_id: UUID) -> None:
        attempted.append(tenant_id)
        if tenant_id == failing:
            raise RuntimeError("tenant dispatch exploded")

    _serve_loop(
        tenant_ids=[UUID(_T1), failing, UUID(_T3)],
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    expected = [UUID(_T1), failing, UUID(_T3)]
    assert attempted[0:3] == expected  # hataya rağmen sonraki tenant aynı sırada
    assert attempted[3:6] == expected  # hatalı tenant aynı konumda yeniden denendi


def test_serve_loop_snapshots_tenant_list_for_the_sweep() -> None:
    """Sweep sırasında listenin sonradan değişmesi o sweep'i etkilemez."""
    tenants = [UUID(_T1), UUID(_T2)]
    seen: list[UUID] = []

    def dispatch(tenant_id: UUID) -> None:
        seen.append(tenant_id)
        tenants.append(UUID(_T3))  # çalışırken listeyi büyüt

    _serve_loop(
        tenant_ids=tenants,
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    assert seen == [UUID(_T1), UUID(_T2), UUID(_T1), UUID(_T2)]


# --------------------------------------------------------- poll interval sözleşmesi


def test_interval_cli_overrides_environment() -> None:
    assert resolve_poll_interval(2.5, "7.5") == 2.5


def test_interval_falls_back_to_environment() -> None:
    assert resolve_poll_interval(None, "7.5") == 7.5


def test_interval_uses_default_when_cli_and_environment_absent() -> None:
    assert resolve_poll_interval(None, None) == _DEFAULT_POLL_INTERVAL_SECONDS
    assert resolve_poll_interval(None, "") == _DEFAULT_POLL_INTERVAL_SECONDS
    assert resolve_poll_interval(None, "   ") == _DEFAULT_POLL_INTERVAL_SECONDS


def test_interval_accepts_minimum_value() -> None:
    assert resolve_poll_interval(None, "0.1") == 0.1
    assert resolve_poll_interval(0.1, None) == 0.1


@pytest.mark.parametrize("raw", ["0", "-1", "-0.5", "0.09", "nan", "inf", "-inf", "abc", "1,5"])
def test_interval_rejects_invalid_environment_values(raw: str) -> None:
    with pytest.raises(IntervalError):
        resolve_poll_interval(None, raw)


@pytest.mark.parametrize("value", [0.0, -1.0, 0.09, float("nan"), float("inf")])
def test_interval_rejects_invalid_cli_values(value: float) -> None:
    with pytest.raises(IntervalError):
        resolve_poll_interval(value, None)


def test_interval_error_message_names_variable_without_leaking_value() -> None:
    """Mesaj yalnız değişken adı + kategori taşır; geçersiz değeri tekrar etmez."""
    with pytest.raises(IntervalError) as exc_info:
        resolve_poll_interval(None, "super-secret-typo-value")

    message = str(exc_info.value)
    assert "WORKER_POLL_INTERVAL_SECONDS" in message
    assert "super-secret-typo-value" not in message


def test_serve_rejects_invalid_interval_environment(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "0")
    with pytest.raises(SystemExit) as exc_info:
        main(["--serve", "--tenant", _T1])

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "WORKER_POLL_INTERVAL_SECONDS" in captured.err
    assert "WORKER_TENANT_IDS" not in captured.err  # ilgisiz environment içeriği taşımaz


def test_serve_loop_isolates_failing_tenant() -> None:
    processed: list[UUID] = []
    failing = UUID(_T1)

    def dispatch(tenant_id: UUID) -> None:
        if tenant_id == failing:
            raise RuntimeError("tenant dispatch exploded")
        processed.append(tenant_id)

    cycles = _serve_loop(
        tenant_ids=[failing, UUID(_T2), UUID(_T3)],
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    # Bir tenant sürekli hata verse bile döngü DEVAM eder ve diğerleri işlenir.
    assert cycles == 2
    assert processed.count(UUID(_T2)) == 2
    assert processed.count(UUID(_T3)) == 2


def test_serve_loop_stops_gracefully_between_tenants() -> None:
    stop = _GracefulStop()
    seen: list[UUID] = []

    def dispatch(tenant_id: UUID) -> None:
        seen.append(tenant_id)
        stop.request(15, None)  # ilk tenant'tan sonra durdurma iste

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2), UUID(_T3)],
        dispatch=dispatch,
        stop=stop,
        interval=0.0,
        max_cycles=None,  # sınırsız: yalnız stop sinyaliyle biter
    )

    assert seen == [UUID(_T1)]  # durdurma isteği tur ortasında saygı görür
    assert cycles == 1


def test_serve_loop_with_no_tenants_does_nothing() -> None:
    assert (
        _serve_loop(tenant_ids=[], dispatch=lambda _: None, stop=_GracefulStop(), interval=0.0) == 0
    )


# ------------------------------------------------------- heartbeat yapılandırması

_NOW = datetime(2026, 7, 24, 10, 0, 0, tzinfo=UTC)


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def test_heartbeat_path_uses_default_when_env_is_unset() -> None:
    """Heartbeat KAPATILAMAZ: değişken yoksa default yol kullanılır."""
    assert resolve_heartbeat_path(None) == _DEFAULT_HEARTBEAT_PATH
    assert _DEFAULT_HEARTBEAT_PATH == "/tmp/flowpilot-worker-heartbeat.json"  # noqa: S108


def test_heartbeat_path_env_overrides_default() -> None:
    assert resolve_heartbeat_path("/var/run/hb.json") == "/var/run/hb.json"
    assert resolve_heartbeat_path("  /var/run/hb.json  ") == "/var/run/hb.json"


@pytest.mark.parametrize("raw", ["", "   ", "\t"])
def test_heartbeat_path_rejects_blank_value(raw: str) -> None:
    """Boş değer 'heartbeat kapalı' anlamına GELMEZ; açıkça reddedilir."""
    with pytest.raises(HeartbeatError) as excinfo:
        resolve_heartbeat_path(raw)

    assert _HEARTBEAT_PATH_ENV_VAR in str(excinfo.value)


def test_heartbeat_max_age_uses_default_when_absent() -> None:
    assert resolve_heartbeat_max_age(None) == _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
    assert resolve_heartbeat_max_age("  ") == _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS
    assert _DEFAULT_HEARTBEAT_MAX_AGE_SECONDS == 60.0


def test_heartbeat_max_age_accepts_minimum_value() -> None:
    assert resolve_heartbeat_max_age("1.0") == 1.0
    assert resolve_heartbeat_max_age("15") == 15.0


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "0.99", "nan", "inf", "-inf"])
def test_heartbeat_max_age_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(HeartbeatError):
        resolve_heartbeat_max_age(raw)


def test_heartbeat_max_age_error_names_variable_without_leaking_value() -> None:
    with pytest.raises(HeartbeatError) as excinfo:
        resolve_heartbeat_max_age("gizli-deger")

    assert _HEARTBEAT_MAX_AGE_ENV_VAR in str(excinfo.value)
    assert "gizli-deger" not in str(excinfo.value)


# ------------------------------------------------------------ JSON heartbeat modeli


def _heartbeat(tmp_path: Path, *, tenant_count: int = 3) -> tuple[WorkerHeartbeat, Path]:
    target = tmp_path / "hb.json"
    heartbeat = WorkerHeartbeat(str(target), pid=123, tenant_count=tenant_count, started_at=_NOW)
    return heartbeat, target


def _read_doc(target: Path) -> dict[str, object]:
    document = json.loads(target.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_starting_heartbeat_contains_all_contract_fields(tmp_path: Path) -> None:
    heartbeat, target = _heartbeat(tmp_path)

    heartbeat.write_starting(now=_NOW + timedelta(seconds=1))

    document = _read_doc(target)
    assert set(document) == {
        "status",
        "pid",
        "started_at",
        "updated_at",
        "last_full_success_at",
        "tenant_count",
        "consecutive_failed_sweeps",
    }
    assert document["status"] == "starting"
    assert document["pid"] == 123
    assert document["started_at"] == "2026-07-24T10:00:00Z"  # UTC + Z suffix
    assert document["updated_at"] == "2026-07-24T10:00:01Z"
    assert document["last_full_success_at"] is None  # hiç tam başarı yok
    assert document["tenant_count"] == 3
    assert document["consecutive_failed_sweeps"] == 0


def test_heartbeat_document_contains_no_tenant_ids_or_secret_like_content(
    tmp_path: Path,
) -> None:
    """Belge yalnız sayısal tenant SAYISI taşır; UUID/DSN/token benzeri içerik taşımaz."""
    heartbeat, target = _heartbeat(tmp_path)

    heartbeat.write_starting(now=_NOW)
    heartbeat.record_sweep(0, now=_NOW)

    raw = target.read_text(encoding="utf-8")
    assert _T1 not in raw and _T2 not in raw
    assert "postgresql" not in raw.lower()
    assert "traceback" not in raw.lower()
    assert "authorization" not in raw.lower()
    assert isinstance(_read_doc(target)["tenant_count"], int)


def test_heartbeat_write_is_atomic_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    heartbeat, _ = _heartbeat(tmp_path)

    heartbeat.write_starting(now=_NOW)

    assert [entry.name for entry in tmp_path.iterdir()] == ["hb.json"]


def test_heartbeat_write_sets_owner_only_permission_on_posix(tmp_path: Path) -> None:
    target = tmp_path / "hb.json"

    write_heartbeat_document(str(target), {"status": "starting"})

    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    else:  # Windows: POSIX izin biti yok; en azından dosya yazılmış olmalı
        assert target.is_file()


def test_heartbeat_write_cleans_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "hb.json"

    def _broken_replace(src: object, dst: object) -> None:
        raise OSError("replace patladı")

    monkeypatch.setattr(worker_main.os, "replace", _broken_replace)
    with pytest.raises(OSError):
        write_heartbeat_document(str(target), {"status": "starting"})

    # Yarım/geçici dosya BIRAKILMAZ.
    assert list(tmp_path.iterdir()) == []


def test_heartbeat_write_creates_missing_parent_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "hb.json"

    write_heartbeat_document(str(target), {"status": "starting"})

    assert target.is_file()


# --------------------------------------------------------- heartbeat yaşam döngüsü


def test_first_full_success_transitions_starting_to_healthy(tmp_path: Path) -> None:
    heartbeat, target = _heartbeat(tmp_path)
    heartbeat.write_starting(now=_NOW)

    success_at = _NOW + timedelta(seconds=2)
    heartbeat.record_sweep(0, now=success_at)

    document = _read_doc(target)
    assert document["status"] == "healthy"
    assert document["last_full_success_at"] == _fmt(success_at)
    assert document["updated_at"] == _fmt(success_at)
    assert document["consecutive_failed_sweeps"] == 0


def test_partial_failure_marks_degraded_and_preserves_last_full_success(
    tmp_path: Path,
) -> None:
    heartbeat, target = _heartbeat(tmp_path)
    heartbeat.write_starting(now=_NOW)
    success_at = _NOW + timedelta(seconds=2)
    heartbeat.record_sweep(0, now=success_at)

    heartbeat.record_sweep(1, now=_NOW + timedelta(seconds=4))

    document = _read_doc(target)
    assert document["status"] == "degraded"
    # Önceki tam başarı DEĞİŞMEZ: sürekli başarısız worker taze görünemez.
    assert document["last_full_success_at"] == _fmt(success_at)
    assert document["consecutive_failed_sweeps"] == 1


def test_consecutive_failures_increment_counter(tmp_path: Path) -> None:
    heartbeat, target = _heartbeat(tmp_path)
    heartbeat.write_starting(now=_NOW)

    heartbeat.record_sweep(2, now=_NOW + timedelta(seconds=1))
    heartbeat.record_sweep(1, now=_NOW + timedelta(seconds=2))

    document = _read_doc(target)
    assert document["consecutive_failed_sweeps"] == 2
    assert document["last_full_success_at"] is None  # hiç tam başarı olmadı


def test_full_success_resets_failure_counter(tmp_path: Path) -> None:
    heartbeat, target = _heartbeat(tmp_path)
    heartbeat.write_starting(now=_NOW)
    heartbeat.record_sweep(1, now=_NOW + timedelta(seconds=1))
    heartbeat.record_sweep(1, now=_NOW + timedelta(seconds=2))

    recovered_at = _NOW + timedelta(seconds=3)
    heartbeat.record_sweep(0, now=recovered_at)

    document = _read_doc(target)
    assert document["status"] == "healthy"
    assert document["consecutive_failed_sweeps"] == 0
    assert document["last_full_success_at"] == _fmt(recovered_at)


def test_stopping_and_stopped_statuses_are_written(tmp_path: Path) -> None:
    heartbeat, target = _heartbeat(tmp_path)
    heartbeat.write_starting(now=_NOW)

    heartbeat.write_stopping(now=_NOW + timedelta(seconds=1))
    assert _read_doc(target)["status"] == "stopping"

    heartbeat.write_stopped(now=_NOW + timedelta(seconds=2))
    assert _read_doc(target)["status"] == "stopped"


def test_runtime_write_failure_does_not_raise_or_leak_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sweep sonrası yazım hatası worker'ı düşürmez; raw exception loglanmaz."""
    heartbeat, _ = _heartbeat(tmp_path)
    logged: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        worker_main, "_log", lambda action, **fields: logged.append((action, fields))
    )

    def _broken_write(path: str, document: dict[str, object]) -> None:
        raise OSError("disk dolu: /gizli/yol postgresql://user:pw@db/x")

    monkeypatch.setattr(worker_main, "write_heartbeat_document", _broken_write)
    heartbeat.record_sweep(0, now=_NOW)  # exception YÜKSELTMEZ

    assert [action for action, _ in logged] == ["worker.heartbeat_write_failed"]
    flattened = json.dumps(logged)
    assert "disk dolu" not in flattened  # raw exception mesajı LOGLANMAZ
    assert "postgresql" not in flattened
    assert logged[0][1]["error_type"] == "OSError"  # yalnız hata TİPİ loglanır


# ------------------------------------------------ heartbeat servis loop entegrasyonu


def test_serve_loop_reports_failed_tenant_count_per_completed_sweep() -> None:
    failing = UUID(_T1)
    reported: list[int] = []

    def dispatch(tenant_id: UUID) -> None:
        if tenant_id == failing:
            raise RuntimeError("tenant dispatch exploded")

    _serve_loop(
        tenant_ids=[failing, UUID(_T2), UUID(_T3)],
        dispatch=dispatch,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
        record_sweep=reported.append,
    )

    # Hata sonraki tenant'ları ENGELLEMEZ ve her sweep hatalı tenant SAYISINI raporlar.
    assert reported == [1, 1]


def test_serve_loop_reports_zero_failures_on_full_success() -> None:
    reported: list[int] = []

    _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2)],
        dispatch=lambda _: None,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
        record_sweep=reported.append,
    )

    assert reported == [0, 0]


def test_serve_loop_does_not_report_interrupted_sweep() -> None:
    """Stop ile yarıda kesilen sweep 'tam başarı' olarak RAPORLANAMAZ."""
    stop = _GracefulStop()
    reported: list[int] = []

    def dispatch(tenant_id: UUID) -> None:
        stop.request(15, None)  # ilk tenant'tan sonra durdurma iste

    _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2)],
        dispatch=dispatch,
        stop=stop,
        interval=0.0,
        max_cycles=None,
        record_sweep=reported.append,
    )

    assert reported == []


def test_serve_loop_reports_sweep_completed_by_final_tenant() -> None:
    """Stop SON tenant'tan sonra geldiyse sweep tamamlanmıştır ve raporlanır."""
    stop = _GracefulStop()
    reported: list[int] = []

    def dispatch(tenant_id: UUID) -> None:
        stop.request(15, None)

    _serve_loop(
        tenant_ids=[UUID(_T1)],
        dispatch=dispatch,
        stop=stop,
        interval=0.0,
        max_cycles=None,
        record_sweep=reported.append,
    )

    assert reported == [0]


def test_serve_loop_runs_unchanged_when_record_sweep_is_not_given() -> None:
    """Heartbeat callback'i opsiyoneldir: verilmezse döngü davranışı DEĞİŞMEZ."""
    processed: list[UUID] = []

    cycles = _serve_loop(
        tenant_ids=[UUID(_T1), UUID(_T2)],
        dispatch=processed.append,
        stop=_GracefulStop(),
        interval=0.0,
        max_cycles=2,
    )

    assert cycles == 2
    assert len(processed) == 4


# ----------------------------------------------------------- _run_serve yaşam döngüsü


class _FakeService:
    def __init__(self) -> None:
        self.calls = 0

    def run_dispatch_pass(self, **kwargs: object) -> None:
        self.calls += 1


class _FakeWiring:
    def __init__(self) -> None:
        self.disposed = False
        self.service = _FakeService()

    def dispose(self) -> None:
        self.disposed = True


def _test_settings() -> Settings:
    return Settings(_env_file=None, app_environment="test")


def test_run_serve_writes_full_lifecycle_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """starting → healthy/degraded → stopping → stopped sırası ve dispose garantisi."""
    wiring = _FakeWiring()
    monkeypatch.setattr(worker_main, "build_runtime", lambda settings: wiring)

    statuses: list[object] = []
    original_write = worker_main.write_heartbeat_document

    def _recording_write(path: str, document: dict[str, object]) -> None:
        statuses.append(document["status"])
        original_write(path, document)

    monkeypatch.setattr(worker_main, "write_heartbeat_document", _recording_write)

    def _fake_loop(
        *,
        tenant_ids: object,
        dispatch: object,
        stop: object,
        interval: object,
        record_sweep: Callable[[int], None],
        max_cycles: object = None,
    ) -> int:
        record_sweep(0)
        record_sweep(1)
        return 2

    monkeypatch.setattr(worker_main, "_serve_loop", _fake_loop)

    target = tmp_path / "hb.json"
    exit_code = _run_serve(
        _test_settings(),
        tenant_ids=[UUID(_T1), UUID(_T2)],
        worker_id="w",
        interval=1.0,
        limit=5,
        heartbeat_path=str(target),
    )

    assert exit_code == 0
    assert statuses == ["starting", "healthy", "degraded", "stopping", "stopped"]
    assert wiring.disposed
    final = json.loads(target.read_text(encoding="utf-8"))
    assert final["status"] == "stopped"
    assert final["tenant_count"] == 2


def test_run_serve_fails_fast_when_startup_heartbeat_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Startup damgası yazılamazsa loop HİÇ başlamaz, wiring dispose edilir, exit 1."""
    wiring = _FakeWiring()
    monkeypatch.setattr(worker_main, "build_runtime", lambda settings: wiring)

    def _broken_write(path: str, document: dict[str, object]) -> None:
        raise OSError("disk dolu: /gizli/yol")

    monkeypatch.setattr(worker_main, "write_heartbeat_document", _broken_write)
    loop_calls: list[object] = []
    monkeypatch.setattr(worker_main, "_serve_loop", lambda **kwargs: loop_calls.append(kwargs) or 0)

    exit_code = _run_serve(
        _test_settings(),
        tenant_ids=[UUID(_T1)],
        worker_id="w",
        interval=1.0,
        limit=5,
        heartbeat_path=str(tmp_path / "hb.json"),
    )

    assert exit_code == 1
    assert loop_calls == []  # runtime service loop BAŞLAMADI
    assert wiring.disposed
    err = capsys.readouterr().err
    assert _HEARTBEAT_PATH_ENV_VAR in err
    assert "disk dolu" not in err  # raw exception SIZDIRILMAZ
    assert "gizli" not in err


# ------------------------------------------------------------ --check-heartbeat


def _healthy_document(now: datetime, **overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "status": "healthy",
        "pid": 123,
        "started_at": _fmt(now - timedelta(seconds=120)),
        "updated_at": _fmt(now),
        "last_full_success_at": _fmt(now - timedelta(seconds=5)),
        "tenant_count": 3,
        "consecutive_failed_sweeps": 0,
    }
    document.update(overrides)
    return document


def _write_raw(tmp_path: Path, content: str) -> Path:
    target = tmp_path / "hb.json"
    target.write_text(content, encoding="utf-8")
    return target


def _write_document(tmp_path: Path, document: dict[str, object]) -> Path:
    return _write_raw(tmp_path, json.dumps(document))


def test_check_heartbeat_accepts_fresh_healthy_document(tmp_path: Path) -> None:
    target = _write_document(tmp_path, _healthy_document(_NOW))

    exit_code, message = check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)

    assert exit_code == 0
    assert "sağlıklı" in message
    # Dosya içeriği stdout'a DÖKÜLMEZ.
    assert "tenant_count" not in message
    assert "{" not in message


@pytest.mark.parametrize("status", ["starting", "degraded", "stopping", "stopped"])
def test_check_heartbeat_rejects_non_healthy_statuses(tmp_path: Path, status: str) -> None:
    target = _write_document(tmp_path, _healthy_document(_NOW, status=status))

    exit_code, message = check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)

    assert exit_code == 1
    assert status in message


def test_check_heartbeat_rejects_unknown_status(tmp_path: Path) -> None:
    target = _write_document(tmp_path, _healthy_document(_NOW, status="zombie"))

    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_rejects_degraded_even_with_fresh_updated_at(
    tmp_path: Path,
) -> None:
    """Sürekli degraded worker, dosyayı taze yazsa bile healthy SAYILMAZ."""
    document = _healthy_document(
        _NOW,
        status="degraded",
        updated_at=_fmt(_NOW),
        consecutive_failed_sweeps=7,
    )
    target = _write_document(tmp_path, document)

    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_rejects_missing_last_full_success(tmp_path: Path) -> None:
    for value in (None,):
        target = _write_document(tmp_path, _healthy_document(_NOW, last_full_success_at=value))
        assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1

    document = _healthy_document(_NOW)
    del document["last_full_success_at"]
    target = _write_document(tmp_path, document)
    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_rejects_stale_last_full_success(tmp_path: Path) -> None:
    stale = _fmt(_NOW - timedelta(seconds=61))
    target = _write_document(tmp_path, _healthy_document(_NOW, last_full_success_at=stale))

    exit_code, message = check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)

    assert exit_code == 1
    assert "bayat" in message


def test_check_heartbeat_accepts_age_exactly_at_threshold(tmp_path: Path) -> None:
    on_edge = _fmt(_NOW - timedelta(seconds=60))
    target = _write_document(tmp_path, _healthy_document(_NOW, last_full_success_at=on_edge))

    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 0


def test_check_heartbeat_rejects_naive_timestamp(tmp_path: Path) -> None:
    naive = "2026-07-24T09:59:59"  # tzinfo YOK
    target = _write_document(tmp_path, _healthy_document(_NOW, last_full_success_at=naive))

    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_tolerates_small_future_but_rejects_large(tmp_path: Path) -> None:
    slightly_future = _fmt(_NOW + timedelta(seconds=3))
    target = _write_document(
        tmp_path, _healthy_document(_NOW, last_full_success_at=slightly_future)
    )
    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 0

    far_future = _fmt(_NOW + timedelta(seconds=10))
    target = _write_document(tmp_path, _healthy_document(_NOW, last_full_success_at=far_future))
    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_rejects_invalid_json(tmp_path: Path) -> None:
    target = _write_raw(tmp_path, "{bozuk json")

    exit_code, message = check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)

    assert exit_code == 1
    assert "bozuk" not in message  # ham içerik mesaja TAŞINMAZ


def test_check_heartbeat_rejects_non_object_root(tmp_path: Path) -> None:
    target = _write_raw(tmp_path, '["healthy"]')

    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pid", "123"),
        ("pid", True),
        ("pid", 0),
        ("pid", -5),
        ("tenant_count", "3"),
        ("tenant_count", True),
        ("consecutive_failed_sweeps", -1),
        ("consecutive_failed_sweeps", True),
        ("consecutive_failed_sweeps", "0"),
        ("started_at", "2026-07-24T09:00:00"),
        ("started_at", 12345),
        ("updated_at", "yakında"),
        ("status", 7),
    ],
)
def test_check_heartbeat_rejects_invalid_field_types(
    tmp_path: Path, field: str, value: object
) -> None:
    target = _write_document(tmp_path, _healthy_document(_NOW, **{field: value}))

    assert check_heartbeat(str(target), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_rejects_missing_file(tmp_path: Path) -> None:
    assert check_heartbeat(str(tmp_path / "yok.json"), max_age_seconds=60.0, now=_NOW)[0] == 1


def test_check_heartbeat_cli_mode_never_builds_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checker database/wiring'e DOKUNMAZ: build_runtime çağrılırsa test patlar."""

    def _forbidden(settings: object) -> object:
        raise AssertionError("checker build_runtime çağıramaz")

    monkeypatch.setattr(worker_main, "build_runtime", _forbidden)
    target = _write_document(tmp_path, _healthy_document(datetime.now(UTC)))
    monkeypatch.setenv(_HEARTBEAT_PATH_ENV_VAR, str(target))
    monkeypatch.setenv(_HEARTBEAT_MAX_AGE_ENV_VAR, "60")

    assert main(["--check-heartbeat"]) == 0


def test_check_heartbeat_cli_mode_uses_default_path_when_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Path unset → heartbeat kapanmaz; default yol denetlenir (dosya yoksa exit 1)."""
    monkeypatch.delenv(_HEARTBEAT_PATH_ENV_VAR, raising=False)
    monkeypatch.delenv(_HEARTBEAT_MAX_AGE_ENV_VAR, raising=False)

    exit_code = main(["--check-heartbeat"])

    # Default yolda taze-healthy bir belge beklemiyoruz; sonuç deterministik olarak
    # ya 1'dir (dosya yok) ya da 0 (aynı makinede gerçek worker çalışıyorsa).
    assert exit_code in (0, 1)
    assert "heartbeat" in capsys.readouterr().out


def test_check_heartbeat_cli_mode_rejects_blank_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(_HEARTBEAT_PATH_ENV_VAR, "   ")

    with pytest.raises(SystemExit) as excinfo:
        main(["--check-heartbeat"])

    assert excinfo.value.code == 2
    assert _HEARTBEAT_PATH_ENV_VAR in capsys.readouterr().err


def test_check_heartbeat_cli_mode_rejects_invalid_max_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(_HEARTBEAT_PATH_ENV_VAR, str(tmp_path / "hb.json"))
    monkeypatch.setenv(_HEARTBEAT_MAX_AGE_ENV_VAR, "0.5")

    with pytest.raises(SystemExit) as excinfo:
        main(["--check-heartbeat"])

    assert excinfo.value.code == 2
    assert _HEARTBEAT_MAX_AGE_ENV_VAR in capsys.readouterr().err


def test_check_heartbeat_mode_is_mutually_exclusive_with_serve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        main(["--check-heartbeat", "--serve", "--tenant", _T1])

    assert "not allowed with" in capsys.readouterr().err


# ----------------------------------------------------------------- subprocess smoke


def test_module_entrypoint_runs_as_subprocess_and_exits_zero() -> None:
    # `python -m flowpilot.worker --check` gerçekten çalışır ve ASILI KALMAZ.
    result = subprocess.run(
        [sys.executable, "-m", "flowpilot.worker", "--check"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert CHECK_OK_MESSAGE in result.stdout


def test_check_heartbeat_subprocess_exits_one_without_touching_database(
    tmp_path: Path,
) -> None:
    """Healthcheck komutu gerçekten çalışır, ASILI KALMAZ ve DB'ye DOKUNMAZ."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONIOENCODING": "utf-8",
        _HEARTBEAT_PATH_ENV_VAR: str(tmp_path / "hb.json"),
        # Kasten GEÇERSİZ DSN: healthcheck DB'ye bağlanmaya çalışsaydı bu görünürdü.
        "DATABASE_URL": "postgresql+psycopg://invalid:invalid@127.0.0.1:1/none",
    }
    result = subprocess.run(
        [sys.executable, "-m", "flowpilot.worker", "--check-heartbeat"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        env=env,
    )

    assert result.returncode == 1, result.stderr
    assert "heartbeat" in result.stdout
    assert "Traceback" not in result.stderr
