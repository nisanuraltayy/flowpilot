"""Container build context sözleşmesi (FP-OPS-001).

Dockerfile'lar ve `.dockerignore` dosyaları için STATİK doğrulama — Docker daemon
GEREKTİRMEZ. Amaç: secret/env dosyalarının build context'e girmemesi ve deployment
sözleşmesinin (non-root, startup'ta migration yok, dev server yok) korunması.
"""

from __future__ import annotations

import subprocess
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


def _stages(path: Path) -> dict[str, str]:
    """Dockerfile'i `FROM ... AS <ad>` sinirlarindan stage'lere ayirir (yorumsuz).

    Stage adi olmayan bir FROM bulunursa test anlamli sekilde patlar; boylece
    stage'e bagli iddialar sessizce bos metin uzerinde dogrulanmaz.
    """
    stages: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in _instructions(path).splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FROM "):
            parts = stripped.split()
            assert len(parts) >= 4 and parts[-2].upper() == "AS", f"adsiz FROM: {stripped}"
            current = stages.setdefault(parts[-1], [])
        if current is not None:
            current.append(line)
    return {name: "\n".join(lines) for name, lines in stages.items()}


def _stage_order(path: Path) -> list[str]:
    return list(_stages(path))


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
    # Healthcheck YALNIZ gercek liveness endpoint'ini kullanir (readiness DEGIL:
    # gecici bir database kesintisi saglikli API surecini oldurmemeli).
    assert "/health/live" in instructions
    assert "/health/ready" not in instructions


def test_backend_default_build_target_is_api_not_worker() -> None:
    """`--target` verilmeden yapilan build API uretir; worker default DEGILDIR."""
    order = _stage_order(_BACKEND / "Dockerfile")

    assert order[-1] == "api", f"son stage 'api' olmali, bulunan: {order[-1]}"
    assert "worker" in order
    assert order.index("worker") < order.index("api")


def test_backend_api_stage_does_not_run_worker() -> None:
    api_stage = _stages(_BACKEND / "Dockerfile")["api"]

    assert "flowpilot.api.main:app" in api_stage
    assert "flowpilot.worker" not in api_stage


def test_backend_worker_stage_runs_service_mode_without_http() -> None:
    worker_stage = _stages(_BACKEND / "Dockerfile")["worker"]

    # Worker AYRI bir composition root'tur; ASGI uygulamasini CALISTIRMAZ.
    assert "flowpilot.api.main:app" not in worker_stage
    assert "uvicorn" not in worker_stage
    # Servis modu + heartbeat tabanli healthcheck (HTTP portu YOK).
    assert "--serve" in worker_stage
    assert "--check-heartbeat" in worker_stage
    assert "HEALTHCHECK" in worker_stage
    assert "EXPOSE" not in worker_stage
    # Tenant listesi image'a GOMULMEZ (environment'tan gelir).
    assert "WORKER_TENANT_IDS=" not in worker_stage
    # Startup'ta migration YOK.
    assert "upgrade head" not in worker_stage


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


def _git_tracked_modes(pattern: str) -> dict[str, str]:
    """git'in KAYITLI dosya modlarını döndürür ({yol: mode}); git yoksa boş sözlük.

    Filesystem yerine git modu okunur: Windows'ta POSIX executable biti yoktur, bu
    yüzden yalnız dosya sistemine bakan bir kontrol bu sınıf hatayı YAKALAYAMAZ.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-s", "--", pattern],  # noqa: S607 — sabit git komutu
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git yoksa
        return {}
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    modes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if parts and path:
            modes[path.strip()] = parts[0]
    return modes


def test_shebang_scripts_are_committed_executable() -> None:
    """Shebang'li script'ler git'te 100755 olmalı (Linux CI: ruff EXE001).

    REGRESYON: Windows'ta ruff EXE001'i değerlendiremediği için shebang'li ama
    executable OLMAYAN bir script local'de sessizce geçer, Linux CI'da patlar.
    """
    modes = _git_tracked_modes("scripts/*.py")
    if not modes:  # git checkout değil (ör. sdist / git archive) → doğrulanamaz
        pytest.skip("git kayıtlı dosya modları okunamadı (git checkout değil)")

    for path, mode in sorted(modes.items()):
        script = _REPO_ROOT / path
        if not script.is_file():
            continue
        first_line = script.read_text(encoding="utf-8").splitlines()[:1]
        if first_line and first_line[0].startswith("#!"):
            assert mode == "100755", (
                f"{path} shebang iceriyor ama git modu {mode} "
                "(Linux CI'da ruff EXE001 hatasi verir; 100755 olmali)"
            )
