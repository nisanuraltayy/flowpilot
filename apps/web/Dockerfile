# FlowPilot Web (Next.js) — provider-neutral production image.
#
# Build context: apps/web  (kendi package.json + package-lock.json'a sahiptir)
#   docker build -t flowpilot-web:local apps/web
#
# Kurallar:
# - SAĞLAYICIYA ÖZEL hiçbir şey yoktur (Render/Vercel/Fly/Railway manifesti YOK).
# - Development server (`next dev`) KULLANILMAZ; standalone server çalıştırılır.
# - Image içine .env.local, secret veya anahtar KOPYALANMAZ (.dockerignore).
# - Non-root çalışır.
#
# BUILD-TIME vs RUNTIME environment:
# - NEXT_PUBLIC_* değişkenleri BUILD sırasında bundle'a gömülür → `--build-arg` ile verilir.
# - Server-only değişkenler (FLOWPILOT_API_BASE_URL) RUNTIME'da verilir; build'e GİRMEZ
#   ve browser bundle'a SIZMAZ (NEXT_PUBLIC_ öneki yoktur, `server-only` ile korunur).

# ---------------------------------------------------------------------------
# Stage 1 — deps: yalnız lockfile ile deterministik kurulum (cache dostu)
# ---------------------------------------------------------------------------
# Node sürümü repository ile hizalı: CI `node-version: "20"` kullanır.
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
# Stage 2 — builder: production build (standalone output)
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Yalnız PUBLIC değişkenler build-time'da gömülür. Secret DEĞİLDİRLER.
# Server-only değerler bilinçli olarak BURADA YOKTUR.
ARG NEXT_PUBLIC_SUPABASE_URL=""
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=""
ARG NEXT_PUBLIC_APP_URL=""
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY \
    NEXT_PUBLIC_APP_URL=$NEXT_PUBLIC_APP_URL

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 3 — runtime: yalnız standalone çıktısı (node_modules/dev bağımlılığı yok)
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# node:alpine imajında hazır gelen non-root `node` kullanıcısı (uid/gid 1000).
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
COPY --from=builder --chown=node:node /app/public ./public

USER node

EXPOSE 3000

# Standalone entrypoint — `next start` değil, üretilen server.js.
# Port ve hostname environment'tan gelir (güvenli default: 3000 / 0.0.0.0).
CMD ["node", "server.js"]
