# scripts/ — Geliştirme ve Doğrulama Script'leri

Kalite kapılarını **çalıştırılabilir** hâle getiren script'ler. CI ve local'de **aynı** script'ler çalışır — "bende çalışıyordu" durumunu engellemek için.

## Üretilecek script'ler

| Script | Rol |
|---|---|
| `check-architecture.*` | Mimari fitness function'ları: FF-01…FF-16 ([dependency-rules.md](../docs/architecture/dependency-rules.md)) |
| `check-contracts.*` | OpenAPI lint + breaking-change diff + AsyncAPI validation |
| `check-secrets.*` | Secret tarama (her commit'te) |
| `verify-migrations.*` | Boş DB ve önceki release şeması üzerinde migration testi |
| `check-tenant-tables.*` | Her tenant tablosunda `tenant_id` + RLS politikası var mı (FF-03, FF-04) |

## Kritik fitness function'lar (hatırlatma)

- **FF-01** Domain katmanında `sqlalchemy` / `fastapi` / Supabase SDK importu **yok**
- **FF-08** Kod tabanında `eval(` / `exec(` **yok**
- **FF-09** Para alanlarında `float` **yok**
- **FF-11** Published workflow tablolarına `UPDATE` çalıştıran kod **yok**

## Kural

**Bu script'ler kapatılamaz, atlanamaz veya "geçici olarak" devre dışı bırakılamaz.** Kırmızıysa merge yok.

Windows script'leri `.ps1` uzantılıdır ve `.gitattributes` gereği **CRLF** ile saklanır.

## Durum

Boş.
