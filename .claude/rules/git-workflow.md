# Git ve Pull Request Kuralları

Bağlayıcı kaynak: PRD §33.2, §45.4, §45.5, §48.3.

> **Mevcut durum:** Bu dizin henüz bir git repository'si **değildir**. Agent `git init` çalıştırmaz; repository başlatma owner onayına bağlıdır (Epic E00). Aşağıdaki kurallar repository başlatıldığı andan itibaren geçerlidir.

---

## 1. Branch

- `main` korumalı branch'tir. Doğrudan push YASAK.
- Branch adı story ID'si ile başlar:
  - `feat/FP-E06-003-purchase-request-submission`
  - `fix/FP-E10-004-duplicate-approval`
  - `spike/FP-E08-002-runtime-determinism`
  - `docs/FP-E00-002-adr-process`
- Bir branch **tek story** taşır.

---

## 2. Commit

- Conventional Commits: `type(scope): açıklama`
  - `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `spike`, `perf`
  - Scope: modül adı (`approval`, `workflow-runtime`, `organization`, ...)
- Commit mesajında story ID bulunur: `feat(approval): sıralı adım aktivasyonu (FP-E10-002)`
- Commit atomiktir; derlenmeyen veya testi kırık ara commit `main`'e gitmez.

**YASAK:**

- `--no-verify` ile hook bypass etmek
- Git history rewrite (`push --force`, `rebase` ile paylaşılan geçmişi değiştirmek)
- Secret, `.env`, credential veya kişisel veri commit etmek
- Generated artifact'i elle düzenleyip commit etmek
- Lockfile'ı dependency değişmediği hâlde commit etmek

---

## 3. Pull request

**Bir PR = bir ana amaç.** Unrelated refactor, formatting veya "yolda gördüm" düzeltmeleri **ayrı PR**.

- 400–600 satırı aşan anlamlı diff (generated code hariç) **bölme adayı** olarak işaretlenir.
- PR açıklaması AGENTS.md §8'deki teslim raporu formatını kullanır.

### PR merge edilemez — engelleyici koşullar

- Kalite kapılarından biri kırmızı (format, lint, typecheck, unit, integration, contract, migration, secret scan)
- Tenant verisine dokunuyor ama **cross-tenant testi yok**
- Yetki kontrolü var ama **negatif authorization testi yok**
- API / event / migration değişmiş ama **sözleşme dokümanı güncellenmemiş**
- Yeni permission eklenmiş ama merkezi katalogda yok
- TODO, placeholder, fake success veya commented-out kod var
- Açık **critical/high** security finding var
- Yeni dependency gerekçesiz (lisans, bakım durumu, güvenlik, alternatifler, removal cost belirtilmemiş)
- Frontend'te error / empty / loading / permission-denied state'i eksik

---

## 4. Dokümantasyon zorunluluğu

Aşağıdaki değişiklikler **doküman güncellemesi olmadan merge edilemez** (PRD §33.2):

- Yeni endpoint veya breaking API değişikliği → OpenAPI
- Yeni event veya payload değişikliği → AsyncAPI / event katalogu
- Yeni modül / bounded context → `docs/architecture/domain-boundaries.md`
- Yeni workflow node türü → ADR + workflow definition schema (MVP node seti dışına çıkmak owner kararıdır)
- Yeni rol veya permission → permission katalogu
- Yeni veri sınıfı, yeni provider, yeni environment variable
- Güvenlik kontrolünü etkileyen değişiklik
- Mimari karar değişikliği → yeni ADR (mevcut ADR **silinmez**, `Superseded by ADR-xxx` olarak işaretlenir)

---

## 5. Self-review checklist

Agent PR açmadan önce kendi diff'ini okur ve şunları doğrular:

- [ ] Diff yalnız story scope'undaki dosyaları içeriyor
- [ ] Domain katmanında framework/SDK importu yok
- [ ] Cross-module doğrudan DB yazımı yok
- [ ] Generic repository yok
- [ ] `eval`/`exec` yok
- [ ] Para float değil (minor unit + currency)
- [ ] Tüm timestamp'ler UTC
- [ ] Tenant verisi taşıyan yeni tabloda `tenant_id` + RLS var
- [ ] Yeni async handler idempotent
- [ ] Retry bounded
- [ ] Secret yok, `.env` yok
- [ ] Failing/skipped test yok
- [ ] Career Copilot'a ait hiçbir dosya değişmedi

---

## 6. Repository kapsamı

Bu repository **yalnızca FlowPilot**'a aittir. Career Copilot dosyaları bu repository'ye eklenmez, oradan kopyalanmaz, o klasöre yazılmaz.
