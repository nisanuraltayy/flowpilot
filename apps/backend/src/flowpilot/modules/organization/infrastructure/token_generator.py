"""Kriptografik güvenli davet token üreticisi (`InvitationTokenGeneratorPort` adapter'ı).

`secrets.token_urlsafe` kullanır (CSPRNG). Domain yalnız hash fonksiyonunu tanımlar;
ham token üretimi bu infrastructure adapter'ındadır ve YALNIZ oluşturma cevabında döner.
"""

from __future__ import annotations

import secrets

# 32 bayt entropi → ~43 karakter URL-safe token (yüksek çakışma direnci).
_TOKEN_NBYTES = 32


class SecretsInvitationTokenGenerator:
    """`InvitationTokenGeneratorPort` port'unu uygular (CSPRNG)."""

    def new_raw_token(self) -> str:
        return secrets.token_urlsafe(_TOKEN_NBYTES)
