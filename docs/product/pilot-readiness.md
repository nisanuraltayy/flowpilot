# FlowPilot Pilot Readiness

> Bu belge, **local MVP kabul PASS** (2026-07-19, commit `c9043e8`) sonrası pilot'a
> geçmeden **önce** kapatılması gereken işleri listeler. Bir pilot yapıldığını **iddia
> ETMEZ** — pilot henüz başlamadı. Kapsam: [mvp-scope-v0.1.md](mvp-scope-v0.1.md) ·
> release: [mvp-v0.1.0.md](../releases/mvp-v0.1.0.md).

## Durum özeti

- ✅ Local uçtan uca MVP kabul: **PASS** (owner onaylı).
- ⏳ Pilot: **hazır değil** — aşağıdaki blocker'lar açık.

## Pilot öncesi blocker'lar

| # | Blocker | Sahip | Not |
|---|---|---|---|
| 1 | **Hosting / veri bölgesi kararı** | owner | LOCK-006 açık; provider-neutral kalır, deployment'ta karar gerekir |
| 2 | **Production DB backup politikası** | owner + eng | Zamanlı yedek + PITR; **restore tatbikatı** staging'de yapılmadan production yok |
| 3 | **CI'ın gerçek GitHub runner'da geçmesi** | eng | `.github/workflows/ci.yml` yazıldı; **gerçek runner'da henüz koşmadı** (bu repo'da remote/push yok) |
| 4 | **Staging deploy** | eng | staging ortamı yok; [staging-acceptance-checklist](../operations/staging-acceptance-checklist.md) orada koşacak |
| 5 | **Production Supabase redirect URL'leri** | eng | Site URL + `/auth/callback` allow-list (staging + production) |
| 6 | **Separation-of-duties kararı** | owner | self-approval MVP'de SERBEST (ASM-0016); pilot öncesi yeniden değerlendirilir |
| 7 | **Rol atama yönetimi / kontrollü operasyon prosedürü** | owner + eng | rol yönetimi UI/API'si yok; çok-kullanıcılı atama için prosedür gerekir |
| 8 | **Dependency advisories** | eng | npm 2 *moderate* (next→postcss); high/critical yok; izlenecek. Python audit aracı için §aşağı |
| 9 | **Logging / monitoring** | eng | yapılandırılmış log + metrik/alarm; secret-redaction doğrulaması |
| 10 | **Security headers** | eng | HSTS + frame/nosniff vb. (staging checklist'te) |
| 11 | **Rate limiting değerlendirmesi** | eng | public endpoint'ler için abuse/DoS koruması; liste endpoint'leri zaten bounded |
| 12 | **Privacy / KVKK veri envanteri** | owner + eng | toplanan kişisel veri sınıflandırması; minimizasyon; saklama süreleri |
| 13 | **Kullanıcı destek + incident iletişim yöntemi** | owner | pilot müşteriyle iletişim kanalı + incident süreci |

## Önerilen ilk pilot ölçeği

**3–5 küçük işletme veya kontrollü test organizasyonu.** Bu bir **planlama önerisidir**;
gerçek bir pilot yürütüldüğü **iddia edilmez**. Küçük ölçek: (a) tek-kullanıcı self-approval
akışının sahada gözlemlenmesi, (b) çok-kullanıcılı rol atama prosedürünün elle doğrulanması,
(c) backup/restore ve incident süreçlerinin düşük riskle test edilmesi içindir.

## Kapsam dışı (pilot sonrası)

Kullanıcı daveti · rol yönetimi UI/API · separation-of-duties enforcement · team/department ·
workflow designer · dosya ekleri · e-posta notification · billing · **AI özellikleri**
(LOCK-007 — production AI kararı pilot sonrasına açıkça ertelendi).

## İlgili kilitler

- **LOCK-006 (hosting/veri bölgesi): AÇIK** — deployment provider-neutral; owner kararı bekliyor.
- **LOCK-007 (AI provider ve veri politikası): AÇIK** — AI MVP dışı; production entegrasyon kararı
  pilot sonrasına **açıkça ve gerekçeli** ertelendi (sessiz kapanış değil). Kilit durumu şeması
  yalnız AÇIK/KAPALI desteklediğinden yeni bir "deferred" statüsü uydurulmadı; durum **AÇIK**
  kalır, erteleme gerekçesi burada ve release kaydında belgelendi.
