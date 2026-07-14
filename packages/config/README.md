# packages/config — Konfigürasyon Yükleme

Environment değişkenlerinin **tek yerden**, **tip güvenli** ve **doğrulanmış** şekilde okunması.

## Sorumluluk

- `.env` / environment değişkenlerini okumak ve **başlangıçta doğrulamak** (eksik zorunlu değişken → uygulama açılmaz, çalışma zamanında sürpriz olmaz)
- Ortam ayrımı: `local` / `test` / `staging` / `production`
- Adapter seçimi: `AUTH_PROVIDER=fake|supabase`, `MALWARE_SCAN_PROVIDER=noop|<provider>`

## Sınırlar

- **Secret'ler log'a yazılmaz**, hata mesajında gösterilmez.
- `SUPABASE_SERVICE_ROLE_KEY` yalnız backend'de bulunur; frontend'e **ASLA** verilmez.
- **Production'da `fake` adapter YASAKTIR** — config guard bunu engellemelidir.
- Uygulama, veritabanına **`BYPASSRLS` yetkisi olmayan** rolle bağlanır (ADR-006). Migration için ayrı, DDL yetkili rol kullanılır.
- Değişken kategorileri: [.env.example](../../.env.example)

## Durum

Boş.
