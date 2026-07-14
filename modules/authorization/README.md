# modules/authorization — Authorization

**Sahip olduğu kavramlar:** Role, Permission, Policy.
**Sahip olduğu tablolar:** `roles`, `role_permissions`.

## Sorumluluk

Tek soruyu cevaplar: **`authorize(actor, action, resource)`**. Sistemdeki tüm yetki kararları buradan geçer.

## Sınırlar

- **Dağınık rol kontrolü YASAK.** Controller/router içinde `if role == "admin"` bulunamaz — merkezi policy boundary'si burasıdır.
- Her korumalı endpoint bir **policy adı** belirtir (FF-06).
- Her permission merkezi katalogda kayıtlıdır (FF-14).
- Yetki reddi kaynağın **varlığını sızdırmaz** ve **audit'e yazılır** (`security.authorization.denied.v1`).
- Ownership policy'si desteklenir: requester rolü yetmese bile kendi talebini okuyabilir.
- Yayınlama yetkisi (`workflow.definition.publish`) oluşturma yetkisinden **ayrıdır**.

MVP dışı: ABAC, field-level visibility, custom rol tanımlama.

## Durum

Boş.
