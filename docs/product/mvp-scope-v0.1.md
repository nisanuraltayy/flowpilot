# FlowPilot — MVP Kapsamı v0.1 (Owner-Approved)

- **Durum:** ✅ **Owner-approved — BAĞLAYICI**
- **Tarih:** 2026-07-14
- **Onaylayan:** Nisa Nur Altay (product owner)
- **Sürüm:** v0.1

---

## 0. Bu dokümanın statüsü

> **Bu doküman, PRD'deki geniş MVP tanımının (PRD §7.1 ve §24) ÜZERİNDE önceliğe sahiptir.**

[PRD](../FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md) **değiştirilmemiştir ve değiştirilmeyecektir**. PRD; araştırma, uzun vadeli ürün vizyonu ve normatif mühendislik sözleşmesi olarak geçerliliğini korur. Ancak **teslim edilecek kapsam** bu dosyadan okunur.

Kaynak öncelik sırası (CLAUDE.md §2) buna göre okunur:

1. Güvenlik, tenant izolasyonu, hukuki zorunluluklar
2. Kabul edilmiş ADR'ler
3. **Bu doküman (owner-approved MVP kapsamı)** ← kapsam çatışmasında bağlayıcı
4. PRD'nin MUST / MUST NOT kuralları (mühendislik sözleşmesi olarak tam geçerli)
5. Sözleşmeler, invariant'lar, story kabul kriterleri

**Ayrım netleştirmesi:** PRD'nin **mühendislik kuralları** (invariant'lar, anti-pattern'ler, state machine'ler, güvenlik gereksinimleri, §32–§48) tamamen bağlayıcıdır ve bu doküman onları gevşetmez. Bu doküman yalnızca **hangi özelliklerin ne zaman teslim edileceğini** belirler.

---

## 1. Sürüm kademeleri

| Kademe | Tanım |
|---|---|
| **Local MVP** | Bu dokümanın §2'sindeki kapsam. Uçtan uca çalışan satın alma süreci. Pilot müşteriye açılmaz. |
| **Pilot-ready** | Local MVP + §4'teki pilot çıkış kriterleri. Gerçek müşteri verisi işlenmeden önce zorunlu. |
| **Sonraki** | PRD'nin geri kalan MVP/P1/P2 hedefleri. |

---

## 2. Gerçek MVP kapsamı (Local MVP)

Aşağıdakiler **kapsamdadır** ve teslim edilir:

### Platform ve güvenlik
- **Authentication boundary** — managed provider (Supabase Auth, [ADR-005](../adr/ADR-005-authentication-boundary.md)) `AuthProviderPort` arkasında
- **Tenant ve organization** — tenant aggregate, TenantContext
- **Membership ve RBAC** — üyelik yaşam döngüsü, rol/permission katalogu, merkezi authorization policy
- **Tenant isolation** — application scope + PostgreSQL RLS + cross-tenant regression suite ([ADR-006](../adr/ADR-006-postgresql-tenant-isolation.md))
- **Audit log** — append-only, business transaction ile atomik

### Süreç
- **Satın alma formu** — ürün/hizmet adı, kategori, tutar (minor unit + currency), gerekçe, isteğe bağlı dosya
- **Workflow publish ve immutable versioning** — draft → validate → publish → hash'li immutable version
- **Workflow node seti (yalnızca 6):**
  1. `Start`
  2. `Form`
  3. `Condition`
  4. `Sequential Approval`
  5. `Notification`
  6. `End`
- **Task / inbox** — human task aggregate, assignee resolution, kişisel inbox
- **In-app notification** — provider-neutral port, yalnız in-app adapter
- **Instance timeline** — human/system aksiyon ayrımı, koşul gerekçesinin görünürlüğü

### Altyapı
- **Transactional outbox** ([ADR-007](../adr/ADR-007-transactional-outbox.md))
- **Idempotent PostgreSQL worker** — polling dispatcher, idempotent inbox, bounded retry
- **Temel operasyon dashboard'u** — açık talep, bekleyen onay, tamamlanan/reddedilen sayaçları

### Doğrulama
- **Satın alma E2E demo** — giriş → organizasyon/membership → talep → koşul → sıralı onay → state transition → bildirim → audit → timeline

---

## 3. Local MVP kapsamı DIŞI

Aşağıdakiler **implemente edilmez**. Bir agent bunları "mantıklı olduğu için" ekleyemez.

### Workflow
- Parallel split / join
- Quorum approval (M/N)
- Sub-workflow
- Webhook node
- Script node
- AI node
- DMN karar tabloları
- **Görsel workflow builder canvas**
- Wait / Timer node (persisted timer altyapısı spike'ta kanıtlanır; **node olarak sunulmaz**)

### Onay
- Delegation / vekâlet
- Yedek onaycı
- SLA, hatırlatma, çok seviyeli eskalasyon
- Toplu onay
- E-posta üzerinden tek tık onay

### Bildirim ve entegrasyon
- **E-posta bildirimi** → *pilot-ready kapsamında* (§4)
- Slack / Teams / SMS / push
- Digest, bildirim tercihleri
- Outbound webhook, API key, connector'lar

### Diğer
- AI özellikleri (haftalık özet, doğal dilden workflow taslağı, RAG)
- Gelişmiş analitik, cycle time, darboğaz analizi, CSV export
- Billing, entitlement, kota (**sınır tasarımda korunur, implemente edilmez**)
- İzin ve çalışan onboarding şablonları (yalnız **satın alma** şablonu vardır)
- Arama (MVP'de PostgreSQL full-text kararı verildi ancak ilk dilimde ekran yok)
- SSO / SCIM / MFA politikası
- **Gerçek malware tarama entegrasyonu** → *pilot-ready kapsamında* (§4)

---

## 4. Pilot-ready çıkış kriterleri

Local MVP tamamlandıktan sonra, **gerçek müşteri verisi işlenmeden önce** zorunlu:

| # | Kriter | Neden |
|---|---|---|
| 1 | **E-posta bildirimi** (in-app'e ek kanal) | Onaycı uygulamaya girmezse bekleyen onayı fark etmez; ürünün çözmeye çalıştığı gecikme problemi geri gelir |
| 2 | **Zararlı dosya taraması** — gerçek entegrasyon | Tarama olmadan bir kullanıcının yüklediği zararlı dosya aynı tenant'ta indirilebilir. **Zorunlu güvenlik çıkış kriteri** |
| 3 | Backup / restore testi yapılmış | PRD §24 |
| 4 | Güvenlik gözden geçirmesi — açık critical/high finding yok | PRD §24 |
| 5 | Cross-tenant izolasyon testleri tam yeşil | PRD §24 |

---

## 5. Port zorunlulukları (MVP'de tasarlanır, adapter sonra gelir)

MVP'de **portu tasarlanır**, ancak yalnız belirtilen adapter uygulanır. Bu, sonraki kanalın/sağlayıcının domain kodunu değiştirmeden eklenmesini sağlar.

| Port | MVP'de uygulanan adapter | Sonra eklenecek |
|---|---|---|
| `AuthProviderPort` | Supabase Auth adapter + fake adapter | (Provider değişimi) |
| `NotificationChannelPort` | **Yalnız in-app** | E-posta (pilot-ready), Slack/Teams (sonra) |
| `MalwareScanPort` | **Yalnız no-op / stub** — `scan_status` alanı ve indirmeyi engelleyen kapı hazır | Gerçek tarama servisi (pilot-ready) |
| `FileStoragePort` | S3-compatible (local: MinIO) | Production sağlayıcısı (LOCK-006) |
| `WorkflowRuntimePort` | Custom PostgreSQL-backed (spike şartına bağlı) | Temporal (spike başarısızsa) |
| `ClockPort`, `IdGeneratorPort` | System / fake | — |

**Kural:** `NotificationChannelPort` ve `MalwareScanPort`, MVP'de tek adapter'ları olsa bile **kanal-nötr / sağlayıcı-nötr** tasarlanır. E-posta veya tarama eklemek bir adapter eklemek olmalıdır, bir refactor değil.

---

## 6. Satın alma onay eşikleri (geçici ürün varsayımı)

Demo ve ilk dikey dilim için varsayılan eşikler:

| Tutar | Onay zinciri |
|---|---|
| < 10.000 TL | Ekip yöneticisi |
| 10.000 – 50.000 TL | Ekip yöneticisi → Finans |
| > 50.000 TL | Ekip yöneticisi → Finans → Genel Müdür |

**MUST NOT:** Bu değerler ve kademe sayısı **domain koduna hard-code edilemez**. Eşikler, workflow definition içindeki `Condition` node koşullarından gelir; onay zinciri `Sequential Approval` node config'inden okunur. Eşiği değiştirmek **yeni bir workflow version yayınlamak** olmalıdır — kod değişikliği değil.

Bunlar **doğrulanmamış ürün varsayımıdır** — bkz. [ASM-0001](../assumptions.md).

**Tasarım sonucu:** Sequential Approval node'u **1, 2 veya 3 adımlı** zincirleri desteklemelidir (kademe sayısı config'ten gelir; sabit değildir).

---

## 7. Kapsam değişikliği kuralı

Bu dokümanın kapsamı **yalnız owner tarafından** değiştirilir. Agent:

- Kapsam dışı bir özelliği "mantıklı" veya "zaten kolay" diyerek ekleyemez.
- Kapsam içi bir özelliği "gereksiz" diyerek çıkaramaz.
- Bir kapsam çatışması fark ederse `docs/open-questions.md` içine `OQ-xxx` açar ve durur.

Kapsam genişletme talebi geldiğinde: yeni bir kapsam sürümü (`mvp-scope-v0.2.md`) yazılır; bu dosya silinmez.

---

## 8. İzlenebilirlik

| Kapsam maddesi | Epic |
|---|---|
| Authentication boundary | E01 |
| Tenant ve organization | E02 |
| Membership ve RBAC | E03 |
| Tenant isolation | E04 |
| Satın alma formu | E05, E06 |
| Workflow publish ve immutable versioning | E07 |
| Workflow runtime (6 node) | E08 (spike), E09 (core) |
| Sequential Approval | E10 |
| Task / inbox | E11 |
| In-app notification | E12 |
| Audit log ve instance timeline | E13 |
| Temel operasyon dashboard'u | E14 |
| Satın alma E2E demo | E15 |
| Transactional outbox + idempotent worker | E09 (FP-E09-004, FP-E09-005) |

Backlog: [epics.yaml](../backlog/epics.yaml) · [vertical-slice-purchase-request.yaml](../backlog/vertical-slice-purchase-request.yaml)
