"""Workflow Runtime — application katmanı.

`WorkflowRuntimePort` (provider-neutral capability sözleşmesi), typed
command/result DTO'ları, repository/UnitOfWork port'ları ve use-case orkestrasyonu
burada yaşar. Somut adapter'a değil YALNIZ porta bağımlıdır; SQLAlchemy model veya
session döndürmez.
"""
