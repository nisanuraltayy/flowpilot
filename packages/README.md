# packages/ — Paylaşılan Paketler

Modüller arası **paylaşılan** ama iş mantığı **içermeyen** kod.

## Alt dizinler

| Paket | Rol |
|---|---|
| [contracts/](contracts/README.md) | OpenAPI / AsyncAPI / JSON Schema sözleşmeleri ve bunlardan **üretilen** tipler |
| [shared/](shared/README.md) | Primitive value object'ler, error base, `Clock`, `IdGenerator` |
| [observability/](observability/README.md) | Structured log, metric, trace sözleşmeleri |
| [testing/](testing/README.md) | Test altyapısı: fake adapter'lar, fixture'lar, fake clock |
| [config/](config/README.md) | Environment değişkeni yükleme ve doğrulama |
| [ui/](ui/README.md) | Frontend design system (token'lar, ortak bileşenler) |

## Bağımlılık sınırı

**MUST NOT:**
- `packages/*` **hiçbir modüle bağımlı olamaz**. Bağımlılık oku her zaman `modules/* → packages/*` yönündedir.
- `packages/shared` bir **domain çöplüğü olamaz**. İş kuralı, entity, use case veya repository barındıramaz.

## Durum

Boş.
