# apps/backend/tests — Backend Testleri

Tek pytest rootdir: `apps/backend`. Testler **`src/` içinde değildir** — src-layout sayesinde testler **kurulmuş** paketi import eder; testler distribution'a sızmaz ve "yerelde çalışıyor, Docker'da import hatası" sınıfı hatalar yerelde yakalanır ([ADR-009](../../../docs/adr/ADR-009-python-physical-layout.md)).

## Yerleşim

| Dizin | Kapsam |
|---|---|
| [`unit/`](unit/README.md) | Domain, policy, condition evaluator, `Money`, state machine — dış bağımlılık yok |
| [`integration/`](integration/README.md) | Gerçek PostgreSQL: transaction, RLS, outbox, idempotency, timer, concurrency |
| [`contract/`](contract/README.md) | Port fake ↔ gerçek adapter aynı seti geçer; OpenAPI/AsyncAPI |
| [`security/`](security/README.md) | Cross-tenant (IDOR/BOLA) ve negatif authorization suite'i |

Tarayıcı e2e testleri burada **değil**, repo kökündeki [`tests/e2e/`](../../../tests/e2e/README.md) altındadır (web + API birlikte sürülür).

## Test altyapısı (üretilecek)

- **Fake adapter'lar** — `AuthProviderPort`, `FileStoragePort`, `NotificationChannelPort`, `MalwareScanPort`, `WorkflowRuntimePort`
- **Fake clock** — DST/timezone testleri için zaman kontrolü
- **Deterministik `IdGenerator`**
- **Fixture'lar** — tenant, membership, workflow version, purchase request
- **Cross-tenant harness** — iki tenant kurup IDOR/BOLA senaryolarını çalıştıran ortak altyapı

## Bozulamaz kurallar

- **Failing test silinemez, `skip`/`xfail` ile geçilemez.** Test kırmızıysa: ya kod hatalıdır ve düzeltilir, ya da kabul kriteri hatalıdır ve **açıkça, gerekçesiyle** güncellenir.
- **Fake adapter ve gerçek adapter AYNI contract test setini geçer.** Bir story yalnızca fake'e karşı test edilerek "done" sayılamaz.
- **Workflow runtime e2e/integration testinde tamamen mock'lanamaz** (PRD §39 anti-pattern'i).
- Fake adapter **production konfigürasyonunda kullanılamaz** (config guard).
- Tenant verisine dokunan **her** story'de cross-tenant testi zorunludur.
- Yetki kontrolü olan **her** endpoint'te negatif authorization testi zorunludur.
- Testler birbirinden bağımsızdır; sıraya bağımlı test YASAK.

## Durum

Boş.
