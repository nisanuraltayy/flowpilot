"""Domain error temel sınıfı.

Tüm domain error'ları bundan türer. Serbest metin yerine stabil, yakalanabilir
tipler kullanılır (PRD §38.15).
"""

from __future__ import annotations


class DomainError(Exception):
    """FlowPilot domain kurallarının ihlali."""
