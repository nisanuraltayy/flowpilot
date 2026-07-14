# infra/ — Altyapı

Container tanımları ve veritabanı migration'ları.

## Alt dizinler

| Dizin | Rol |
|---|---|
| [containers/](containers/README.md) | Dockerfile'lar ve local geliştirme compose tanımı (PostgreSQL, MinIO) |
| [migrations/](migrations/README.md) | Alembic migration'ları — şema ve **RLS politikaları** |

## Kural: provider-neutral

Deployment **Docker tabanlı ve provider-neutral**dır (LOCK-006 hâlâ açık; ilk aday Render). Sağlayıcıya özgü manifest, buildpack veya SDK **eklenmez** — hosting kararı verilene kadar.

## Durum

Boş. Dockerfile, `docker-compose.yml` ve migration **henüz oluşturulmadı**.
