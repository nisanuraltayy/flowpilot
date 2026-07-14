# tests/ — Modül Sınırını Aşan Testler

Tek bir modülün içinde kalan unit ve integration testleri **o modülün kendi `tests/` klasöründedir**. Burada yalnızca **birden fazla modülü birlikte** doğrulayan testler bulunur.

## Alt dizinler

| Dizin | Rol |
|---|---|
| [e2e/](e2e/README.md) | Uçtan uca akış: satın alma dikey dilimi |
| [security/](security/README.md) | Cross-tenant (IDOR/BOLA) ve negatif authorization suite'i |

## Bozulamaz kurallar

- **Failing test silinemez, `skip`/`xfail` ile geçilemez.** Test kırmızıysa: ya kod hatalıdır ve düzeltilir, ya da kabul kriteri hatalıdır ve **açıkça, gerekçesiyle** güncellenir.
- **Workflow runtime e2e testte tamamen mock'lanamaz** (PRD §39 anti-pattern'i). Kritik davranışı test etmeyen bir e2e testi, test değil dekordur.
- Tenant verisine dokunan **her** story'de cross-tenant testi zorunludur.
- Yetki kontrolü olan **her** endpoint'te negatif authorization testi zorunludur.
- Testler **fake clock** kullanabilmelidir; domain gerçek sistem saatine bağlı olamaz.
- Testler birbirinden bağımsızdır; sıraya bağımlı test YASAK.

## Durum

Boş.
