# modules/workflow-design — Workflow Design

**Sahip olduğu kavramlar:** `WorkflowDraft`, `WorkflowVersion`, Node, Edge, Form Schema.
**Sahip olduğu tablolar:** `workflows`, `workflow_versions`, `workflow_nodes`, `workflow_edges`, `form_schemas`.

## Sorumluluk

Sürecin **tanımı**. Draft düzenleme, graph validation, publish ve versiyonlama.

## Sınırlar (en kritik invariant burada)

- **Published workflow version IMMUTABLE'dır.** Yayınlanan içerik hash'lenir. Published tablolara `UPDATE` çalıştıran **hiçbir kod yolu bulunamaz** (FF-11).
- `published → draft` geçişi **YASAK**. Yeni düzenleme **yeni draft** üretir; published kayıt değişmez.
- Publish işlemi: validation + yetki + immutable version + hash + audit — **hepsi tek transaction'da**.
- **Bilinmeyen node tipi yayınlanamaz.** MVP node seti: `Start`, `Form`, `Condition`, `Sequential Approval`, `Notification`, `End` (FF-16).
- Draft'lar optimistic concurrency ile korunur (409 Conflict; sessiz overwrite YASAK).
- Graph validation: yetim node, ulaşılamayan End, Condition'da default branch eksikliği → yayın **engellenir**.

## Durum

Boş.
