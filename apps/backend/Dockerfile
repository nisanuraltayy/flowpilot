# FlowPilot Backend — provider-neutral production image (API + worker).
#
# Build context: apps/backend  (distribution kendi kendine yeterlidir — ADR-009)
#   docker build -t flowpilot-api:local apps/backend                            # API (default)
#   docker build --target worker-runtime -t flowpilot-worker:local apps/backend # worker
#
# API ve worker AYNI distribution'ın İKİ COMPOSITION ROOT'udur (ADR-009): ortak
# `runtime` katmanını paylaşırlar, AYRI process/servis olarak çalıştırılırlar.
# `api` stage'i EN SONDADIR: `--target` verilmeden yapılan build API üretir; worker
# hiçbir koşulda default process DEĞİLDİR.
#
# Kurallar:
# - SAĞLAYICIYA ÖZEL hiçbir şey yoktur (Render/Vercel/Fly/Railway manifesti YOK).
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
# Stage 2 — runtime: API ve worker'ın PAYLAŞTIĞI taban
#
# Yalnız venv + migration varlıkları; derleyici/pip artığı yok. Bu stage BİLİNÇLİ
# olarak process tanımlamaz (CMD yoktur) — çalıştırılabilir image'lar aşağıdaki
# `worker` ve `api` stage'leridir.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

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

# ---------------------------------------------------------------------------
# Stage 3 — worker-runtime: outbox/timer dispatch servisi
#                           (AYRI process, --target worker-runtime)
#
# HTTP port DİNLEMEZ; liveness HTTP ile ölçülemez (API'nin /health/live healthcheck'i
# burada KULLANILMAZ). Bunun yerine süreç yaşam döngüsünü heartbeat JSON belgesine
# yazar (starting → healthy/degraded → stopping → stopped); healthcheck bu belgeyi
# ve `last_full_success_at` tazeliğini doğrular (database'e DOKUNMAZ).
#
# Tenant allowlist'i WORKER_TENANT_IDS ile verilir (worker cross-tenant KEŞİF
# YAPMAZ). Boşsa süreç kontrollü hata ile çıkar; sessizce boş çalışmaz.
# ---------------------------------------------------------------------------
FROM runtime AS worker-runtime

# Heartbeat dosyası: container'a özgü, non-root kullanıcının yazabildiği geçici yol.
# Kod default'u ile AYNI değerdir; kalıcı volume GEREKTİRMEZ.
ENV WORKER_HEARTBEAT_PATH=/tmp/flowpilot-worker-heartbeat.json \
    WORKER_HEARTBEAT_MAX_AGE_SECONDS=60

# Heartbeat doğrulaması: worker loop BAŞLATMAZ, database bağlantısı KURMAZ.
# start-period süreci ilk TAM BAŞARILI sweep'e kadar hoşgörür; retries bounded'dır.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-m", "flowpilot.worker", "--check-heartbeat"]

# Servis modu: tenant'lar WORKER_TENANT_IDS'ten, poll interval
# WORKER_POLL_INTERVAL_SECONDS'tan gelir. SIGTERM'de graceful durur.
CMD ["python", "-m", "flowpilot.worker", "--serve"]

# ---------------------------------------------------------------------------
# Stage 4 — api: HTTP process. EN SON STAGE = default build target.
# ---------------------------------------------------------------------------
FROM runtime AS api

ENV APP_PORT=8000

EXPOSE 8000

# Liveness — YALNIZ gerçek liveness endpoint'i kullanılır. Readiness gerçek
# database kontrolü yapar; container healthcheck'i olarak KULLANILMAZ, çünkü
# geçici bir database kesintisi sağlıklı bir API sürecini öldürmemelidir
# (readiness load balancer / platform trafik kararına aittir).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:'+os.environ.get('APP_PORT','8000')+'/health/live'; \
sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)"

# Uvicorn — gerçek ASGI entrypoint: flowpilot.api.main:app (module-level `app`).
# Reload YOKTUR. Port environment'tan gelir, güvenli default 8000'dir.
CMD ["sh", "-c", "exec uvicorn flowpilot.api.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
