# apps/web — Kullanıcı Uygulaması (Next.js)

FlowPilot web arayüzü. Next.js 16 (App Router) + React 19 + TypeScript (strict) + Tailwind CSS v4 (ADR-002, ADR-009).

Bu aşamada teslim edilen uçtan uca kullanıcı akışı (tarayıcıdan çalışır):

```text
Giriş yap → aktif organizasyonu çöz/seç → satın alma talebi oluştur
  → "Taleplerim"de gör → kişisel onay kutusunda ilk görevi gör
  → onayla / reddet → sıradaki görev inbox'ta → süreç bitince durum + timeline
```

MVP'de aynı owner üç approval role'e de atandığı için tek kullanıcı tüm sıralı akışı
uçtan uca tamamlayabilir (self-approval SERBEST — owner kararı, ASM-0016).

## Kurulum

```powershell
# apps/web dizininde
npm install
Copy-Item .env.local.example .env.local   # .env.local GIT'E GİRMEZ
# .env.local içine gerçek Supabase değerlerini girin (aşağıya bakın)
```

## Komutlar (apps/web dizininden)

```powershell
npm run dev            # geliştirme sunucusu (http://localhost:3000)
npm run build          # production build
npm run start          # production sunucusu
npm run lint           # ESLint
npm run typecheck      # tsc --noEmit (strict)
npm run test           # Vitest
npm run test:coverage  # Vitest + v8 coverage
```

## `.env.local` alanları

| Değişken | Görünürlük | Açıklama |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | public | Supabase proje URL'i. Eksikse build/render bozulmaz; auth kontrollü "yapılandırılmamış" mesajı verir. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | public | Publishable (anon) key — tarayıcıya gidebilen **tek** anahtar. |
| `FLOWPILOT_API_BASE_URL` | **server-only** | FastAPI taban adresi. `NEXT_PUBLIC_` öneki **yoktur** — browser bundle'a girmez. |
| `NEXT_PUBLIC_APP_URL` | public | Auth callback URL'inin türetildiği public adres. |

**Yasak:** `SUPABASE_SERVICE_ROLE_KEY`, JWT secret veya herhangi bir Supabase gizli anahtarı bu uygulamada **kullanılmaz ve `.env.local`'a yazılmaz**. Frontend yalnız **publishable key** kullanır (ADR-005). Gerçek değerler commit edilmez; `.env.local` `.gitignore`'dadır.

## Mimari

### Supabase yalnız authentication (ADR-005)

Browser'dan **hiçbir Supabase business/database tablosuna erişilmez**. FlowPilot verisi **yalnız FastAPI** üzerinden yönetilir. Supabase yalnız kimlik doğrular ve access token üretir.

### SSR cookie/session (@supabase/ssr)

- [`lib/supabase/client.ts`](src/lib/supabase/client.ts) — browser client (yalnız client component).
- [`lib/supabase/server.ts`](src/lib/supabase/server.ts) — server client (Server Component / Action / Route Handler).
- [`lib/supabase/proxy.ts`](src/lib/supabase/proxy.ts) + [`proxy.ts`](src/proxy.ts) — her istekte session yeniler, korumalı yolları uygular.

Cookie adapter'ı güncel **toplu API** (`getAll`/`setAll`) kullanır; deprecated tekil `get`/`set`/`remove` **yoktur**. Korumalı yollarda **doğrulanmış claims** (`getClaims()`, JWT imzası kontrol edilir) kullanılır — yalnız session cookie'sinin varlığına güvenilmez.

**Korumalı:** `/onboarding/*`, `/dashboard`, `/organizations/*`, `/purchase-requests/*`, `/tasks/*`. **Açık:** `/login`, `/signup`, `/auth/*`, statik dosyalar.

### Login / Signup akışı

Server action'lar ([`features/auth/actions.ts`](src/features/auth/actions.ts)):

- `signInAction` — `signInWithPassword`; başarıda `/dashboard` (context çözümü orada: 0 org → onboarding, çok org → seçim). Hata **tek generic mesaj** (kullanıcı var/yok **sızdırılmaz**).
- `signUpAction` — `signUp` (callback `/auth/callback`); oturum hemen açılırsa `/dashboard`, aksi halde `/auth/check-email`. Var olan kullanıcıyı **sızdırmayan** generic mesaj.
- `signOutAction` — oturumu kapatır, `/login`.

Şifreler hiçbir state/log/debug çıktısına yazılmaz.

### FastAPI server action akışı

[`lib/api/flowpilot-api.ts`](src/lib/api/flowpilot-api.ts) **server-only**'dir (`import "server-only"` — client bundle sızması derleme anında engellenir):

1. Server, Supabase server client ile session'ı alır.
2. Session'daki access token **yalnız FastAPI'ye iletmek için** okunur.
3. Session'daki user nesnesi backend authorization kararı için **kullanılmaz**.
4. FastAPI token'ı kendi JWT adapter'ıyla **yeniden doğrular**.
5. Token browser'a, form state'e veya log'a **dönmez**.

Native `fetch`, `cache: "no-store"`, kontrollü timeout (10 sn), **otomatik retry yok**. Yanıt **Zod** ile doğrulanır (kör güven yok). HTTP eşlemeleri: `201` → başarı; `401` → yeniden giriş; `422` → güvenli alan hatası; `503` → "kimlik doğrulama servisine erişilemiyor"; `500`/bozuk gövde/timeout → kullanıcı-dostu genel hata. Backend teknik detayı kullanıcıya **gösterilmez**.

> **TODO (packages/contracts):** Şu an tek endpoint için küçük, lokal transport tipleri kullanılıyor. OpenAPI'den üretilen TypeScript client `packages/contracts` altında gelecekte oluşturulacak — **paralel bir business model source-of-truth kurulmadı**.

### Organization onboarding

[`features/organizations/actions.ts`](src/features/organizations/actions.ts) `createOrganizationAction`: Zod ön-doğrulama (nihai kaynak backend), server-side token, FastAPI çağrısı, typed sonuç. **Actor/owner/tenant ID form alanı değildir** — kimlik yalnız doğrulanmış oturumdan gelir. Başarıda yeni organizasyon **aktif org cookie'sine** yazılır.

### Aktif organizasyon context'i

Aktif organizasyon seçimi **server-side** yönetilir:

- Cookie: **`flowpilot_active_organization`** — HttpOnly, SameSite=Lax, Secure(prod), Path=/, **yalnız org UUID** taşır. **Authorization kaynağı DEĞİLDİR.**
- Her istekte backend `GET /v1/me/organizations` ile membership **yeniden doğrulanır** (actor-scoped RLS). Kullanıcı rastgele bir UUID yazsa bile aktif üyeliğinde yoksa context çözülmez.
- Yönlendirme (SAF karar: [`active-organization.ts`](src/features/organizations/active-organization.ts)): 0 org → `/onboarding/organization`; tek org → otomatik seçim; çok org → `/organizations/select`; cookie stale ise **yok sayılır** → yeniden seçim.
- IO + yönlendirme [`context.ts`](src/features/organizations/context.ts) (server-only); seçim [`select-actions.ts`](src/features/organizations/select-actions.ts).

### FlowPilot API kaynakları (server-only)

[`lib/api/http.ts`](src/lib/api/http.ts) + [`lib/api/resources.ts`](src/lib/api/resources.ts): typed fonksiyonlar — `listMyOrganizations`, `createPurchaseRequest`, `listMyPurchaseRequests`, `getPurchaseRequest`, `getPurchaseRequestTimeline`, `getMyTaskInbox`, `decideApprovalTask`. Her biri Zod ile doğrular, snake_case → camelCase eşler. Onay kararında **Idempotency-Key** server tarafında (`crypto.randomUUID`) üretilir; kullanıcıdan istenmez, token/actor'dan türetilmez. Para TL metninden **float üretmeden** kuruşa çevrilir ([`lib/money.ts`](src/lib/money.ts)); **backend nihai doğrulama kaynağıdır**. Karar sonrası **optimistic UI YOK** — server-confirmed state beklenir.

## Sayfalar

`/` (yönlendirir) · `/login` · `/signup` · `/auth/*` · `/onboarding/organization` · `/organizations/select` · `/dashboard` · `/purchase-requests` (Taleplerim) · `/purchase-requests/new` · `/purchase-requests/[id]` (detay + timeline) · `/tasks/inbox` (onay kutusu). `/dashboard` sonrası tümü korumalı **ve** aktif organizasyon gerektirir.

Arayüz **Türkçe**, açık temalı, B2B SaaS; erişilebilir (semantic nav + `aria-current`, label'lar, `aria-live`, focus görünürlüğü, renk-dışı durum, yeterli kontrast). Durum/rol/timeline event'leri Türkçe etikete eşlenir; backend'in **döndürmediği** değer uydurulmaz (güvenli fallback). UUID ana arayüzde gösterilmez. Dark mode ve animasyon kütüphanesi **yok**.

## Test / kalite

Vitest + Testing Library. **105 test; coverage ~%97 statements/lines, ~%93 branches** (eşik %80). Kapsam: aktif organizasyon karar mantığı (0/1/çok org, stale cookie), para parsing (float üretmediği kanıtlanır), durum/rol/timeline etiket eşlemeleri + bilinmeyen değer fallback, API client (Bearer, aktif org URL, Zod reddi, 401/404/409/422/503/timeout eşlemeleri, Idempotency-Key header, token sızmaması), form davranışları (pending çift-submit engeli, hata görünürlüğü, kimlik alanı yokluğu, 409 çakışma mesajı).

**Coverage kapsamı dışı (bilinçli):** server action'lar ve Supabase SDK wiring'i (`lib/supabase/{client,server}.ts`, `updateSession`) — bunları birim testte doğrulamak tüm SDK'yı mock'lamak (kodu değil mock'u test etmek) demek olur. Bunlar `typecheck` + `build` + (canlı) smoke ile doğrulanır.

`npm audit --audit-level=high`: **temiz** (0 high/critical). Not: Next transitive'i `postcss` üzerinden **2 moderate** advisory taşır; tek "düzeltme" Next'i kırıcı biçimde düşürmektir (yapılmadı). CSS stringify XSS'i yalnız güvenilmeyen CSS işlense geçerlidir — kabul edildi.

Bu kapılar CI'da otomatik koşar ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) `frontend` job) ve local'de [`scripts/release_verify.ps1`](../../scripts/release_verify.ps1) ile toplu çalıştırılabilir.

## Canlı Supabase durumu ✅ Doğrulandı (2026-07-15)

Canlı Supabase kabul testi **geçti** (OQ-009/OQ-010 — kapandı; bkz. [docs/open-questions.md](../../docs/open-questions.md)):

- Gerçek signup → e-posta doğrulaması → gerçek login akışı canlı Supabase projesiyle uçtan uca çalıştı.
- Onboarding'den oluşturulan test organizasyonu, gerçek ES256 access token ile `POST /v1/organizations` → **201** döndürdü; tenant + aktif owner membership **aynı transaction'da** oluştu.
- Credential'lar yalnız git-ignored `.env.local` içindedir; bu belgeye ve repository'ye **hiçbir değer kopyalanmaz**.
- Build, test, lint, typecheck credential'sız da tam çalışır; Supabase yapılandırılmamışsa auth submit kontrollü "yapılandırılmamış" mesajı gösterir.

## Bu aşamada BULUNMAYANLAR (bilinçli)

Rol yönetimi UI/API'si, kullanıcı daveti, team/department, tam RBAC, separation-of-duties
enforcement (self-approval MVP'de SERBEST), changes_requested, notification delivery,
dosya/MinIO, analytics, workflow designer, dark mode. Dashboard sayımları **yalnız**
kullanıcının kendi talep listesi + inbox'ından türetilir (sahte KPI/yeni analytics
endpoint'i yok).

## Sonraki aşama

Canlı uçtan uca kabul testi → hata düzeltmeleri → deployment/pilot hazırlığı.
