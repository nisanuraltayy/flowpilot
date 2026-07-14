# tests/unit — Unit Testleri

Dış bağımlılık olmadan çalışan, hızlı testler. Fake clock ve deterministik `IdGenerator` kullanılır.

## Kapsam

- Condition evaluator (DSL parser, sınır değerleri: 10.000 ve 50.000 TL, determinizm, zararlı payload reddi)
- Workflow graph validation (yetim node, ulaşılamayan End, bilinmeyen node tipi)
- State machine geçişleri (instance, task, approval step)
- Sıralı onay mantığı (1, 2 ve 3 adımlı zincirler)
- Authorization policy objeleri
- `Money` value object (minor unit + currency, sınır değerleri, para birimi uyuşmazlığı)
- Zaman hesapları (UTC, timezone)

## Hedef

Workflow runtime, condition evaluator, approval domain, authorization ve tenant policy: **%90 branch coverage**.

## Durum

Boş.
