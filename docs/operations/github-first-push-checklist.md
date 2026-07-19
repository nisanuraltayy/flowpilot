# FlowPilot — GitHub İlk Push Kontrol Listesi

> Bu belge, FlowPilot'ı **private** bir GitHub repository'sine ilk kez bağlamak ve
> pushlamak için sıralı prosedürdür.
>
> ⚠️ **Bu adımlar bu görevde ÇALIŞTIRILMADI.** Komutlar **kullanıcı** tarafından, kendi
> GitHub hesabıyla, sonraki interaktif adımda çalıştırılacaktır. Aşağıdaki komutlar
> referanstır; agent remote eklemez / push yapmaz.

## Ön koşullar

- [ ] Yerel repo temiz: `git status` → working tree clean.
- [ ] HEAD doğru release commit'inde: `git log --oneline -1` → `chore: select Frankfurt hosting for initial pilot` (bu görevin commit'i) veya daha yenisi.
- [ ] Annotated tag mevcut: `git tag -l "v0.1.0-mvp"`.
- [ ] `.gitignore` `.env` ve `apps/web/.env.local`'ı **hariç tutuyor** (secret sızmaz).

## 1. Private repository oluştur

- [ ] GitHub'da **private** bir repository oluştur (ör. `flowpilot`). Boş oluştur — README/lisans/.gitignore **ekleme** (yerelde zaten var, çakışma olmasın).
- [ ] Repository'nin **Career Copilot'tan ayrı** ve doğru hesap/organizasyonda olduğunu doğrula.

## 2. Remote URL'yi kullanıcıdan al ve ekle

- [ ] Kullanıcı repository'nin remote URL'ini sağlar (SSH önerilir: `git@github.com:<owner>/flowpilot.git`).
- [ ] Remote ekle:

```bash
git remote add origin <REMOTE_URL>
```

- [ ] **Doğrula** (yanlış hedefe push'u önle):

```bash
git remote -v
```

- [ ] URL'in **FlowPilot** repository'sini gösterdiğini teyit et — **Career Copilot repository'sine push YAPILMADIĞINI** kesinleştir.

## 3. Önce `main`, sonra tag

- [ ] `main` branch'ini pushla:

```bash
git push -u origin main
```

- [ ] Annotated tag'i pushla:

```bash
git push origin v0.1.0-mvp
```

> Tag'i ayrıca pushlamak gerekir; `git push` tag'leri otomatik göndermez.

## 4. GitHub Actions (CI) doğrulaması

- [ ] Push sonrası **Actions** sekmesinde `CI` workflow'u tetiklenir.
- [ ] Workflow izinlerinin **minimum** olduğunu doğrula (repo Settings → Actions → Workflow permissions = **Read repository contents**; workflow zaten `permissions: contents: read` bildirir).
- [ ] **CI'ın gerçek runner'da geçmesini BEKLE** (backend + migration-verify + frontend job'ları yeşil).
- [ ] Testler fake/kontrollü auth kullandığından **gerçek Supabase secret'ı gerekmez**; herhangi bir secret eklenmesine gerek yoktur.

## 5. Branch protection (CI geçtikten SONRA)

- [ ] `main` için branch protection etkinleştir: PR zorunlu, **CI status check zorunlu**, force-push kapalı.
- [ ] Bunu CI **ilk kez yeşil olduktan sonra** yap (aksi hâlde ilk push/kurulum kilitlenebilir).

## 6. Güvenlik doğrulamaları

- [ ] **Secret ekleme.** Bu MVP'de CI gerçek secret gerektirmez; repository/Actions secret'ı tanımlama.
- [ ] `.env` ve `apps/web/.env.local`'ın **push edilmediğini** doğrula (GitHub'da dosya listesi + `git ls-files | grep -E "\.env"` boş olmalı; yalnız `.env.example` türü izinli).
- [ ] Yanlışlıkla **Career Copilot** dosyası/geçmişi push edilmediğini doğrula.
- [ ] Push edilen geçmişin yalnız FlowPilot commit'lerini içerdiğini doğrula.

## 7. Sonrası

- Remote yeşil CI ile hazır olduğunda: [render-staging-plan.md](render-staging-plan.md) ile
  Render Frankfurt staging kurulumuna geçilir (ADR-010). Gerçek deployment o adımda yapılır.

---

**Not:** Bu belgedeki komutlar hesap erişimi gerektirir ve **kullanıcı** tarafından
çalıştırılır. Agent; remote eklemez, push yapmaz, repository oluşturmaz, secret üretmez.
