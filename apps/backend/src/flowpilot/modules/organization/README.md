# modules/organization — Organization

**Sahip olduğu kavramlar:** Tenant, `OrganizationMembership`, Team.
**Sahip olduğu tablolar:** `tenants`, `memberships`, `teams`, `team_members`.

## Sorumluluk

**Tenant sınırının kaynağı burasıdır.** `TenantContext` bu modülün membership verisinden çözülür; sistemdeki diğer her şeyin izolasyonu buna dayanır.

## Sınırlar

- Tenant kimliği **istemciden gelen gövde veya query parametresinden ASLA okunmaz** — doğrulanmış token → user → membership zincirinden çözülür.
- **Supabase'in organizations/roles modeli KULLANILMAZ** (ADR-005). Üyelik FlowPilot'ın kendi PostgreSQL'indedir.
- Invariant: **bir tenant hiçbir anda owner'sız kalamaz.**
- Tenant + owner membership oluşturma **tek transaction**'dadır.

## Durum

Boş.
