# modules/identity — Identity

**Sahip olduğu kavramlar:** User, external auth binding.
**Sahip olduğu tablolar:** `users` *(global — tenant'sız; whitelist'te)*.

## Sorumluluk

Kullanıcının kim olduğunu FlowPilot tarafında temsil eder. Supabase'ten gelen doğrulanmış `sub` claim'ini `users.external_auth_id`'ye eşler.

## Sınırlar

- **`AuthProviderPort` burada tanımlanır**; Supabase adapter'ı `infrastructure/` altındadır (ADR-005).
- Supabase SDK'sı **yalnız adapter'da** bulunur; domain'e sızamaz.
- Bir kullanıcı birden fazla tenant'a üye olabilir → **rol burada tutulmaz**. Rol ve üyelik `organization` modülündedir.
- E-posta **primary key değildir**.
- Doğrulanmamış e-postaya sahip kullanıcı tenant verisine erişemez.

## Durum

Boş.
