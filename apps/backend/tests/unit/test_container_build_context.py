"""Container build context sözleşmesi (FP-OPS-001).

Dockerfile'lar ve `.dockerignore` dosyaları için STATİK doğrulama — Docker daemon
GEREKTİRMEZ. Amaç: secret/env dosyalarının build context'e girmemesi ve deployment
sözleşmesinin (non-root, startup'ta migration yok, dev server yok) korunması.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND = _REPO_ROOT / "apps" / "backend"
_WEB = _REPO_ROOT / "apps" / "web"

# Build context'e ASLA girmemesi gereken desenler.
_SECRET_PATTERNS = (".env", "*.pem", "*.key")


def _read(path: Path) -> str:
    assert path.is_file(), f"beklenen dosya yok: {path}"
    return path.read_text(encoding="utf-8")


def _instructions(path: Path) -> str:
    """Yalnız GERÇEK Dockerfile talimatları (yorum satırları hariç).

    Negatif iddialar (`--reload` yok, `next dev` yok ...) yorumlardaki açıklama
    metinlerine takılmamalıdır; bu yüzden yorumlar ayıklanır.
    """
    lines = [line for line in _read(path).splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


@pytest.mark.parametrize("dockerignore", [_BACKEND / ".dockerignore", _WEB / ".dockerignore"])
def test_dockerignore_excludes_secret_and_env_files(dockerignore: Path) -> None:
    content = _read(dockerignore)
    for pattern in _SECRET_PATTERNS:
        assert pattern in content, f"{dockerignore.name} '{pattern}' desenini dislamiyor"
    # `.env.*` (or. .env.local, .env.production) da dislanmali.
    assert ".env.*" in content or "*.env" in content


def test_backend_dockerignore_keeps_required_sources() -> None:
    """Gerekli kaynaklar YANLISLIKLA dislanmamali (aksi halde image calismaz)."""
    content = _read(_BACKEND / ".dockerignore")
    required = {"pyproject.toml", "src/", "alembic.ini", "migrations"}
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert stripped not in required, f"gerekli kaynak dislanmis: {stripped}"


def test_web_dockerignore_excludes_build_artifacts_but_keeps_sources() -> None:
    content = _read(_WEB / ".dockerignore")
    assert "node_modules/" in content
    assert ".next/" in content
    required = {"package.json", "package-lock.json", "src/", "public/"}
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert stripped not in required, f"gerekli kaynak dislanmis: {stripped}"


def test_backend_dockerfile_deployment_contract() -> None:
    instructions = _instructions(_BACKEND / "Dockerfile")
    # Non-root calisir.
    assert "USER 10001:10001" in instructions
    # Gercek ASGI entrypoint; reload YOK.
    assert "flowpilot.api.main:app" in instructions
    assert "--reload" not in instructions
    # Host 0.0.0.0.
    assert "--host 0.0.0.0" in instructions
    # Startup'ta OTOMATIK migration YOK (talimatlarda alembic upgrade calismaz).
    assert "upgrade head" not in instructions
    # Healthcheck YALNIZ gercek liveness endpoint'ini kullanir (sahte readiness degil).
    assert "/health/live" in instructions
    assert "/health/ready" not in instructions
    # Worker bu image'in default process'i DEGILDIR.
    assert "flowpilot.worker" not in instructions


def test_web_dockerfile_deployment_contract() -> None:
    instructions = _instructions(_WEB / "Dockerfile")
    # Non-root calisir.
    assert "USER node" in instructions
    # Development server KULLANILMAZ.
    assert "next dev" not in instructions
    assert "npm run dev" not in instructions
    # Standalone entrypoint.
    assert "server.js" in instructions
    # Deterministik kurulum.
    assert "npm ci" in instructions
    # Server-only degisken build-time'a GOMULMEZ (yalniz NEXT_PUBLIC_* ARG olur).
    assert "ARG FLOWPILOT_API_BASE_URL" not in instructions


def test_web_next_config_uses_standalone_output() -> None:
    content = _read(_WEB / "next.config.ts")
    assert '"standalone"' in content or "'standalone'" in content
