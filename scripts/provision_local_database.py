#!/usr/bin/env python
"""LOCAL DEVELOPMENT aracı — FlowPilot PostgreSQL rollerini provision eder.

⚠️ Bu bir LOCAL DEVELOPMENT aracıdır. Production role provisioning bu script'in
görevi DEĞİLDİR (production'da roller ayrı, denetlenen bir süreçle yönetilir).

İki rol oluşturur (idempotent — ikinci çalıştırmada güvenle tekrar çalışır):

  flowpilot_migrator : DDL/migration rolü. NOSUPERUSER, NOBYPASSRLS, NOCREATEDB,
                       NOCREATEROLE. public şemada CREATE yetkisi (tablo oluşturur).
  flowpilot_app      : uygulama DML rolü. NOSUPERUSER, NOBYPASSRLS, NOCREATEDB,
                       NOCREATEROLE. Yalnız public şemada USAGE (DML grant'ları
                       migration tarafından verilir).

Admin bağlantısı YALNIZ provisioning için kullanılır (bootstrap superuser
flowpilot_admin). Parolalar environment'tan alınır; terminale YAZILMAZ.
Yalnız `flowpilot` database ve FlowPilot rolleri yönetilir — Career Copilot
database veya rollerine DOKUNULMAZ.
"""

from __future__ import annotations

import os
import sys

import psycopg
from dotenv import load_dotenv
from psycopg import sql

MIGRATOR_ROLE = "flowpilot_migrator"
APP_ROLE = "flowpilot_app"


def _ensure_login_role(
    conn: psycopg.Connection[object], role: str, password: str
) -> None:
    """Rolü idempotent oluşturur ve güvenli öznitelikleri zorlar."""
    conn.execute(
        sql.SQL(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {name_lit}) THEN "
            "CREATE ROLE {name_ident} LOGIN; "
            "END IF; END $$;"
        ).format(name_lit=sql.Literal(role), name_ident=sql.Identifier(role))
    )
    conn.execute(
        sql.SQL(
            "ALTER ROLE {ident} WITH LOGIN NOSUPERUSER NOBYPASSRLS "
            "NOCREATEDB NOCREATEROLE PASSWORD {pw}"
        ).format(ident=sql.Identifier(role), pw=sql.Literal(password))
    )


def provision_roles(
    conn: psycopg.Connection[object],
    *,
    database: str,
    app_password: str,
    migrator_password: str,
) -> None:
    """flowpilot_migrator ve flowpilot_app rollerini (idempotent) sağlar.

    `conn` autocommit modunda, admin/superuser bir bağlantı olmalıdır. Bu
    fonksiyon hem CLI hem de integration test fixture'ı tarafından kullanılır.
    """
    _ensure_login_role(conn, MIGRATOR_ROLE, migrator_password)
    _ensure_login_role(conn, APP_ROLE, app_password)

    db_ident = sql.Identifier(database)
    for role in (MIGRATOR_ROLE, APP_ROLE):
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {db} TO {role}").format(
                db=db_ident, role=sql.Identifier(role)
            )
        )
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {role}").format(
                role=sql.Identifier(role)
            )
        )

    # Migrator tabloları oluşturur → public şemada CREATE gerekir.
    conn.execute(
        sql.SQL("GRANT CREATE ON SCHEMA public TO {role}").format(
            role=sql.Identifier(MIGRATOR_ROLE)
        )
    )


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(
            f"HATA: {name} tanimli degil (.env dosyasini kontrol edin).",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return value


def main() -> int:
    # Repo kökündeki .env'i yükler (varsa). CI/manuel export edilmişse de çalışır.
    load_dotenv()
    database = os.environ.get("POSTGRES_DB", "flowpilot")
    with psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=database,
        user=_env("POSTGRES_USER"),
        password=_env("POSTGRES_PASSWORD"),
        autocommit=True,
    ) as conn:
        provision_roles(
            conn,
            database=database,
            app_password=_env("POSTGRES_APP_PASSWORD"),
            migrator_password=_env("POSTGRES_MIGRATION_PASSWORD"),
        )

    # Secret DEĞERLERİ yazılmaz — yalnız rol adları.
    print(f"Roller hazir (idempotent): {MIGRATOR_ROLE}, {APP_ROLE} @ db={database}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
