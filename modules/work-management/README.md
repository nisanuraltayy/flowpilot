# modules/work-management — Work Management

**Sahip olduğu kavramlar:** `Task`, Assignment.
**Sahip olduğu tablolar:** `tasks`, `task_assignments`.

## Sorumluluk

İnsan aksiyonu bekleyen iş. Task yaşam döngüsü, assignee çözümleme ve kişisel inbox.

## Sınırlar

- **Terminal task yeniden tamamlanamaz.** Completion **idempotent**tir.
- `overdue` ayrı bir state **değildir**, türetilmiş alandır (`is_overdue`). Aynı kavram iki yerde tutulmaz.
- Assignee yalnız **aynı tenant'ın aktif üyesi** olabilir. Suspended üye atanamaz.
- Assignee bulunamazsa **kontrollü hata/incident** üretilir — süreç **sessizce asılı kalmaz**.
- Inbox sorguları tenant + authorization ile filtrelenir ve **cursor pagination** kullanır (FF-15).
- Approval modülü bu tabloya **doğrudan yazamaz**; command veya event kullanır.

MVP dışı: checklist, öncelik yönetimi, SLA/eskalasyon.

## Durum

Boş.
