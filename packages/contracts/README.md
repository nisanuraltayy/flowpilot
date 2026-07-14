# packages/contracts — API ve Event Sözleşmeleri

Backend (Python) ile frontend (TypeScript) arasındaki **tek gerçek kaynak**. Monorepo kararının (ADR-008) ana gerekçesi budur: sözleşme ve tüketicisi **aynı commit'te** değişir.

## İçerik (üretilecek)

| Dosya | Rol |
|---|---|
| `openapi.yaml` | HTTP API sözleşmesi |
| `asyncapi.yaml` | Event sözleşmesi (outbox → consumer) |
| `workflow-definition.schema.json` | Workflow tanımının versiyonlu JSON Schema'sı |
| `error-catalog.md` | Stabil error code'lar, HTTP eşlemesi, kullanıcı mesajı |
| `generated/` | OpenAPI'den **üretilen** TypeScript client ve tipler |

## Kurallar

- **Frontend tipleri elle yazılmaz** — OpenAPI'den üretilir. Elle senkronizasyon YASAK.
- `generated/` içeriği **elle düzenlenmez**.
- API veya event değişirse sözleşme **aynı PR'da** güncellenir; aksi hâlde merge edilemez.
- Event tipleri versiyonludur (`approval.decided.v1`). Mevcut version'ın payload semantiği değiştirilmez; yeni alanlar optional olur.
- Her event `tenant_id` ve `correlation_id` taşır.
- Breaking change (alan silme/yeniden adlandırma, tip değişimi, required alan ekleme) yeni major version gerektirir.
- CI: OpenAPI lint + **breaking-change diff** + AsyncAPI schema validation.

## Durum

Boş. Sözleşmeler backend scaffold ile birlikte oluşturulacak.
