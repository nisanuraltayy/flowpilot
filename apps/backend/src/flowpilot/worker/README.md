# flowpilot.worker — Asenkron İşlem Process'i

**Rol:** Composition root. `api`'den **ayrı bir process**'tir (ADR-003). Transactional outbox'ı tüketir, timer'ları ateşler, event handler'ları çalıştırır.

## Sorumlulukları

- **Outbox dispatcher** — `outbox_events` tablosunu `FOR UPDATE SKIP LOCKED` ile güvenli okur, handler'lara dağıtır, işlenmiş olarak işaretler (ADR-007)
- **Timer worker** — vadesi gelen persisted timer'ları lease mekanizmasıyla ateşler
- **Event consumer'lar** — notification üretimi, read model projection'ı
- Bounded retry (exponential backoff + jitter) ve dead-letter/incident yönetimi

## Bağımlılık sınırı

**MUST:**
- Her handler **idempotency davranışını tanımlar** ve `processed_events` (inbox) ile duplicate side effect'i engeller (FF-07).
- Idempotency işareti, side effect ile **aynı transaction'da** yazılır.
- Worker DB session'ını **tenant context ile** açar ve **RLS'e tabidir**. `BYPASSRLS` yetkili rol kullanmak, en sinsi cross-tenant sızıntı yoludur — **YASAK** (SPK-10).
- Terminal instance guard'ı **worker yolunda da** uygulanır; event handler bir arka kapı olamaz (SPK-09).

**MUST NOT:**
- **Sonsuz retry YASAK.** Maksimum attempt ve maksimum toplam süre tanımlıdır.
- In-memory timer **YASAK**; timer'lar veritabanındadır.
- `"exactly once"` iddiası **YASAK**. Yaklaşım: at-least-once delivery + idempotent consumer.

## Komutlar

```powershell
# Import + ayar doğrulama (worker loop BAŞLATMAZ) — kalite kapısı
python -m flowpilot.worker --check

# Tek dispatch turu (timer ateşle → outbox claim → idempotent işle), sonra çık
python -m flowpilot.worker --run-once --tenant <uuid> [--worker-id NAME]

# Kontrollü döngü: en çok N tur, turlar arası S sn; SIGTERM/SIGINT'te graceful durur
python -m flowpilot.worker --run --tenant <uuid> --max-passes N [--interval S]
```

`--max-passes 0` reddedilir (sonsuz busy loop YASAK). Dispatch **tenant-scoped**
çalışır: her tur açık bir `--tenant` context'i altında; RLS'e tabidir (BYPASSRLS YOK).

## Durum

✅ **Runtime worker modu yazıldı** (Epic E09). Wiring yalnız [wiring.py](wiring.py)
composition root'undadır; iş mantığı içermez — `WorkflowRuntimeService.run_dispatch_pass`
application sınırını çağırır. LOCK-003 kapandı (ADR-004 Accepted, 2026-07-19).
Notification/read-model consumer'ları ve çoklu-tenant zamanlama sonraki story'lerde eklenecektir.
