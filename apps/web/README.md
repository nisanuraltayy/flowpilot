# apps/web — Kullanıcı Uygulaması (Next.js)

**Rol:** Kullanıcı arayüzü. Next.js + TypeScript (ADR-002).

## Sorumlulukları

- Route haritası: `/inbox` (tasks, approvals), `/requests`, `/workflows`, `/notifications`, dashboard, `/settings`
- Supabase ile kimlik doğrulama akışı (token **sunucu tarafında** tutulur)
- Backend API'yi `packages/contracts`'tan **üretilen** TypeScript client ile çağırmak

## Bağımlılık sınırı

**MUST NOT:**
- **Business logic içeremez.** Yetki kararı, koşul değerlendirmesi, onay sırası ve state transition **yalnız backend'dedir**. Frontend bunları yalnızca **gösterir**.
- Backend modüllerini import **edemez**. Yalnız `packages/contracts` üzerinden konuşur.
- API tiplerini **elle yazamaz** — OpenAPI sözleşmesinden üretir.
- **Onay/ret kararlarında optimistic UI YASAK.** Server-confirmed state gösterilir. Arka plan işi bitmeden "tamamlandı" bildirimi gösterilmez.
- Yetkisiz butonu gizlemek **yeterli değildir** — backend enforcement zorunludur. UI gizleme yalnız kozmetiktir.
- `SUPABASE_SERVICE_ROLE_KEY` tarayıcıya **ASLA** gitmez.

**MUST:**
- Her ekran şu state'leri implemente eder: loading/skeleton, empty, permission-denied, not-found, validation-error, recoverable-server-error, processing/queued, success.
  **Yalnız happy path ile story tamamlanamaz.**
- Tarih ve para gösterimi locale-aware olur; UTC → organizasyon timezone dönüşümü **yalnız gösterim katmanındadır**.

## Durum

Boş. `package.json`, Next.js scaffold ve kaynak kodu **henüz oluşturulmadı**.
