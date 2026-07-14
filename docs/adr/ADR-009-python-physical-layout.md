# ADR-009 — Python Fiziksel Yerleşimi ve Paketleme: Tek Distribution, `flowpilot.modules.*`

- **Durum:** ✅ Accepted
- **Tarih:** 2026-07-15
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** —
- **Tamamladığı ADR:** [ADR-008](ADR-008-monorepo.md) (monorepo kararını fiziksel Python yerleşimiyle tamamlar)
- **İlgili ADR'ler:** [ADR-001](ADR-001-backend-stack.md) (Python/FastAPI/SQLAlchemy/Alembic), [ADR-003](ADR-003-modular-monolith.md) (modüler monolit)

---

## Context

ADR-008 monorepo'yu, ADR-003 modüler monoliti, ADR-001 Python stack'ini kararlaştırdı. Ancak hiçbiri **Python kodunun fiziksel olarak nereye yazılacağını** söylemedi. Foundation commit'i (`7d43704`) `apps/api`, `apps/worker`, `modules/*`, `packages/*` dizinlerini yalnız README'lerle oluşturdu — bu bir *dizin ağacıdır*, bir *Python paketleme yapısı değildir*.

Scaffold'dan önce çözülmesi gereken somut problemler:

1. **4 bounded context klasörünün adında tire vardı** — `workflow-design`, `workflow-runtime`, `work-management`, `purchase-request`. `import modules.workflow-runtime` bir **syntax hatasıdır**. Tireli adlar `importlib` ile dolaylı yüklenebilir, ama bu statik analizi, IDE'yi, mypy'ı ve **mimari fitness function'ları** kör eder — yani mimarinin tek otomatik güvencesini devre dışı bırakır.
2. **Import kökü tanımsızdı.** `modules/` ve `packages/` `sys.path`'e nasıl girecekti? `PYTHONPATH` hack'i "bende çalışıyor, Docker'da patlıyor" sınıfı hatalar üretir.
3. **`apps/api` ve `apps/worker` ayrı Python projeleri olsaydı**, ikisi de aynı domain'i kullandığı için ya kod kopyalanacaktı (aynı bounded context için iki source of truth — **yasak**) ya da üçüncü bir paylaşılan distribution + editable install zinciri gerekecekti.
4. **`packages/{shared, observability, config, testing}` ayrı distribution yapılırsa** solo developer 4+ `pyproject.toml`, 4 sürüm ve bir editable-install zinciri yönetmek zorunda kalırdı.

Bu karar **kod yazılmadan önce** verilmiştir; şu an maliyeti README taşımaktır. Kod yazıldıktan sonra aynı karar 10× pahalıya mal olurdu.

---

## Decision

**Tek Python distribution, tek import kökü, `modules` segmenti korunmuş bounded context'ler.**

1. **Distribution:** `flowpilot-backend` — tek `pyproject.toml`, `apps/backend/` altında.
2. **Import kökü:** `flowpilot` — `apps/backend/src/flowpilot/` (src-layout).
3. **Bounded context'ler:** `flowpilot.modules.<snake_case>` (13 adet).
4. **Composition root'lar:** `flowpilot.api` ve `flowpilot.worker` — **ayrı proje değil**, aynı distribution'ın iki entrypoint'i.
5. **`shared`, `observability`, `config`** ayrı distribution **değil**; `flowpilot`'ın alt paketleri.
6. **`testing`** ayrı distribution **değil**; backend test yapısının parçası (`apps/backend/tests/`).
7. **`packages/`** altında yalnız **dil-nötr** veya **frontend** paketler kalır: `contracts` (OpenAPI/AsyncAPI/JSON Schema + üretilen TS tipleri) ve `ui`.
8. **Alembic:** tek history — `apps/backend/alembic.ini` + `apps/backend/migrations/`.

### Snake_case yeniden adlandırma

| Eski | Yeni |
|---|---|
| `purchase-request` | `purchase_request` |
| `workflow-design` | `workflow_design` |
| `workflow-runtime` | `workflow_runtime` |
| `work-management` | `work_management` |

Diğer 9 context adı zaten geçerli Python identifier'ıydı.

**Kural:** Bounded context klasör adları **snake_case** olmalıdır. Tireli ad Python import yolunda **kullanılamaz**.

---

## Alternatives considered

| Seçenek | Neden reddedildi |
|---|---|
| **A — root `modules/` doğrudan Python package** | Top-level namespace kirliliği (`import approval`, `import audit`, `import document` — PyPI paketleriyle çakışma riski gerçek). `sys.path` belirsizliği. Modül sınırı dizinde var ama **import grafiğinde zorlanamaz**. |
| **B — `packages/backend/src/flowpilot/`** | `packages/` dokümanlarımızda açıkça *"paylaşılan paketler, iş mantığı içermez"* olarak tanımlı. Tüm backend'i oraya koymak bu tanımı çöpe atar. Ayrıca gereksiz derinlik. |
| **C — root `src/flowpilot/`** | Doğru fikir (tek import kökü), iki eksik: (1) repo'da Next.js de var; root `src/` tüm repo'yu Python projesi gibi gösterir. (2) `flowpilot.approval` ile `flowpilot.api` **kardeş** olur — hangisinin bounded context, hangisinin composition root olduğu import satırından anlaşılmaz. |
| **D (seçilen) — `apps/backend/src/flowpilot/` + `modules` segmenti** | C'nin güçlü yanlarını alır, iki eksiğini kapatır. `apps/backend` ↔ `apps/web` simetriktir. |

Ayrı repository ve mikroservis **değerlendirilmedi** — ADR-003 ve ADR-008 bunları zaten kapatmıştır.

---

## Tek distribution gerekçesi

1. **API ve worker aynı domain kodunu kullanır.** Tek distribution, kopyalamayı **yapısal olarak imkânsız** kılar. İki proje olsaydı, "aynı bounded context için iki source of truth" yasağı yalnız disipline bırakılırdı.
2. **Solo developer + AI agent bağlamında ceremony maliyeti gerçektir.** 13 modül × ayrı distribution = 13 `pyproject.toml`, 13 sürüm, editable install zinciri, her değişiklikte yeniden kurulum. Bu, hiçbir mimari fayda üretmeden günlük iş akışını yavaşlatır.
3. **Tek `pyproject.toml`, tek venv, tek mypy/ruff config, tek pytest rootdir.** Kalite kapıları tek yerden çalışır.
4. **Docker build tek tree kopyalar.** Aynı image, farklı `CMD` ile `api` ve `worker` process'leri olarak çalışabilir — ADR-003'ün "aynı kod tabanı, ayrı process" kararının en ucuz karşılığı.
5. **Modül bağımsızlığı paketlemeyle değil, fitness function'larla korunur.** Bu bilinçli bir takastır: paketleme sınırı bize izolasyon *hissi* verirdi; asıl izolasyonu sağlayan şey import grafiği üzerindeki otomatik kontroldür.

---

## `flowpilot.modules.*` gerekçesi

`modules` segmenti bir seviye derinlik ekler:

```python
from flowpilot.modules.approval.application.commands import DecideApprovalStep   # seçilen
from flowpilot.approval.application.commands import DecideApprovalStep           # reddedilen
```

Bu ek segment **kasıtlıdır**:

1. **Modül sınırı her import satırında görünür olur.** Bounded context (`flowpilot.modules.*`) ile altyapı/composition (`flowpilot.api`, `flowpilot.worker`, `flowpilot.shared`, `flowpilot.config`, `flowpilot.observability`) **import yolundan ayırt edilir**.
2. **Fitness check tek satırlık kurala iner.** *"`flowpilot.modules.X.*` içinde `flowpilot.modules.Y.domain` veya `.infrastructure` importu = ihlal."* Bu kuralı yazmak için mimariyi anlamaya gerek yoktur — string eşleşmesi yeter.
3. **AI agent için okunabilirlik.** Bir agent diff'e baktığında, `modules/notification/` altındaki bir dosyada `flowpilot.modules.approval.infrastructure` görürse ihlali **mimariyi bilmeden** yakalar.

Maliyet: import satırları biraz uzar. Kazanç: mimarinin en kritik kuralı makine tarafından okunabilir hâle gelir. Bu takas kabul edilmiştir.

---

## API ve worker composition sınırları

İkisi de aynı distribution içindedir ve **iş mantığı içermezler**.

| | `flowpilot.api` | `flowpilot.worker` |
|---|---|---|
| Entrypoint | `flowpilot.api.main:app` (uvicorn) | `python -m flowpilot.worker` |
| Sorumluluk | HTTP routing, Supabase token doğrulama, `TenantContext` çözümleme, authorization policy çağrısı, command/query dispatch | Outbox dispatcher, timer worker, event consumer |
| Adapter wiring | **Burada** (DI) — `AuthProviderPort` → Supabase/fake, `FileStoragePort` → S3/MinIO, `MalwareScanPort` → noop | **Burada** |
| DB rolü | `BYPASSRLS` **yok** | `BYPASSRLS` **yok** |

**Bağlayıcı kurallar:**

- İkisi de **yalnız `flowpilot.modules.*.application`** katmanını çağırır.
- `domain` ve `infrastructure` doğrudan **import edilmez** — tek istisna adapter wiring'dir ve o da tek bir dosyada toplanır (`api/deps.py`, `worker/wiring.py`).
- Router/handler içinde **iş kuralı, rol kontrolü veya repository çağrısı YASAK**.

---

## Test yerleşimi

| Test türü | Yer |
|---|---|
| Unit (domain, policy, condition evaluator, `Money`) | `apps/backend/tests/unit/` |
| Integration (PostgreSQL, RLS, outbox, worker, transaction) | `apps/backend/tests/integration/` |
| Contract (fake ↔ gerçek adapter, OpenAPI/AsyncAPI) | `apps/backend/tests/contract/` |
| Security (cross-tenant IDOR/BOLA, negatif authorization) | `apps/backend/tests/security/` |
| E2E (tarayıcı akışı — web + API birlikte) | `tests/e2e/` (repo kökü) |

**Testler `src/` içinde DEĞİLDİR.** src-layout sayesinde testler **kurulmuş** paketi import eder; testler distribution'a sızmaz. Bu, "yerelde çalışıyor ama Docker'da import hatası" sınıfı hataları yerelde yakalatır.

Bu karar, modül başına `tests/` konvansiyonunu **değiştirir**: tek pytest rootdir (`apps/backend`), tek `conftest.py` hiyerarşisi, context'e göre alt klasör.

---

## Alembic yerleşimi

```text
apps/backend/
├── alembic.ini
└── migrations/
    ├── env.py
    └── versions/
```

**Tek migration history. Modül başına ayrı history YOK.**

Gerekçe: modüler monolit **tek PostgreSQL veritabanını** paylaşır. Modül başına ayrı history, aynı veritabanı üzerinde sıralanamayan bağımsız zincirler üretir — oysa foreign key'ler ve **RLS politikaları** modüller arası bir sıra zorunluluğu doğurur. İki history, sessizce bozulan bir migration düzenidir.

- Migration'lar **RLS politikalarını da versiyonlar** (yeni tenant tablosu, politikası olmadan merge edilemez).
- Migration DDL rolü, uygulama rolünden **ayrıdır** (`MIGRATION_DATABASE_URL`).
- `infra/migrations/` **ikinci bir source of truth OLAMAZ**; yalnız `apps/backend/migrations/`'a işaret eden bir işaretçidir.

---

## Dependency enforcement yaklaşımı

Modül bağımsızlığı paketlemeyle değil, **otomatik kontrollerle** korunur. `scripts/check-architecture.*` şu katmanlı sözleşmeyi doğrular:

```text
flowpilot.modules.<X>.domain
    └── bağımlı olabilir: flowpilot.shared
    └── YASAK: fastapi, sqlalchemy, pydantic, supabase, herhangi bir provider SDK
                flowpilot.modules.<Y>.*  (başka bir context)
                flowpilot.api, flowpilot.worker, flowpilot.<X>.infrastructure

flowpilot.modules.<X>.application
    └── bağımlı olabilir: kendi domain'i, kendi port'ları, flowpilot.shared
    └── YASAK: somut adapter, ORM modeli, HTTP framework

flowpilot.modules.<X>.infrastructure / presentation
    └── bağımlı olabilir: kendi application + domain'i, dış SDK'lar
    └── YASAK: flowpilot.modules.<Y>.infrastructure / domain

flowpilot.api, flowpilot.worker
    └── bağımlı olabilir: flowpilot.modules.*.application, flowpilot.shared/config/observability
    └── YASAK: iş mantığı; domain/infrastructure'a doğrudan erişim (adapter wiring hariç)
```

**Somut import kuralları (bağlayıcı):**

1. Domain katmanında **FastAPI, SQLAlchemy, Supabase veya provider SDK importu YASAK**.
2. Bir bounded context, başka bir bounded context'in **`domain` veya `infrastructure`** katmanını **doğrudan import edemez**.
3. Modüller arası erişim **yalnız** açık application contract, command/query veya versiyonlu integration event üzerinden yapılır.
4. `flowpilot.api` ve `flowpilot.worker` **yalnız application sınırlarını** çağırır.
5. **Adapter wiring yalnız composition root'ta** yapılır.
6. **`PYTHONPATH` hack'i kullanılmaz** — paket editable install ile çözülür (`pip install -e apps/backend`).
7. **Aynı bounded context için ikinci bir source of truth oluşturulmaz.**

Araç önerisi: `import-linter` (olgun, layered contract desteği). Alternatif: AST tabanlı özel script. Karar scaffold aşamasında verilecek; **kural her hâlükârda CI'da zorunlu kapıdır**.

---

## Trade-offs

**Kabul edilen maliyetler:**

1. **Derin yollar.** `apps/backend/src/flowpilot/modules/workflow_runtime/domain/instance.py` — 7 seviye. IDE ve import ile çalışılır, dizin gezinerek değil.
2. **Tek sürüm.** Modüller bağımsız versiyonlanamaz. Solo developer için bu bir kayıp değil, kazançtır.
3. **Paylaşılan bağımlılık havuzu.** Notification modülü, workflow-runtime'ın bağımlılığını teknik olarak import edebilir. Bunu paketleme değil, **fitness check** engeller — bilinçli takas.
4. **`modules` segmenti import satırlarını uzatır.** Karşılığında modül sınırı makine-okunur olur.
5. **Root `tests/` ile backend `tests/` ikiliği.** Kural net: Python testleri backend'de, tarayıcı e2e'si root'ta.

**Elde edilen:**

- Kod kopyalama yapısal olarak imkânsız.
- Tek venv, tek config, tek test komutu.
- Modül ihlali statik olarak yakalanabilir.
- Docker build basit.

---

## Future service extraction strategy

Bir modül (ör. `notification` veya `analytics`) ölçek veya organizasyon nedeniyle ayrı servise çıkarılacaksa:

1. **Ön koşul (bugünden sağlanıyor):** İlgili modül hiçbir başka modülün `domain`/`infrastructure`'ını import etmiyor; yalnız integration event tüketiyor. `notification` ve `analytics` bu yüzden **event-only** tasarlandı.
2. **Adım 1 — Sözleşme sabitlenir.** Modülün tükettiği/ürettiği event'ler `packages/contracts/asyncapi.yaml`'da zaten versiyonludur.
3. **Adım 2 — Alt paket çıkarılır.** `flowpilot/modules/notification/` yeni bir distribution'a taşınır; `flowpilot.shared` ortak bağımlılık olarak paylaşılır veya kopyalanır.
4. **Adım 3 — Transport değişir.** Outbox dispatcher, in-process handler yerine HTTP/queue adapter'ına yazar. **Domain kodu değişmez** — yalnız adapter değişir.
5. **Adım 4 — Veri sahipliği taşınır.** Modülün tabloları (`notifications`) ayrı bir şema/veritabanına taşınır.

**Big-bang microservice rewrite YASAK** (ADR-003). Strangler pattern ile capability bazlı ayrılır.

Bu yerleşim, ayırmayı **kolaylaştırır**: modül zaten kendi `domain`/`application`/`infrastructure` katmanlarına sahip, kendi tablolarını yönetiyor ve dışarıyla yalnız sözleşme üzerinden konuşuyor. Ayırma işi bir **paketleme ve transport değişikliğidir**, bir yeniden yazım değil.

---

## Yeniden değerlendirme tetikleyicileri

- Bir modül gerçekten servise çıkarılırsa (o modül için ayrı distribution).
- Ekip büyür ve bağımsız sürümleme ihtiyacı doğarsa.
- Tek `pyproject.toml`'daki bağımlılık havuzu, modüller arası istenmeyen bağımlılıkları fitness check'in yakalayamadığı bir noktaya taşırsa.
