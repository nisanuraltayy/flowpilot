# infra/ — Altyapı

Container tanımları ve veritabanı migration'ları.

## Alt dizinler

| Dizin | Rol |
|---|---|
| [containers/](containers/README.md) | Dockerfile'lar ve local geliştirme compose tanımı (PostgreSQL, MinIO) |
| [migrations/](migrations/README.md) | Alembic migration'ları — şema ve **RLS politikaları** |

## Kural: provider-neutral

Uygulama kodu **sağlayıcı-nötr**dür. İlk hosting kararı verildi: **Render (Frankfurt) + Supabase Auth** (ADR-010; LOCK-006 kapandı) — kapsam staging + ilk pilot. **Gerçek deployment henüz YAPILMADI.** Sağlayıcıya özgü manifest/`render.yaml` yalnız gerçek Render kurulumunda, servis komutları doğrulandıktan sonra eklenir; uygulama kodu Render'a bağımlı hâle getirilmez.

## Durum

Boş. Dockerfile, `docker-compose.yml` ve migration **henüz oluşturulmadı**.
