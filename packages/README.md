# packages/ — Dil-Nötr ve Frontend Paketleri

| Paket | Rol |
|---|---|
| [contracts/](contracts/README.md) | OpenAPI / AsyncAPI / JSON Schema sözleşmeleri ve bunlardan **üretilen** TypeScript tipleri |
| [ui/](ui/README.md) | Frontend design system (token'lar, ortak bileşenler) |

## Neden yalnız ikisi

[ADR-009](../docs/adr/ADR-009-python-physical-layout.md) gereği **`shared`, `observability`, `config` ve test altyapısı ayrı Python distribution DEĞİLDİR.** Bunlar tek backend distribution'ının alt paketleridir:

| Eski konum | Yeni konum |
|---|---|
| `packages/shared` | `apps/backend/src/flowpilot/shared` |
| `packages/observability` | `apps/backend/src/flowpilot/observability` |
| `packages/config` | `apps/backend/src/flowpilot/config` |
| `packages/testing` | `apps/backend/tests` |

Gerekçe: solo developer için 4+ ayrı `pyproject.toml`, 4 sürüm ve bir editable-install zinciri, hiçbir mimari fayda üretmeden günlük iş akışını yavaşlatırdı.

`packages/` altında yalnız **dil-nötr** (`contracts`) veya **frontend'e ait** (`ui`) paketler kalır.

## Bağımlılık sınırı

- `packages/contracts` **tek gerçek kaynaktır**: backend OpenAPI'yi üretir, frontend ondan TypeScript tiplerini üretir. Tipler **elle yazılmaz**.
- `packages/*` hiçbir bounded context'e bağımlı olamaz.

## Durum

Boş.
