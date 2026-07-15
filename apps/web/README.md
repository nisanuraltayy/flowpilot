# apps/web — Kullanıcı Uygulaması (Next.js)

FlowPilot web arayüzü. Next.js 16 (App Router) + React 19 + TypeScript (strict) + Tailwind CSS v4 (ADR-002, ADR-009).

Bu aşamada teslim edilen ilk kullanıcı akışı:

```text
Kayıt ol → (gerekliyse e-posta doğrulama) → Giriş yap → oturum cookie'si
  → Organizasyon adı → Next.js server action → FastAPI'ye Bearer token
  → POST /v1/organizations → organizasyon + aktif owner membership → başarı ekranı
```

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

**Korumalı:** `/onboarding/*`, `/dashboard`. **Açık:** `/login`, `/signup`, `/auth/*`, statik dosyalar.

### Login / Signup akışı

Server action'lar ([`features/auth/actions.ts`](src/features/auth/actions.ts)):

- `signInAction` — `signInWithPassword`; başarıda `/onboarding/organization`. Hata **tek generic mesaj** (kullanıcı var/yok **sızdırılmaz**).
- `signUpAction` — `signUp` (callback `/auth/callback`); oturum hemen açılırsa onboarding, aksi halde `/auth/check-email`. Var olan kullanıcıyı **sızdırmayan** generic mesaj.
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

[`features/organizations/actions.ts`](src/features/organizations/actions.ts) `createOrganizationAction`: Zod ön-doğrulama (nihai kaynak backend), server-side token, FastAPI çağrısı, typed sonuç. **Actor/owner/tenant ID form alanı değildir** — kimlik yalnız doğrulanmış oturumdan gelir; Authorization header browser'da **oluşturulmaz**.

## Sayfalar

`/` (session'a göre yönlendirir) · `/login` · `/signup` · `/auth/check-email` · `/auth/error` · `/auth/callback` (code→session, open-redirect korumalı) · `/onboarding/organization` (korumalı) · `/dashboard` (korumalı, minimal shell).

Arayüz **Türkçe**, açık temalı, B2B SaaS; erişilebilir (label'lar, `aria-live`, focus görünürlüğü, renk-dışı durum). Dark mode ve animasyon kütüphanesi bu aşamada **yok**.

## Test / kalite

Vitest + Testing Library. **49 test, coverage %100 statements/functions/lines, %98.5 branches** (birim-test edilebilir saf mantık: şemalar, redirect, API client eşlemeleri, form davranışları — pending disabled, hata görünürlüğü, şifre sızmaması, actor enjekte edilememesi).

**Coverage kapsamı dışı (bilinçli):** server action'lar ve Supabase SDK wiring'i (`lib/supabase/{client,server}.ts`, `updateSession`) — bunları birim testte doğrulamak tüm SDK'yı mock'lamak (kodu değil mock'u test etmek) demek olur. Bunlar `typecheck` + `build` + (canlı) smoke ile doğrulanır.

`npm audit --audit-level=high`: **temiz** (0 high/critical). Not: Next transitive'i `postcss` üzerinden **2 moderate** advisory taşır; tek "düzeltme" Next'i kırıcı biçimde düşürmektir (yapılmadı). CSS stringify XSS'i yalnız güvenilmeyen CSS işlense geçerlidir — kabul edildi.

## Canlı Supabase durumu

Gerçek Supabase projesi/credential **henüz yok**. Bu yüzden:

- Build, test, lint, typecheck **tam çalışır**; production build başarılı, `/login` ve `/signup` render edilir (smoke ile doğrulandı), korumalı yollar `/login`'e yönlendirir.
- Auth submit edildiğinde kontrollü "Kimlik doğrulama henüz yapılandırılmamış" mesajı gösterilir.
- **Canlı signup/login ve gerçek `POST /v1/organizations` uçtan uca kabul testi YAPILMADI** — açık konu: [docs/open-questions.md](../../docs/open-questions.md) OQ-009/OQ-010. Gerçek `SUPABASE_URL` + publishable key sağlandığında test edilebilir.

## Sonraki aşama

**Purchase Request dikey dilimi:** form → tutar eşiği koşulu → sıralı onay → görev inbox → audit timeline. Dashboard şu an **gerçek business verisi içermez** (sahte liste/istatistik yok).
