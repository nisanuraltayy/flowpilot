# Test Kuralları

Bağlayıcı kaynak: PRD §20, §48.3, §48.4, §48.5.

---

## 1. Temel ilke

Test, implementasyonu **doğrulamak** içindir; implementasyona uydurulmaz.

**YASAK:**

- Failing test'i silmek.
- Failing test'i `skip` / `xfail` / `it.skip` ile görünmez yapmak.
- Beklenen değeri, kod öyle davrandığı için değiştirmek.
- Testi yalnızca mock'a karşı yazıp gerçek boundary'yi (DB, transaction, worker, policy) hiç doğrulamamak.
- Kabul kriterlerini kod tamamlandıktan **sonra** yazmak.
- Workflow runtime'ı e2e testte tamamen mock'lamak.

Bir test kırmızıysa: ya kod hatalıdır ve düzeltilir, ya da kabul kriteri hatalıdır ve **açıkça** güncellenir (gerekçesiyle PR'da belirtilir).

---

## 2. Test türleri ve kapsam

### Unit test

- Condition evaluator (DSL parser, deterministik sonuç, timeout)
- Workflow graph validation
- State machine geçişleri (instance, task, approval step)
- Approval sıralama mantığı
- Authorization policy objeleri
- Money value object (minor unit + currency, yuvarlama, para birimi uyuşmazlığı)
- Zaman hesapları (UTC, timezone)

### Integration test

- DB transaction sınırları (state + outbox + audit **aynı** transaction)
- Transactional outbox yazımı ve polling worker dispatch'i
- Idempotent inbox (aynı event iki kez → tek side effect)
- Optimistic concurrency conflict → 409/412
- Row Level Security politikalarının gerçekten uygulandığı
- FileStoragePort adapter (local MinIO adayı)
- Persisted timer'ın restart sonrası çalışması

### Contract test

- OpenAPI lint + breaking-change diff
- AsyncAPI / event schema validation
- Port sözleşmeleri: fake adapter ve gerçek adapter **aynı** contract test setini geçer (özellikle `AuthProviderPort` ve `WorkflowRuntimePort`)

### End-to-end test

- Satın alma talebi dikey dilimi (giriş → talep → koşul → sıralı onay → notification → audit → timeline)
- Ret ve değişiklik talebi yolları
- Worker restart sonrası sürecin doğru tamamlanması
- Duplicate event ve duplicate approval senaryoları

### Güvenlik testi (ZORUNLU)

Tenant verisine dokunan **her** story:

- **Cross-tenant test:** Tenant A actor'ü, Tenant B kaynağına ID tahmini ile erişemez (IDOR/BOLA).
- **Negative authorization test:** Yetkisiz rol reddedilir; yetki reddi audit'e yazılır.
- Self-approval engeli, duplicate approval engeli, yetkisiz step kararı engeli.

### Resilience testi

- Worker kill/restart
- Duplicate event teslimi
- DB transaction rollback
- Timer gecikmesi

---

## 3. Zorunlu senaryo kuralları (Gherkin ilkeleri)

- Kabul kriteri **gözlemlenebilir davranışı** anlatır, implementasyon detayını değil. "API çağrılır" değil, "ikinci onay adımı aktif olur" yazılır.
- Her story'de en az bir **negatif authorization** senaryosu bulunur.
- Concurrency etkisi olan story'de **yarış koşulu** senaryosu bulunur (çift tıklama, iki cihaz, iki worker).
- Asenkron story'de **duplicate**, **retry** ve **terminal failure** senaryoları bulunur.
- Frontend story'sinde loading, empty, permission-denied, not-found, validation-error ve success state'leri test edilir. Yalnız happy path ile story tamamlanamaz.

---

## 4. Coverage hedefleri

Coverage tek başarı metriği değildir; regresyon sinyali olarak kullanılır.

| Alan | Hedef |
|---|---|
| Workflow runtime, condition evaluator, approval domain | %90 branch |
| Authorization ve tenant policy | %90 branch |
| Diğer backend application/domain | %80 line, %75 branch |
| Frontend kritik state/validation mantığı | %75 branch |

- Her production bug için **önce veya aynı PR'da** regression test yazılır.
- Generated code ve trivial DTO'lar açık kuralla coverage dışında bırakılabilir.

---

## 5. Test verisi ve determinizm

- Testlerde **fake clock** kullanılabilmelidir; domain gerçek sistem saatine bağlı olmamalıdır.
- ID üretimi injectable olmalıdır; testte deterministik ID kullanılabilmelidir.
- Test fixture'ları seed verisinden ayrılır. Production verisi fixture'a gömülmez.
- Testler birbirinden bağımsız çalışır; sıraya bağımlı test YASAK.

---

## 6. Kalite kapıları

> Repository bootstrap onaylanana kadar çalıştırılabilir test komutu **yoktur**. Bootstrap (Epic E00) sonrasında aşağıdaki kapılar zorunlu olur.

Story done olmadan geçmesi gerekenler:

1. Format + lint
2. Type check (Python + TypeScript)
3. Unit test
4. Integration test
5. Contract test / lint
6. Cross-tenant test (tenant verisine dokunuyorsa)
7. Negative authorization test (yetki kontrolü varsa)
8. Migration test (boş DB + önceki şema)
9. Secret scan
10. Dependency vulnerability scan — açık critical/high yok

Kapıların hiçbiri "geçici olarak" atlanamaz.
