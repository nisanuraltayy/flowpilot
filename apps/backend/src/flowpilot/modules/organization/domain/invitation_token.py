"""Davet token'ı — güvenli üretim portu + deterministik hash (at-rest).

Ham token KRIPTOGRAFİK OLARAK GÜVENLİ üretilir (`secrets`, infrastructure adapter);
domain yalnız DETERMİNİSTİK hash fonksiyonunu tanımlar. Veritabanında YALNIZ hash
saklanır; ham token asla persist edilmez, log'lanmaz, audit/outbox'a yazılmaz.

`hashlib` standart kütüphanedir (framework/ORM/SDK değil) — domain'de kullanımı serbest
(check_import_boundaries DOMAIN_FORBIDDEN_ROOTS listesinde değildir).
"""

from __future__ import annotations

import hashlib
from typing import Protocol

# SHA-256 hex digest uzunluğu — DB kolonu `token_hash String(64)` ile hizalı.
TOKEN_HASH_LENGTH = 64


def hash_invitation_token(raw_token: str) -> str:
    """Ham token'ı deterministik SHA-256 hex digest'e çevirir (at-rest saklama).

    Aynı girdi → aynı çıktı (lookup için); ham token'dan hash türetilebilir ama
    hash'ten ham token türetilemez.
    """
    if not raw_token:
        raise ValueError("bos token hash'lenemez")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def invitation_request_fingerprint(*, invited_email: str, role: str) -> str:
    """Idempotency payload parmak izi (deterministik hash; PII saklamaz).

    Aynı Idempotency-Key farklı payload ile gelirse tespit için kullanılır. Ham
    e-posta `request_fingerprint` kolonunda değil, YALNIZ hash olarak yer alır.
    """
    return hashlib.sha256(f"{invited_email}|{role}".encode()).hexdigest()


def invitation_accept_fingerprint(*, organization_id: str, token_hash: str) -> str:
    """Davet KABUL isteğinin payload parmak izi (Idempotency-Key conflict tespiti).

    `operation | organization_id | token_hash` üzerinden deterministik hash. Ham token
    veya token_hash DOĞRUDAN saklanmaz; yalnız bu fingerprint hash'inin içinde yer alır.
    """
    return hashlib.sha256(f"invitation.accept|{organization_id}|{token_hash}".encode()).hexdigest()


class InvitationTokenGeneratorPort(Protocol):
    """Kriptografik güvenli ham token üreten port (injectable — testte deterministik).

    Domain doğrudan `secrets`/random KULLANMAZ; üretim infrastructure adapter'ındadır.
    """

    def new_raw_token(self) -> str: ...
