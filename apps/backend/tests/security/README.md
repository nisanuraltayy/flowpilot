# apps/backend/tests/security — Güvenlik Regresyon Suite'i

Cross-tenant veri sızıntısı PRD'de **"Kritik"** etkili risktir ve itibar açısından geri döndürülemez. Bu suite olmadan izolasyon iddiası **kanıtsızdır**.

## 1. Cross-tenant suite (IDOR / BOLA)

Tenant A'nın actor'ü, Tenant B'nin kaynak ID'sini **tahmin ederek** şunları denemelidir — hepsi reddedilmelidir:

- Purchase request okuma
- Workflow instance okuma / iptal etme
- Approval step'e **karar verme**
- Task okuma / tamamlama
- Notification okuma
- Audit ve timeline okuma
- Doküman **indirme**
- Dashboard'da başka tenant'ın verisini sayma

Ek olarak: **uygulama filtresi bilinçli olarak kaldırıldığında bile RLS'in sorguyu boşa düşürdüğü** kanıtlanmalıdır (ADR-006, ikinci savunma katmanı).

Ayrıca: **worker'ın RLS'e tabi olduğu** doğrulanmalıdır. Worker'ın `BYPASSRLS` yetkili rolle çalışması, en sinsi sızıntı yoludur.

## 2. Negatif authorization suite

Yetki kontrolü olan **her** endpoint için en az bir "yetkisiz actor reddedilir" senaryosu:

- Self-approval engeli
- Duplicate approval → tek karar
- Atanmamış kullanıcının karar vermesi
- Sıra atlama (2. adım onaycısının erken karar vermesi)
- Yetkisiz workflow publish
- Yetkisiz audit okuma

Yetki reddi **kaynağın varlığını sızdırmaz** ve **audit'e yazılır**.

## Kural

**Bu suite kapatılamaz.** Her PR'da çalışır. Yeni bir tenant-scoped kaynak eklendiğinde suite'e eklenmezse **story done sayılamaz**.

## Durum

Boş.
