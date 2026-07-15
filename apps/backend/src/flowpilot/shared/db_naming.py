"""Veritabanı constraint/index adlandırma sözleşmesi.

Bu YALNIZCA bir pure-dict SÖZLEŞMEDİR — SQLAlchemy import ETMEZ. Bu yüzden
`flowpilot.shared` içinde durabilir (import-linter "shared saf kalır" contract'ı
korunur) ve tek kaynak olur; her modülün `MetaData` nesnesi bu convention'ı
kullanır (ADR-009 — module-owned metadata).

Alembic'in tek migration history'si bu adlarla tutarlı DDL üretir:
  pk_<table>, fk_<table>_<col>_<referred>, uq_<table>_<col>,
  ix_<table>_<col>, ck_<table>_<constraint>
"""

from __future__ import annotations

NAMING_CONVENTION: dict[str, str] = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}
