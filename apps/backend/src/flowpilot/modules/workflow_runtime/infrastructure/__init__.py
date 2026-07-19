"""Workflow Runtime — infrastructure katmanı (SQLAlchemy 2.0, module-owned).

ORM/Core tabloları, aggregate-specific repository'ler ve UnitOfWork adapter'ı
BURADADIR. Domain/application yalnız port'lara bağımlıdır; infrastructure
port'ları IMPLEMENTE eder ve dış katmanlara ORM tipi sızdırmaz.
"""
