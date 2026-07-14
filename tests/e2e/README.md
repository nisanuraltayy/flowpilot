# tests/e2e — Uçtan Uca Testler

İlk dikey dilimin (satın alma talebi) gerçekten çalıştığının kanıtı.

## Kapsanacak senaryolar (FP-E15-002)

**Happy path**
- Tutar < 10.000 TL → 1 adımlı onay → completed
- Tutar 10.000–50.000 TL → 2 adımlı sıralı onay → completed
- Tutar > 50.000 TL → 3 adımlı sıralı onay → completed

**Alternatif yollar**
- Ret → instance `rejected`, açık task/timer kapanır
- Değişiklik talebi → revizyon → yeniden onay (önceki onaylar geçersiz olur)

**Dayanıklılık**
- Worker `SIGKILL` + restart → süreç **kayıpsız ve duplicate'siz** tamamlanır
- Duplicate outbox event → tek side effect

**Güvenlik**
- Duplicate approval komutu → **tek** karar
- Cross-tenant erişim → reddedilir

Her akış şunu doğrular: giriş → organizasyon/membership → talep → koşul → sıralı onay → state transition → bildirim → audit → timeline.

## Kural

**Workflow runtime mock'lanamaz.** Gerçek runtime adapter'ı ve gerçek PostgreSQL kullanılır — aksi hâlde test, kanıtlaması gereken tek şeyi (dayanıklılık) kanıtlamaz.

## Durum

Boş.
