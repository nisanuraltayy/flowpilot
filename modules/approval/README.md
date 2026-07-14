# modules/approval — Approval

**Sahip olduğu kavramlar:** `ApprovalRequest`, ApprovalStep, ApprovalDecision.
**Sahip olduğu tablolar:** `approval_requests`, `approval_steps`, `approval_decisions`.

## Sorumluluk

Onay motoru — ürünün çekirdek değeri. Sıralı onay (1–3 adım), approve / reject / changes_requested kararları.

## Sınırlar (güvenlik-kritik)

- **Bir approval step için tek geçerli aktif karar bulunur.** Duplicate koruması **veritabanı düzeyindedir** (unique constraint + optimistic lock). Uygulama seviyesinde "önce oku, yoksa yaz" **YETERSİZDİR** — yarış koşuluna açıktır (SPK-05).
- **Sıra atlanamaz:** sonraki step, öncekisi tamamlanmadan aktifleşmez (SPK-04).
- **Sıra asılı kalamaz:** karar + sonraki step aktivasyonu + outbox + audit **aynı transaction**'dadır.
- Karar veren actor'ün **karar anında** yetkili olduğu kanıtlanır ve audit'e yazılır.
- **Self-approval engeli:** requester kendi adımını onaylayamaz; alternate assignee'ye yönlendirilir.
- `ApprovalDecision` **immutable**'dır ve hangi form snapshot'ına verildiği kaydedilir.
- **`tasks` tablosuna doğrudan YAZAMAZ** — Work Management'a command/event gönderir.
- Onay zinciri uzunluğu **config'ten gelir** (Sequential Approval node), koda **hard-code edilemez** (ASM-0001).

MVP dışı: parallel approval, quorum, delegation, eskalasyon.

## Durum

Boş.
