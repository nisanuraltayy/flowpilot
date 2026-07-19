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

## Dışa sunulan cross-module read contract (`MembershipQuery`)

`application/contracts.py` — başka modüller organization verisine YALNIZ bu application
query üzerinden erişir (domain/infra doğrudan import edilmez):

- `find_active(tenant_id, user_id)` — authorization gate (tenant-scoped, RLS).
- `find_active_owner(tenant_id)` — default approver assignment için aktif owner.
- `list_active_for_user(user_id)` — kullanıcının AKTİF üye olduğu organizasyonlar (org
  adı ile), **cross-tenant**. Frontend'in yeniden girişte aktif org context'ini çözmesi
  için (`GET /v1/me/organizations`). **actor-scoped RLS policy** ile (migration 0006)
  YALNIZ kullanıcının kendi üyelik satırları döner; başka kullanıcının üyeliği görünmez.
  Bu bir organization **management** API'si DEĞİLDİR. Bkz. [[ASM-0017]].

## Durum

**Uygulanmış (kısmi):** Tenant + owner membership oluşturma (atomik), `MembershipQuery`
read contract'ı ve `/v1/organizations`, `/v1/me/organizations` endpoint'leri. Team/
department, rol yönetimi ve davet MVP dışında.
