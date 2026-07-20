#requires -Version 5.1
<#
.SYNOPSIS
  FlowPilot release doğrulaması — tüm kalite kapılarını fail-fast çalıştırır.

.DESCRIPTION
  Windows geliştirme ortamı için. Backend (lint/type/boundaries/test) + worker check +
  alembic current + frontend (lint/type/test/coverage/build/audit) + git özeti.

  GÜVENLİK / GÜVENLİ DAVRANIŞ:
  - Secret/token/env DEĞERLERİ yazdırılmaz.
  - Docker volume SİLİNMEZ, container prune YAPILMAZ.
  - Migration DOWNGRADE yapılmaz; yalnız 'alembic current' OKUNUR.
  - Remote/push YAPILMAZ.

.NOTES
  Kullanım (repo kökünden):
    powershell -ExecutionPolicy Bypass -File scripts\release_verify.ps1
  Docker Desktop çalışıyor olmalı (integration testleri Testcontainers kullanır).
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LintImports = Join-Path $RepoRoot ".venv\Scripts\lint-imports.exe"

if (-not (Test-Path $Python)) {
  Write-Error "Sanal ortam bulunamadı: $Python"
  exit 1
}

$script:StepIndex = 0
function Invoke-Gate {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][scriptblock]$Command
  )
  $script:StepIndex++
  Write-Host ""
  Write-Host ("[{0:d2}] {1}" -f $script:StepIndex, $Name) -ForegroundColor Cyan
  & $Command
  if ($LASTEXITCODE -ne 0) {
    Write-Host ("FAIL: {0} (exit {1})" -f $Name, $LASTEXITCODE) -ForegroundColor Red
    exit 1
  }
  Write-Host ("OK: {0}" -f $Name) -ForegroundColor Green
}

Push-Location $RepoRoot
try {
  Write-Host "FlowPilot release doğrulaması başlıyor…" -ForegroundColor Yellow

  # --- Backend kalite kapıları ---
  Invoke-Gate "Backend: ruff check" { & $Python -m ruff check apps/backend/src apps/backend/tests scripts }
  Invoke-Gate "Backend: ruff format --check" { & $Python -m ruff format --check apps/backend/src apps/backend/tests scripts }
  Invoke-Gate "Backend: mypy (strict)" { & $Python -m mypy --config-file apps/backend/pyproject.toml apps/backend/src }
  Invoke-Gate "Backend: import boundaries (AST)" { & $Python scripts/check_import_boundaries.py apps/backend/src }
  Invoke-Gate "Backend: import-linter" { & $LintImports --config apps/backend/pyproject.toml }
  Invoke-Gate "Backend: worker --check" { & $Python -m flowpilot.worker --check }
  Invoke-Gate "Backend: pytest" { & $Python -m pytest apps/backend/tests -q }

  # --- Alembic current (yalnız OKUMA; downgrade yok) ---
  # Alembic INFO log'ları stderr'e yazar; PS 5.1'de native stderr, ErrorActionPreference=Stop
  # altında terminating sayılır. Bu adımda geçici olarak Continue'ya alıp stream'leri
  # birleştirip metin eşleştiriyoruz (revision string'i aranır; exit code'a güvenilmez).
  Invoke-Gate "Backend: alembic current == 0009" {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = (& $Python -m alembic -c apps/backend/alembic.ini current 2>&1 | Out-String)
    $ErrorActionPreference = $prev
    $revLine = ($out -split "`n" | Where-Object { $_ -match "0009" }) -join " "
    Write-Host ("alembic current: {0}" -f $revLine.Trim())
    if ($out -match "0009") { $global:LASTEXITCODE = 0 } else { $global:LASTEXITCODE = 1 }
  }

  # --- Frontend kalite kapıları ---
  Push-Location (Join-Path $RepoRoot "apps\web")
  try {
    Invoke-Gate "Frontend: lint" { npm run lint }
    Invoke-Gate "Frontend: typecheck" { npm run typecheck }
    Invoke-Gate "Frontend: test" { npm run test }
    Invoke-Gate "Frontend: test:coverage" { npm run test:coverage }
    Invoke-Gate "Frontend: build" { npm run build }
    Invoke-Gate "Frontend: npm audit (high)" { npm audit --audit-level=high }
  }
  finally {
    Pop-Location
  }

  # --- Git özeti (yalnız durum; commit/push yok) ---
  Write-Host ""
  Write-Host "[git] durum özeti (yalnız okuma):" -ForegroundColor Cyan
  $status = git status --short
  if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "working tree clean" -ForegroundColor Green
  }
  else {
    Write-Host $status
  }
  git log --oneline -1

  Write-Host ""
  Write-Host "TÜM KAPILAR GEÇTİ ✅" -ForegroundColor Green
}
finally {
  Pop-Location
}
