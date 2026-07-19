# FlowPilot Staging Acceptance Checklist

> Bir staging (veya production ilk) deploy'undan sonra koşulur. Her madde **PASS/FAIL**
> işaretlenir; herhangi bir kritik madde FAIL ise deploy **kabul edilmez** ve rollback
> değerlendirilir (bkz. [deployment-runbook](deployment-runbook.md) §12).
>
> Bu bir **prosedür şablonudur**; doldurulmuş bir çalıştırma gerçek staging ortamı
> gerektirir (henüz yok — LOCK-006).

## Altyapı / güvenlik

- [ ] **HTTPS** — tüm trafik TLS; HTTP → HTTPS yönlendirme; geçerli sertifika.
- [ ] **Security headers** — en az HSTS; frame/embedding koruması; content-type nosniff.
- [ ] **Health** — `GET /health/live` 200; `GET /health/ready` 200.
- [ ] **Migration version** — `alembic current == head (0006)`.
- [ ] **DB rolü** — uygulama `flowpilot_app` ile bağlı; `rolbypassrls=f`, `rolsuper=f`.
- [ ] **RLS context** — context olmadan tenant tablosu sorgusu **0 satır** (default deny).

## Auth akışı

- [ ] **Signup** — yeni kullanıcı kaydı + e-posta doğrulama akışı çalışıyor.
- [ ] **Login** — geçerli kullanıcı giriş yapıp korumalı alana ulaşıyor.
- [ ] **Callback** — `/auth/callback` code→session doğru çalışıyor (open-redirect korumalı).
- [ ] **Logout** — çıkış sonrası korumalı route `/login`'e yönlendiriyor.

## Organizasyon context

- [ ] **Onboarding** — ilk organizasyon oluşturuluyor; kullanıcı aktif owner.
- [ ] **Aktif organizasyon cookie'si** — HttpOnly, SameSite=Lax, Secure(prod), yalnız org UUID.
- [ ] **Cookie authz değil** — stale/rastgele org UUID cookie'si **yetki VERMEZ** (backend membership'i yeniden doğrular).
- [ ] **0/1/çok org** — hiç org → onboarding; tek → otomatik; çok → seçim ekranı.

## Satın alma talebi + eşikler

- [ ] **Create** — talep oluşturuluyor; status `Onay bekliyor`.
- [ ] **9.999,99 ₺ sınırı** — tek adım: **team_manager**.
- [ ] **10.000 ₺ sınırı** — iki adım: **team_manager → finance**.
- [ ] **50.000 ₺ sınırı** — iki adım: **team_manager → finance**.
- [ ] **50.000,01 ₺ sınırı** — üç adım: **team_manager → finance → general_manager**.

## Onay akışı

- [ ] **Sequential approve** — her adım sırayla; sonraki adım öncekisi tamamlanmadan aktifleşmez.
- [ ] **Final approved** — son onay sonrası talep `Onaylandı`; bekleyen görev kalmaz.
- [ ] **Reject terminal** — reddedilen talep `Reddedildi`; sonraki adım görevi **oluşmaz**.
- [ ] **Idempotency** — aynı Idempotency-Key replay → aynı sonuç; farklı payload/çakışan karar → güvenli 409.
- [ ] **Inbox isolation** — kullanıcı yalnız kendine atanmış aktif görevleri görür.

## Görünürlük

- [ ] **Timeline** — kronolojik ve doğru: created → started → task_assigned → approved/rejected → completed/rejected.
- [ ] **Liste/detay/dashboard** — talep durumları ve sayımlar tutarlı (yalnız gerçek verilerden).

## İzolasyon / güvenlik doğrulaması

- [ ] **Cross-tenant IDOR** — tenant A actor'ü, tenant B kaynak ID'sini tahmin ederek erişemez (404, varlık sızmaz).
- [ ] **Membership güvenliği** — üye olmayan kullanıcı ilgili org'da işlem yapamaz (404).
- [ ] **Backend 500 log taraması** — deploy sonrası akışta beklenmeyen 5xx **yok**.
- [ ] **Secret leakage taraması** — loglarda token/secret/parola/anahtar **yok**.
- [ ] **Browser console** — kritik runtime error **yok**.

## Dayanıklılık / operasyon

- [ ] **Backup verification** — deploy öncesi yedek alındı ve **restore prosedürü staging'de test edildi**.
- [ ] **Rollback readiness** — önceki application sürümüne dönüş prosedürü hazır; expand-only şema eski sürümle uyumlu.

---

**Sonuç:** ☐ PASS ☐ FAIL — Tarih: ____ · Ortam: ____ · Commit/sürüm: ____ · Not: ____
