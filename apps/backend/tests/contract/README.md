# tests/contract — Sözleşme Testleri

## Kapsam

**Port contract'ları** — fake adapter ve gerçek adapter **AYNI test setini** geçer:

| Port | Fake | Gerçek |
|---|---|---|
| `AuthProviderPort` | fake adapter | Supabase adapter |
| `FileStoragePort` | in-memory | MinIO / S3 |
| `NotificationChannelPort` | in-memory | in-app (MVP) |
| `MalwareScanPort` | noop | (pilot-ready) |
| `WorkflowRuntimePort` | in-memory | PostgreSQL-backed runtime |

**API/event sözleşmeleri:**

- OpenAPI lint + **breaking-change diff**
- AsyncAPI / event schema validation
- Event fixture consumer testi
- Error catalog eksiksizliği

Sözleşmeler: [packages/contracts](../../../../packages/contracts/README.md)

## Kritik kural

Bir story **yalnızca fake adapter'a karşı** test edilerek "done" sayılamaz. Gerçek boundary (DB, transaction, worker) en az bir integration testte doğrulanır.

## Durum

Boş.
