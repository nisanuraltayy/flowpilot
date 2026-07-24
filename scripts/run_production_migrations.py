#!/usr/bin/env python
"""Deployment RELEASE adımı — Alembic migration'larını head'e yükseltir.

Bu script SAĞLAYICIDAN BAĞIMSIZDIR ve uygulama startup'ının parçası DEĞİLDİR:
API/worker container'ları migration ÇALIŞTIRMAZ. Deployment akışında ayrı,
tek seferlik bir adım olarak çalıştırılır (bkz.
docs/operations/container-deployment.md §Migration release step).

Kullanım (repo kökü veya backend distribution içinden):

    python scripts/run_production_migrations.py
    python scripts/run_production_migrations.py --check-only

Bağlantı: MIGRATION_DATABASE_URL (migrator rolü — `flowpilot_migrator`).
Uygulama rolü (`flowpilot_app`) DDL çalıştırmaz.

Güvenlik / güvenlik ağı:
- Bağlantı dizesi, parola veya herhangi bir secret DEĞERİ EKRANA YAZILMAZ.
  Yalnız revision kimlikleri (secret değildir) raporlanır.
- Database SIFIRLANMAZ, downgrade ÇALIŞTIRILMAZ, seed ÇALIŞTIRILMAZ.
- Başarısızlıkta çıkış kodu KORUNUR (>0) → deployment durur.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

# scripts/ -> repo kökü -> apps/backend/alembic.ini
_DEFAULT_ALEMBIC_INI = (
    Path(__file__).resolve().parent.parent / "apps" / "backend" / "alembic.ini"
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_MISCONFIGURED = 2


def _build_config(alembic_ini: Path) -> Config:
    if not alembic_ini.is_file():
        print(f"HATA: alembic config bulunamadi: {alembic_ini}", file=sys.stderr)
        raise SystemExit(EXIT_MISCONFIGURED)
    return Config(str(alembic_ini))


def _resolve_url() -> str:
    """Migration bağlantı dizesi (DEĞER yazdırılmaz)."""
    from flowpilot.config.settings import get_settings

    try:
        return get_settings().require_migration_database_url()
    except RuntimeError as exc:
        # Mesaj yalnız degisken ADINI icerir; deger icermez.
        print(f"HATA: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_MISCONFIGURED) from exc


def _current_revision(url: str) -> str | None:
    """Veritabanındaki mevcut revision (yoksa None)."""
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _head_revision(config: Config) -> str:
    return ScriptDirectory.from_config(config).get_current_head() or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_production_migrations",
        description="Alembic migration'larini head'e yukseltir (deployment release adimi).",
    )
    parser.add_argument(
        "--alembic-ini",
        type=Path,
        default=_DEFAULT_ALEMBIC_INI,
        help="alembic.ini yolu (varsayilan: apps/backend/alembic.ini)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Yalnizca mevcut/head revision'i raporla; UPGRADE CALISTIRMA.",
    )
    args = parser.parse_args(argv)

    config = _build_config(args.alembic_ini)
    url = _resolve_url()

    head = _head_revision(config)
    if not head:
        print("HATA: migration head bulunamadi.", file=sys.stderr)
        return EXIT_MISCONFIGURED

    try:
        current = _current_revision(url)
    except Exception as exc:  # noqa: BLE001 — bağlantı/izin hatası; secret sızdırmadan raporla
        print(
            f"HATA: veritabanina baglanilamadi ({type(exc).__name__}).", file=sys.stderr
        )
        return EXIT_FAILED

    print(f"alembic current: {current or '(bos)'}")
    print(f"alembic head:    {head}")

    if current == head:
        print("Migration gerekmiyor — veritabani zaten head.")
        return EXIT_OK

    if args.check_only:
        print("check-only: upgrade CALISTIRILMADI (bekleyen migration var).")
        return EXIT_OK

    print("Uygulaniyor: alembic upgrade head")
    try:
        command.upgrade(config, "head")
    except Exception as exc:  # noqa: BLE001 — başarısız migration → deployment DURMALI
        print(f"HATA: migration basarisiz ({type(exc).__name__}).", file=sys.stderr)
        return EXIT_FAILED

    try:
        verified = _current_revision(url)
    except Exception as exc:  # noqa: BLE001 — doğrulama okunamadı; exit code korunur
        print(f"HATA: dogrulama okunamadi ({type(exc).__name__}).", file=sys.stderr)
        return EXIT_FAILED

    if verified != head:
        print(
            f"HATA: upgrade sonrasi revision beklenen head degil "
            f"(current={verified or '(bos)'}, head={head}).",
            file=sys.stderr,
        )
        return EXIT_FAILED

    print(f"Migration tamamlandi — current: {verified}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
