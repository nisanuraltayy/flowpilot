# AGENTS.md — FlowPilot AI Coding Agent Sözleşmesi

Bu dosya, herhangi bir AI coding agent'in FlowPilot repository'sinde çalışma sözleşmesidir. Agent'e özgü kısa günlük talimat için [CLAUDE.md](CLAUDE.md) dosyasına bakın; ikisi çelişirse **bu dosya bağlayıcıdır**.

Normatif dil (PRD §32):

- **MUST / ZORUNLU:** Uygulanmadığında story tamamlanmış kabul edilemez.
- **MUST NOT / YASAK:** Mimari veya güvenlik ihlalidir.
- **SHOULD / ÖNERİLEN:** Aksi seçiliyorsa ADR veya story notunda gerekçe yazılır.
- **MAY / OPSİYONEL:** Ürün ihtiyacına göre uygulanabilir.

---

## 1. Proje bağlamı

FlowPilot, KOBİ'ler için çok kiracılı iş akışı ve onay platformudur. Career Copilot'tan **tamamen bağımsızdır**; o repository'nin kodu, şeması veya konfigürasyonu bu proje için referans değildir ve o klasöre dokunulmaz.

- Çalışma modeli: solo developer + AI coding agent
- Mimari: modüler monolit (ADR-003)
- Repository: monorepo (ADR-008)
- Backend: Python + FastAPI + Pydantic + SQLAlchemy + Alembic (ADR-001)
- **Python yerleşimi:** tek distribution `flowpilot-backend` (`apps/backend`), tek import kökü `flowpilot`, bounded context'ler `flowpilot.modules.<snake_case>`, iki composition root `flowpilot.api` ve `flowpilot.worker` (ADR-009)
- Frontend: Next.js + TypeScript (ADR-002)
- Veritabanı: PostgreSQL; tenant izolasyonu application scope + RLS (ADR-006)
- Asenkron: transactional outbox + PostgreSQL-backed polling worker (ADR-007)
- Workflow runtime: `WorkflowRuntimePort` arkasında custom PostgreSQL-backed runtime; **spike 12/12 geçti, ADR-004 Accepted, LOCK-003 kapandı** (2026-07-19). Production implementation (E09) henüz yazılmadı
- Authentication: **Supabase Auth** — yalnız kimlik doğrulama (ADR-005). Organization, membership, manager hierarchy, RBAC, authorization ve tenant modeli **FlowPilot domain'inde ve FlowPilot'ın PostgreSQL'inde**. Domain katmanı Supabase SDK'sına **bağımlı olamaz**; entegrasyon yalnız `AuthProviderPort` adapter'ındadır.

**Teslim kapsamı için bağlayıcı doküman:** [docs/product/mvp-scope-v0.1.md](docs/product/mvp-scope-v0.1.md) (owner-approved; PRD §7.1/§24'ün üzerinde). PRD değiştirilmez; mühendislik kuralları (invariant, anti-pattern, state machine, güvenlik) tam olarak bağlayıcı kalır.

**Gerçek MVP node seti:** `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End`.
Kapsam dışı: parallel split/join, quorum approval, sub-workflow, webhook node, script node, AI node, DMN, görsel workflow canvas.
Pilot-ready (MVP dışı, ama **portu şimdiden tasarlanır**): e-posta bildirimi (`NotificationChannelPort`), gerçek malware taraması (`MalwareScanPort`).

**İlk dikey dilim:** Satın alma talebi süreci — giriş → organizasyon/membership → talep oluşturma → koşul değerlendirme → sıralı onay → state transition → in-app notification → audit → timeline. Duplicate approval, duplicate event ve cross-tenant erişim engellenir.

---

## 2. Zorunlu çalışma sırası

Agent her görevde **bu sırayı** izler:

1. **İlgili PRD bölümünü oku.** [docs/FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md](docs/FlowPilot_Teknik_PRD_v0.2_Agent_Ready.md)
2. **Aktif ADR'leri oku.** [docs/adr/README.md](docs/adr/README.md)
3. **Story dosyasını oku.** [docs/backlog/](docs/backlog/epics.yaml)
4. **Karar kilidi var mı kontrol et.** Açık kilit varsa üretim kodu **yazma**; spike, ADR veya port sözleşmesi üret.
5. **Büyük değişiklikten önce plan üret.** Plan; etkilenen modüller, sözleşme etkisi, migration etkisi, test etkisi ve riskleri içerir.
6. **Bir story dışına taşma.** Story'de olmayan özellik, refactor veya "mantıklı olduğu için" eklenen scope YASAK.
7. **Bir pull request içinde tek ana amaç uygula.**
8. **API, event veya migration değiştiğinde sözleşmeleri güncelle.** Sözleşme güncellenmeden merge edilemez.
9. **Tenant verisi kullanan kod için cross-tenant test yaz.**
10. **Authorization için negatif test yaz.** En az bir "yetkisiz aktör reddedilir" senaryosu zorunludur.
11. **Test, lint ve type-check geçmeden story'yi tamamlanmış sayma.**
12. **Güvenlik kontrolünü kapatma.** Hook bypass, `--no-verify`, test devre dışı bırakma YASAK.
13. **Bilinmeyen gereksinimi uydurma.**
14. **Varsayımı `ASM-xxxx` kimliğiyle [docs/assumptions.md](docs/assumptions.md) içine kaydet.**
15. **Owner kararı gerektiren konuyu `OQ-xxx` kimliğiyle [docs/open-questions.md](docs/open-questions.md) içine kaydet.**
16. **Secret veya kişisel veri commit etme.**
17. **Career Copilot klasörüne dokunma.**

---

## 3. Karar kilitleri

| Kilit | Konu | Durum | İzin verilen iş |
|---|---|---|---|
| LOCK-001 | Backend stack | KAPALI — ADR-001 | Üretim kodu serbest |
| LOCK-002 | Frontend stack | KAPALI — ADR-002 | Üretim kodu serbest |
| LOCK-003 | Workflow runtime | KAPALI — ADR-004 (spike 12/12 PASS, 2026-07-19) | Custom PostgreSQL-backed runtime `WorkflowRuntimePort` arkasında yazılabilir (E09). Production implementation henüz YOK; ADR-004 §Karar/3 tasarım kararlarına uyulur |
| LOCK-004 | Auth provider | KAPALI — ADR-005 (**Supabase Auth**) | Supabase yalnız `AuthProviderPort` adapter'ında. Supabase'in org/rol modeline bağımlılık YASAK. Supabase'in DB/RLS'i FlowPilot'ın operasyonel veritabanı olarak kullanılamaz. Entegrasyon **bootstrap onayından sonra** |
| LOCK-005 | Queue/worker | KAPALI — ADR-007 | Outbox + PostgreSQL polling worker |
| LOCK-006 | Hosting / veri bölgesi | AÇIK | Provider-neutral Docker. Provider'a özgü manifest YASAK |
| LOCK-007 | AI provider | AÇIK | MVP dışı. Gerçek AI entegrasyonu YASAK |
| LOCK-008 | Monorepo | KAPALI — ADR-008 | Monorepo |

Agent bir kilidi "popüler olduğu için" veya "daha önce kullanıldığı için" aşamaz.

---

## 4. Otonomi sınırları

**Agent bağımsız karar verebilir:**

- İsimlendirme ve küçük refactor
- Mevcut pattern'e uygun sınıf/fonksiyon ayrımı
- Test fixture oluşturma
- Error catalog içindeki kullanıcı mesajı metni
- Geri alınabilir index ekleme
- Mevcut dependency ile implementasyon tercihi

**Agent bağımsız karar VEREMEZ:**

- Tech stack seçimi veya değişimi
- Yeni dependency veya ücretli provider ekleme
- Yeni production secret
- Public API breaking change
- Permission veya tenant boundary gevşetme
- Veri retention değiştirme
- P0 scope'a yeni büyük özellik ekleme
- Migration ile veri silme
- Güvenlik testini kapatma
- Production deploy veya destructive komut

---

## 5. Belirsizlik davranışı

Agent akışı durdurup sürekli soru sormak yerine:

1. En güvenli ve **geri döndürülebilir** seçeneği belirler.
2. Varsayımı `docs/assumptions.md` içine `ASM-xxxx` olarak kaydeder.
3. Etki **yüksek ve geri döndürülemez** ise implementasyon yerine spike/ADR üretir ve `docs/open-questions.md` içine `OQ-xxx` açar.
4. Dış credential story'yi bloke ediyorsa fake adapter + contract test ile ilerler; gerçek entegrasyonu `blocked_external` olarak işaretler.

Varsayım formatı (PRD §33.3):

```yaml
- id: ASM-0001
  statement: "..."
  impact: low | medium | high
  reversible: true | false
  owner: product | engineering | security | legal
  status: unvalidated | validated | rejected
  validation_method: "..."
  expires_at: YYYY-MM-DD
  affected_stories: [FP-E00-001]
```

---

## 6. Değişiklik sınırı

- Bir story mümkün olduğunca **tek vertical slice** olmalıdır.
- 400–600 satırı aşan anlamlı diff **bölme adayı** olarak işaretlenir (generated code hariç).
- Unrelated formatting/refactor **ayrı PR**.
- Lockfile yalnız dependency gerçekten değiştiyse değişir.
- Generated artifact elle düzenlenmez.
- Migration dosyası silinip yeniden üretilmez.

---

## 6b. Import kuralları (ADR-009 — bağlayıcı)

1. **Domain katmanında FastAPI, SQLAlchemy, Supabase veya provider SDK importu YASAK.**
2. Bir bounded context, başka bir context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
3. Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden.
4. `flowpilot.api` ve `flowpilot.worker` **yalnız application sınırlarını** çağırır; iş mantığı içermezler.
5. **Adapter wiring yalnız composition root'ta** (`api/deps.py`, `worker/wiring.py`).
6. **`PYTHONPATH` hack'i YASAK** — editable install (`pip install -e apps/backend`).
7. Bounded context klasör adları **snake_case**; tireli ad YASAK.
8. **Aynı bounded context için ikinci source of truth YASAK.**

---

## 7. Tool ve komut güvenliği

Agent **MUST NOT**:

- Production veritabanına bağlanmak
- `DROP`, `TRUNCATE`, force reset veya git history rewrite çalıştırmak
- Secret dosyalarını commit etmek
- Güvenlik hook'unu bypass etmek veya `--no-verify` kullanmak
- Testleri global olarak devre dışı bırakmak
- Bilinmeyen script'i incelemeden çalıştırmak
- İnternetten indirilen binary'yi checksum/signature doğrulamadan kullanmak
- Career Copilot repository'sine veya klasörüne erişmek

---

## 8. Story teslim raporu

Her story sonunda PR açıklamasında bulunur:

```markdown
## Story
FP-Exx-000

## Yapılanlar
- ...

## Değiştirilen sözleşmeler
- OpenAPI: yes/no
- AsyncAPI: yes/no
- DB migration: yes/no
- Permissions: yes/no

## Test kanıtı
- unit: komut / sonuç
- integration: komut / sonuç
- e2e: komut / sonuç
- security (cross-tenant + negative authz): komut / sonuç

## Risk ve rollback
- ...

## Varsayımlar
- ASM-....

## Açık kararlar
- OQ-...
```

---

## 9. Story "done" sayılamaz — engelleyici koşullar

- Kabul kriterlerinden biri başarısız
- Migration test edilmedi
- Public contract güncellenmedi
- Authorization negatif testi yok
- Tenant isolation testi yok (tenant verisine dokunan story'de)
- Observability (log/metric/trace/audit) eksik
- Frontend'te error/empty/loading/permission-denied state'i eksik
- Yeni dependency gerekçesiz
- TODO, placeholder, fake success veya commented-out kod var
- Test yalnız mock'a karşı çalışıyor; gerçek boundary doğrulanmıyor
- Açık critical/high security finding var

---

## 10. Şu anki repository durumu

**Backend scaffold hazır ve çalışıyor** — ancak **hiçbir iş özelliği içermiyor**.

**Var olanlar:** `apps/backend/pyproject.toml` (tek distribution `flowpilot-backend`), `flowpilot.api` (yalnız `/health/live` + `/health/ready`), `flowpilot.worker` (yalnız `--check`), `flowpilot.config.settings`, 13 **boş** bounded context paketi, test altyapısı ve kalite araçları (pytest, Ruff, mypy strict, import-linter, AST boundary check). Repo kökünde `.venv`.

**Hâlâ YOK ve owner onayı olmadan oluşturulmaz:** database bağlantısı, SQLAlchemy modeli, migration, `alembic.ini`, tenant/RLS, Supabase entegrasyonu, authentication, workflow runtime, purchase request, outbox/worker loop, `Dockerfile`, `docker-compose.yml`, frontend scaffold, health dışında API endpoint'i.

Kalite kapıları için bkz. [CLAUDE.md](CLAUDE.md) §6 — **bu komutlar çalışır ve geçmek zorundadır**.
