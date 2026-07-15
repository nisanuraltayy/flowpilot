"""Integration testleri için paylaşılan sabitler ve yardımcılar (conftest değil).

Constant'lar hem conftest hem test dosyaları tarafından import edilir; conftest'i
doğrudan import etmekten kaçınmak için ayrı bir modülde tutulur.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
IMAGE = "postgres:17.10-alpine"
DB_NAME = "flowpilot_test"
ADMIN_USER = "test_admin"
ADMIN_PW = "test_admin_pw"
APP_PW = "test_app_pw"
MIGRATOR_PW = "test_migrator_pw"


def load_provision_module() -> ModuleType:
    """scripts/provision_local_database.py'yi tekrar kullanmak için yükler."""
    path = REPO_ROOT / "scripts" / "provision_local_database.py"
    spec = importlib.util.spec_from_file_location("provision_local_database", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
