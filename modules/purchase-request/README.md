# modules/purchase-request — Purchase Request

**Sahip olduğu kavramlar:** `PurchaseRequest`, FormSubmission.
**Sahip olduğu tablolar:** `purchase_requests`, `form_submissions`.

## Sorumluluk

İlk dikey dilimin iş domain'i: satın alma talebi (ürün/hizmet adı, kategori, tutar, para birimi, gerekçe, isteğe bağlı dosya).

> Not: Bu context PRD §35.1'in bounded context tablosunda ayrıca listelenmemiştir; ilk dikey dilim satın alma talebi olduğu için ayrı modül olarak konumlandırılmıştır ([ASM-0004](../../docs/assumptions.md)).

## Sınırlar

- **Para float olarak tutulamaz.** `amount_minor` (integer) + `currency` (ISO-4217). Bir kuruşluk yuvarlama hatası, yanlış onay zincirine yönlendirme demektir (FF-09).
- **Onay eşikleri (10.000 / 50.000 TL) bu modüle HARD-CODE EDİLEMEZ.** Eşikler workflow definition'daki Condition node koşullarından gelir (ASM-0001).
- Form submission **immutable snapshot**'tır. Onay kararı hangi snapshot'a verildiğiyle birlikte kaydedilir — aksi hâlde audit değersizdir.
- Talep gönderildikten sonra alanlar **kilitlenir**; yalnız `changes_requested` durumunda izin verilen alanlar açılır.
- Talep oluşturma **idempotent**tir (`Idempotency-Key`).
- Talep numarası tahmin edilemez olmalı; sıralı DB ID dışarı açılmaz.

## Durum

Boş.
