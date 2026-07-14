# packages/testing — Test Altyapısı

Test yazmayı kolaylaştıran paylaşılan araçlar.

## İçerik (üretilecek)

- **Fake adapter'lar** — `AuthProviderPort`, `FileStoragePort`, `NotificationChannelPort`, `MalwareScanPort`, `WorkflowRuntimePort`
- **Fake clock** — DST/timezone testleri için zaman kontrolü
- **Deterministik `IdGenerator`**
- **Fixture'lar** — tenant, membership, workflow version, purchase request
- **Cross-tenant test harness'ı** — iki tenant kurup IDOR/BOLA senaryolarını çalıştıran ortak altyapı

## Kritik kural

**Fake adapter ve gerçek adapter AYNI contract test setini geçer.** Bir story yalnızca fake adapter'a karşı test edilerek **"done" sayılamaz** — gerçek boundary (DB, transaction, worker) en az bir integration testte doğrulanır.

Workflow runtime'ı e2e testte **tamamen mock'lamak YASAKTIR** (PRD §39 anti-pattern'i).

Fake adapter production konfigürasyonunda **kullanılamaz** (build-time/config guard).

## Durum

Boş.
