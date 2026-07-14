# apps/api — Senkron HTTP API (FastAPI)

**Rol:** Composition root. HTTP isteğini karşılar, actor ve tenant context'ini çözer, ilgili modülün command/query'sini çağırır, sonucu döner.

Stack: Python + FastAPI + Pydantic (ADR-001).

## Sorumlulukları

- HTTP routing ve request/response DTO'ları (Pydantic)
- Kimlik doğrulama: Supabase token'ının **her istekte** doğrulanması (JWKS imza, issuer, audience, expiry)
- `TenantContext`'in **bir kez** çözülmesi (token → user → membership)
- Authorization policy'sinin çağrılması
- OpenAPI sözleşmesinin üretilmesi
- Adapter'ların portlara bağlanması (dependency injection)

## Bağımlılık sınırı

**MUST NOT:**
- **İş mantığı içeremez.** Router içinde `if role == "admin"` gibi kontroller YASAKTIR — authorization merkezi policy boundary'sindedir.
- Modüllerin `infrastructure/persistence` katmanını import edemez; repository'yi doğrudan çağırmaz.
- Tenant kimliğini istek gövdesinden veya query parametresinden **okuyamaz**.
- Uzun süren entegrasyon işi yapamaz — asenkron iş `worker`'a outbox üzerinden devredilir.

**MUST:**
- Her korumalı endpoint bir **authorization policy adı** belirtir (FF-06).
- Her liste endpoint'i **cursor pagination** ve server-side max page size kullanır (FF-15).
- Mutating endpoint'ler gerektiğinde `Idempotency-Key` kabul eder.
- Veritabanına **`BYPASSRLS` yetkisi olmayan** rolle bağlanır (ADR-006).

## Durum

Boş. FastAPI scaffold, `pyproject.toml` ve kaynak kodu **henüz oluşturulmadı**.
