# packages/shared — Paylaşılan Primitive'ler

## İçerik (yalnızca bunlar)

- **Value object'ler:** `Money` (minor unit + currency), `TenantId`, `UserId`, `Ulid`
- **Error base sınıfları** ve error catalog sözleşmesi
- **`ClockPort`** — domain içinde doğrudan sistem saati okumak YASAK (FF-12); testlerde fake clock kullanılabilmelidir
- **`IdGeneratorPort`** — domain içinde doğrudan random ID üretimi YASAK

## Sınırlar (katı)

**MUST NOT — bu paket bir domain çöplüğü değildir:**
- İş kuralı ❌
- Entity ❌
- Use case ❌
- Repository ❌
- "Yardımcı fonksiyon" karışımı ❌

**MUST NOT:** Hiçbir modüle bağımlı olamaz.

## `Money` hakkında

Para **float olarak tutulamaz** (FF-09). `amount_minor` (integer) + `currency` (ISO-4217) birlikte taşınır; currency'siz tutar geçersizdir. Farklı para birimlerinde toplama/karşılaştırma **domain hatası** fırlatır — sessizce dönüştürülmez.

Gerekçe: bir kuruşluk yuvarlama hatası, 10.000 TL eşiğinde yanlış onay zincirine yönlendirme demektir.

## Durum

Boş.
