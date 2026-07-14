# modules/analytics — Analytics (temel)

**Sahip olduğu kavramlar:** Dashboard read model.
**Sahip olduğu tablolar:** read model tablosu / materialized view.

## Sorumluluk

Temel operasyon dashboard'u: açık talepler, bekleyen onaylar, tamamlanan ve reddedilen süreç sayaçları.

## Sınırlar

- **Operasyonel tabloları ağır sorgularla yormaz.** Read model / materialized aggregate kullanır (CQRS-lite).
- **Hiçbir iş modülünü import etmez** — event tüketir. Bu, modülü ileride ayırmayı mümkün kılar.
- Projection **idempotent**tir; duplicate event iki kez saymaz. Replay güvenlidir.
- Sorgular tenant + authorization ile filtrelenir. Bir `member` rolündeki kullanıcı **tüm tenant'ın verisini göremez**.
- Read model gecikmesi (eventual consistency) UI'da açıkça gösterilir; yanlış kesinlikte sayı sunulmaz.
- **Reconciliation zorunlu:** read model sayıları kaynak kayıtlarla örneklemde doğrulanır.

MVP dışı: cycle time, SLA metrikleri, darboğaz analizi, trend, CSV export.

## Durum

Boş.
