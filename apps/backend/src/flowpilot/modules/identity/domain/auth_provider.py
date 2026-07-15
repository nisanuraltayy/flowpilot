"""AuthProvider — harici kimlik sağlayıcısının provider-neutral adı.

Domain kavramıdır; hiçbir SDK import etmez. Yeni provider eklemek yalnız buraya
bir değer eklemektir (ADR-005: provider yalnız kimlik doğrular).
"""

from __future__ import annotations

from enum import StrEnum


class AuthProvider(StrEnum):
    """Desteklenen harici kimlik sağlayıcıları."""

    SUPABASE = "supabase"
