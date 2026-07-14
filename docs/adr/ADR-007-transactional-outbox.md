# ADR-007 — Transactional Outbox + PostgreSQL-Backed Polling Worker

- **Durum:** Accepted
- **Tarih:** 2026-07-14
- **Karar veren:** Nisa Nur Altay (product owner)
- **İlgili kilit:** LOCK-005 (**kapandı**)
- **İlgili PRD bölümleri:** §11.5, §11.6, §15, §37.2, §37.4, §37.5, §38.6

## Bağlam

FlowPilot'ta bir kullanıcı işlemi (örn. onay kararı) hem **veritabanı state'ini** değiştirir hem de **yan etkiler** tetikler (sonraki approval step'in aktifleşmesi, in-app notification, audit kaydı, timeline girdisi).

Naif yaklaşım — DB commit + ardından event publish — **dual write**'tır: commit başarılı olup event publish başarısız olursa süreç sessizce durur; onay verilmiş görünür ama workflow ilerlemez. Bu, FlowPilot için kabul edilemez bir tutarsızlıktır.

Ek kısıt: MVP'de Kafka/RabbitMQ/Redis gibi ayrı bir broker altyapısı **istenmiyor** (solo developer, operasyon maliyeti).

## Değerlendirilen seçenekler

| Seçenek | Değerlendirme |
|---|---|
| A. Doğrudan publish (dual write) | **Reddedildi.** PRD'de açıkça yasak anti-pattern. Event kaybı = kayıp süreç. |
| B. Redis/RabbitMQ + outbox | Outbox doğru, ancak ek altyapı bileşeni. MVP ölçeğinde (günlük ≤100k event) gerekçelendirilemez. |
| C. **Transactional outbox + PostgreSQL polling worker** | **Seçilen.** Ek altyapı yok; aynı transaction garantisi; ölçek hedefi için yeterli. |
| D. PostgreSQL `LISTEN/NOTIFY` | Tek başına yetersiz: teslim garantisi yok, bağlantı koparsa bildirim kaybolur. Polling'i **hızlandırmak** için opsiyonel olarak eklenebilir, yerine geçemez. |

## Karar

1. **Transactional outbox.** Business state değişikliği ve integration event **aynı PostgreSQL transaction'ında** `outbox_events` tablosuna yazılır. Transaction commit olmazsa event de olmaz; commit olursa event **kesinlikle** vardır.
2. **PostgreSQL-backed polling worker.** Ayrı bir worker process, `outbox_events` tablosunu `FOR UPDATE SKIP LOCKED` ile güvenli şekilde okur (çoklu worker'da çakışma olmadan), handler'ları çağırır ve kaydı işlenmiş olarak işaretler.
3. **At-least-once + idempotent consumer.** Teslim garantisi at-least-once'tır. Aynı event'in iki kez işlenmesi **duplicate side effect üretmez**; consumer işlediği message kimliğini `processed_events` (idempotent inbox) tablosuna kaydeder.
4. **"Exactly once" iddiası YASAK.**
5. Event formatı CloudEvents'e uyumlu tutulur: `id`, `type` (`...v1` versiyonlu), `source`, `subject`, `time`, `tenantid`, `correlationid`, `data`.

## Gerekçe

- Aynı veritabanı ⇒ state + outbox + audit tek transaction'da atomik. Bu, FlowPilot'ın en kritik invariant'ı (PRD §36.1/13) ve ADR-004'teki custom runtime kararının da temeli.
- Ek altyapı yok ⇒ deploy, izleme ve failure mode sayısı düşük.
- PRD ölçek varsayımı (günlük ≤100.000 event) için PostgreSQL polling fazlasıyla yeterlidir.
- Broker'a geçiş gerekirse dispatcher değişir; **domain kodu değişmez** (outbox tablosu sözleşme sınırıdır).

## Sonuçlar

**Pozitif**

- Event kaybı yapısal olarak imkânsız (commit ⇒ event var).
- Ek altyapı maliyeti sıfır.
- Broker'a geçiş yolu açık ve ucuz.

**Negatif / risk**

- **Polling gecikmesi.** Event işleme, polling aralığı kadar gecikir. PRD hedefi "bildirim enqueue < 5 s" olduğundan bu kabul edilebilir; ancak polling aralığı ve worker lag **metrik olarak izlenmelidir**.
- **Outbox tablosu büyür.** İşlenmiş kayıtlar için retention/temizleme job'ı gerekir; aksi hâlde tablo ve index şişer.
- Idempotency doğru yazılmazsa duplicate side effect (çift notification, çift task) oluşur → **duplicate event testi zorunludur**.
- Polling, veritabanına sürekli yük bindirir (düşük ama sıfır değil).

## Uyum kuralları (agent için bağlayıcı)

1. **Dual write YASAK.** Event, business state ile **aynı transaction'da** outbox'a yazılır.
2. Her background handler **idempotency davranışını tanımlar** ve `processed_events` (veya eşdeğer) dedup mekanizması kullanır.
3. Dispatcher lease/locking (`SKIP LOCKED`) ile çalışır; çoklu worker aynı event'i iki kez dağıtmaz.
4. **Sonsuz retry YASAK.** Exponential backoff + jitter, maksimum attempt ve maksimum toplam süre tanımlıdır. Validation/authorization/kalıcı business error retry edilmez; incident/dead-letter'a düşer.
5. Event tipi versiyonludur (`approval.decided.v1`). Mevcut version'ın payload semantiği değiştirilmez; yeni alanlar optional olur.
6. Her event `tenant_id` ve `correlation_id` taşır.
7. Event replay güvenli olmalıdır (idempotent consumer sayesinde).
8. Outbox retention/temizleme job'ı tanımlanır.
9. **"Exactly once" ifadesi kullanılamaz.**

## Yeniden değerlendirme tetikleyicileri

- Günlük event hacmi PRD varsayımını (100k) aşarsa veya worker lag metriği hedefi sürekli ihlal ederse → broker (Redis/RabbitMQ) dispatcher'ı değerlendirilir.
- Farklı tüketici sistemlerin (dış entegrasyonlar) fan-out ihtiyacı doğarsa.
