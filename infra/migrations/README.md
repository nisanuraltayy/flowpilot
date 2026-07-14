# infra/migrations — Veritabanı Migration'ları (Alembic)

## Zorunlu sıra: Expand → Deploy → Backfill → Switch → Verify → Contract

1. **Expand** — yeni nullable kolon/tablo/index ekle
2. **Deploy** — eski ve yeni şema ile çalışan kod
3. **Backfill** — tekrarlanabilir, chunk'lı, gözlemlenebilir job (**web request içinde backfill YASAK**)
4. **Switch** — kontrollü rollout
5. **Verify** — count, checksum, business invariant kontrolü
6. **Contract** — eski kolon/constraint **sonraki** release'te kaldırılır

## Kurallar

- **Her tenant tablosu `tenant_id` içerir** (FF-03) ve **RLS politikası olmadan merge edilemez** (FF-04). Migration politikayı da versiyonlar.
- Migration production'da **uzun table lock yaratmaz**. Büyük index `CONCURRENTLY` oluşturulur.
- **Migration dosyası silinip yeniden üretilmez.**
- **Migration ile veri silme agent'in bağımsız kararı DEĞİLDİR** — owner onayı gerekir.
- Forward-only davranır; rollback planı application rollback + forward fix'tir.
- CI'da **boş DB** ve **bir önceki release şeması** üzerinde test edilir.
- Seed ve fixture ayrılır; **production verisi seed'e gömülmez**.
- Destructive migration tek deploy'da yapılmaz.

## Durum

Boş. Migration **henüz oluşturulmadı**. İlk migration, backend scaffold'dan sonra gelir.
