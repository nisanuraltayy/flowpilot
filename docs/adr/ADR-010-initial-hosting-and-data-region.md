# ADR-010 — İlk Hosting ve Veri Bölgesi (Render Frankfurt)

- **Durum:** Accepted
- **Tarih:** 2026-07-19
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-006 (**kapandı** — OQ-002 kapandı)
- **İlgili PRD bölümleri:** §32 (deployment), §16/§17 (veri koruma), §9 (KVKK/gizlilik)
- **Kapsam:** **staging ve ilk pilot.** Production ölçekleme öncesi yeniden değerlendirilebilir.

> ⚠️ **Gerçek deployment HENÜZ YAPILMADI.** Bu ADR yalnızca **hangi sağlayıcı/bölge**
> kullanılacağını kaydeder. Hiçbir Render kaynağı oluşturulmadı, hiçbir remote/push yapılmadı.
> Kurulum kullanıcının hesap erişimiyle sonraki interaktif adımda yapılacaktır.

## Bağlam

MVP v0.1.0 local uçtan uca canlı kabulü PASS (2026-07-19, commit `c9043e8`;
[release kaydı](../releases/mvp-v0.1.0.md)). Pilot'a geçmeden önce **hosting ve veri bölgesi**
kararı gerekiyordu (LOCK-006 / OQ-002). O ana dek deployment **provider-neutral** tutuldu:
Docker tabanlı, sağlayıcıya özgü manifest/buildpack/SDK eklenmedi (ADR-003, ADR-008 uyumlu).

Bileşenler: Next.js `web`, FastAPI `api`, outbox/timer `worker`, PostgreSQL ve Supabase Auth.
KVKK açısından Avrupa veri bölgesi tercih edilir; auth (Supabase) ile uygulama/veritabanı
aynı bölgede olmalı ki gecikme ve veri yerleşimi tutarlı olsun.

## Değerlendirilen seçenekler

| Kriter | Render (Frankfurt) | Ayrı PaaS'lar (web/api farklı) | Kubernetes (managed) | Self-host VPS |
|---|---|---|---|---|
| Operasyon yükü (solo/ilk pilot) | **Düşük** — tek panel | Orta (çok panel) | Yüksek | Yüksek |
| Web + API + worker + PG tek yerde | **Evet** | Hayır | Evet | Evet (elde) |
| Aynı-region private networking (API↔PG) | **Var** | Değişken | Var | Elde kurulur |
| Avrupa (Frankfurt) bölgesi | **Var** | Değişken | Var | Var |
| Supabase Auth ile bölgesel uyum | **Frankfurt eşleşir** | Değişken | Eşleşir | Eşleşir |
| Migration/health/rollback kolaylığı | Basit (pre-deploy cmd, health check) | Parçalı | Esnek ama karmaşık | Elde |
| Vendor lock-in | Orta (provider-neutral kod korunur) | Orta | Düşük | Düşük |
| Maliyet (ilk pilot ölçeği) | Düşük–orta | Değişken | Yüksek (min. footprint) | Düşük ama emek yüksek |

## Karar

**İlk pilot için Render (Frankfurt bölgesi) + mevcut Supabase Auth (Frankfurt).**

Render servis dağılımı (hepsi **Frankfurt**):

- **Next.js frontend** → Render **Web Service**
- **FastAPI backend** → Render **Web Service**
- **Workflow worker** → Render **Background Worker**
- **PostgreSQL** → Render **Managed PostgreSQL** (API ile aynı-region **private** bağlantı)
- **Authentication** → mevcut **Supabase Auth** projesi (Frankfurt) — ADR-005 sınırı korunur
- **Object storage** → **kapsam dışı** (MVP'de aktif kullanılmıyor); gerektiğinde sonra
  S3-compatible bir sağlayıcı seçilecek (karar **ertelendi**, bkz. [[ASM-0006]])

## Gerekçe

1. **Bölge:** Türkiye'ye yakın Avrupa (Frankfurt); KVKK açısından Avrupa veri yerleşimi.
2. **Auth uyumu:** Supabase Auth Frankfurt ile aynı bölge → tutarlı gecikme ve veri yerleşimi.
3. **Private networking:** Backend ↔ PostgreSQL aynı-region özel ağ; DB internet'e açılmaz,
   uygulama internal/private URL kullanır.
4. **Tek operasyon paneli:** web + api + worker + PG tek sağlayıcıda → küçük ekip/ilk pilot için
   düşük operasyon yükü.
5. **Provider-neutral kod korunur:** Uygulama kodu Render'a bağımlı değildir (env + standart
   uvicorn/next start + alembic). Taşıma bir konfigürasyon işidir, refactor değil.

## Sonuçlar

**Pozitif**
- Düşük operasyon yükü; tek panel; aynı-region private DB; Avrupa bölgesi.
- MVP kodu değişmeden deploy edilebilir (Docker/standart komutlar).

**Negatif / risk**
- **Vendor lock-in (orta):** Render'a özgü operasyonel kolaylıklara alışma riski. Azaltım:
  uygulama kodu ve migration akışı sağlayıcıdan bağımsız kalır; `render.yaml` ancak gerçek
  kurulumda, komutlar doğrulandıktan sonra eklenir.
- **Ücretsiz kademeler** cold-start/uyku davranışı taşır → yalnız demo için değerlendirilir;
  pilot öncesi **always-on** servisler gerekir (özellikle worker ve DB).
- **Maliyet:** ilk pilot ölçeğinde düşük–orta; büyümeyle yeniden değerlendirilir.
- **Object storage ertelendi:** dosya eki akışı pilot kapsamına girerse ayrı bir depolama
  kararı gerekir.

## Uyum kuralları (agent için bağlayıcı)

1. Uygulama kodu sağlayıcıya bağımlı hâle **getirilmez**; Render'a özgü SDK eklenmez.
2. Gerçek secret'lar, connection string'ler ve ücret bilgileri **repository'ye yazılmaz**;
   yalnız değişken **adları** dokümante edilir ([render-staging-plan](../operations/render-staging-plan.md)).
3. DB internet'e açılmaz; backend **internal/private** DB URL kullanır.
4. Migration'lar deploy öncesi ayrı bir adımda (`alembic upgrade head`) uygulanır; expand-only
   (bkz. [deployment-runbook](../operations/deployment-runbook.md)).
5. `render.yaml` yalnız **gerçek Render kurulumunda servis komutları doğrulandıktan sonra** eklenir.
6. Career Copilot altyapısına dokunulmaz.

## Yeniden değerlendirme tetikleyicileri

- Production ölçekleme (trafik/veri artışı) — bölge/servis tipi/sağlayıcı yeniden değerlendirilir.
- KVKK/veri yerleşimi gereksinimlerinin netleşmesi (managed vs self-host Supabase).
- Dosya eki/object storage akışının pilota girmesi (depolama sağlayıcı kararı).
- Maliyet veya operasyonel sınırların pilotu zorlaması.
