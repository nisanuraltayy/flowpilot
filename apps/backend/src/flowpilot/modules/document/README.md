# modules/document — Document

**Sahip olduğu kavramlar:** Document, DocumentLink.
**Sahip olduğu tablolar:** `documents`, `document_links`.

## Sorumluluk

Dosya eki: güvenli yükleme, yetki kontrollü indirme, kaynakla ilişkilendirme.

## Sınırlar

- **`FileStoragePort`** (S3-compatible; local: MinIO) ve **`MalwareScanPort`** burada tanımlanır.
- **Presigned upload pattern zorunlu:** dosya içeriği API process memory'sinden **geçmez**.
- Object storage path'i **tenant ile izole**dir. Presigned URL kısa TTL'lidir.
- İndirme **her seferinde** authorization kontrolünden geçer.
- Dosya tipi doğrulama yalnız uzantıya değil, **içerik tipine** de bakar.

## ⚠️ Malware tarama — pilot kapısı

MVP'de `MalwareScanPort`'un yalnız **no-op/stub** adapter'ı vardır. `scan_status` alanı ve tarama tamamlanmadan indirmeyi engelleyen kapı **şimdiden hazırdır**.

**Gerçek tarama entegrasyonu PILOT-READY sürümün zorunlu güvenlik çıkış kriteridir** ([ASM-0007](../../../../../../docs/assumptions.md)). Tarama entegre edilmeden Local MVP **pilot müşteriye açılmaz** — aksi hâlde bir kullanıcının yüklediği zararlı dosya aynı tenant'ta indirilebilir.

## Durum

Boş.
