# FlowPilot Backend (API) — provider-neutral production image.
#
# Build context: apps/backend  (distribution kendi kendine yeterlidir — ADR-009)
#   docker build -t flowpilot-api:local apps/backend
#
# Kurallar:
# - SAĞLAYICIYA ÖZEL hiçbir şey yoktur (Render/Vercel/Fly/Railway manifesti YOK).
# - Bu image YALNIZ API process'ini çalıştırır. Worker AYRI bir process/servistir
#   (worker servis modu FP-OPS-002 kapsamındadır) — bu image'ın default'u DEĞİLDİR.
# - Migration UYGULAMA STARTUP'INDA ÇALIŞTIRILMAZ; ayrı bir release adımıdır
#   (bkz. scripts/run_production_migrations.py ve docs/operations/container-deployment.md).
# - Image içine .env, secret, sertifika veya anahtar KOPYALANMAZ (.dockerignore).
# - Non-root çalışır; bytecode ve pip cache bırakılmaz.

# ---------------------------------------------------------------------------
# Stage 1 — builder: bağımlılıkları ve paketi izole bir venv'e kur
# ---------------------------------------------------------------------------
# Python sürümü repository ile hizalı: requires-python >=3.12,<3.14; CI 3.13 kullanır.
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# İzole venv — runtime stage'e bütün olarak kopyalanır.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Cache dostu sıra: önce yalnız dependency metadata'sı, sonra kaynak kod.
# (pyproject değişmediği sürece dependency katmanı yeniden kurulmaz.)
COPY pyproject.toml README.md ./
COPY src/flowpilot/__init__.py ./src/flowpilot/__init__.py
RUN pip install --no-cache-dir .

# Şimdi gerçek kaynak kod; yalnız uygulama katmanı yeniden kurulur.
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

# ---------------------------------------------------------------------------
# Stage 2 — runtime: yalnız venv + migration varlıkları; derleyici/pip artığı yok
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_PORT=8000

# Non-root kullanıcı (sabit uid/gid — platformdan bağımsız).
RUN groupadd --gid 10001 flowpilot \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin flowpilot

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Migration varlıkları image'da bulunur ki AYRI bir release adımı (aynı image ile
# `alembic upgrade head`) çalıştırılabilsin. Startup'ta OTOMATİK çalıştırılmaz.
COPY --chown=10001:10001 alembic.ini ./alembic.ini
COPY --chown=10001:10001 migrations ./migrations

USER 10001:10001

EXPOSE 8000

# Liveness — YALNIZ gerçek liveness endpoint'i kullanılır. `/health/ready` şu an
# statiktir (hiçbir bağımlılığı kontrol etmez); sahte readiness deployment
# healthcheck'i olarak SUNULMAZ (gerçek readiness FP-OPS-002 kapsamındadır).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:'+os.environ.get('APP_PORT','8000')+'/health/live'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)"

# Uvicorn — gerçek ASGI entrypoint: flowpilot.api.main:app (module-level `app`).
# Reload YOKTUR. Port environment'tan gelir, güvenli default 8000'dir.
CMD ["sh", "-c", "exec uvicorn flowpilot.api.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
