"""Bounded context'ler (13).

Bir context, başka bir context'in `domain` veya `infrastructure` katmanını
DOĞRUDAN IMPORT EDEMEZ. Erişim yalnız açık application contract, command/query
veya versiyonlu integration event üzerindendir.

Bu paketlerin içinde henüz entity, model, repository, service, command, handler,
SQLAlchemy tablosu veya iş kuralı YOKTUR.
"""
