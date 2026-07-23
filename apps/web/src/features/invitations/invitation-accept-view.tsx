"use client";

/**
 * Davet kabul ekranı (public). Önizleme durumuna + oturum durumuna göre render eder.
 *
 * Güvenlik:
 * - Token istemci prop'una KONMAZ: kabul action'ı server tarafında (şifreli bound argüman)
 *   org + token taşır. Önizleme yalnız güvenli alanları (org adı, rol, tarih, durum) alır;
 *   e-posta/token içermez.
 * - Başarılı kabulden sonra URL'deki org/token en erken güvenli anda temizlenir
 *   (history.replaceState) — kullanıcı başarı ekranını görmeye devam eder; refresh güvenli.
 */

import { useEffect } from "react";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { ButtonLink } from "@/components/button";
import { SubmitButton } from "@/components/submit-button";
import type { AcceptInvitationResult } from "@/features/invitations/actions";
import { invitationRoleLabel } from "@/features/invitations/display";
import { formatDateTime } from "@/lib/datetime";

export type AcceptPreviewError = "invalid" | "not_found" | "expired" | "unavailable";

export interface SafeInvitationPreview {
  readonly organizationName: string;
  readonly role: string;
  readonly expiresAt: string;
  readonly status: string;
}

interface InvitationAcceptViewProps {
  readonly preview: SafeInvitationPreview | null;
  readonly previewError: AcceptPreviewError | null;
  readonly isAuthenticated: boolean;
  readonly loginHref: string;
  readonly dashboardHref: string;
  readonly action: (
    previous: AcceptInvitationResult,
    formData: FormData,
  ) => Promise<AcceptInvitationResult>;
}

const IDLE: AcceptInvitationResult = { status: "idle" };

function Panel({ children }: { readonly children: React.ReactNode }) {
  return (
    <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      {children}
    </div>
  );
}

export function InvitationAcceptView({
  preview,
  previewError,
  isAuthenticated,
  loginHref,
  dashboardHref,
  action,
}: InvitationAcceptViewProps) {
  const [result, formAction] = useActionState(action, IDLE);

  useEffect(() => {
    if (result.status === "success") {
      // Token'lı sorgu parametrelerini URL'den temizle (başarı ekranı görünmeye devam eder).
      try {
        window.history.replaceState(null, "", "/invitations/accept");
      } catch {
        // no-op: history yoksa (test) güvenli biçimde atla.
      }
    }
  }, [result]);

  // Başarılı kabul.
  if (result.status === "success") {
    return (
      <Panel>
        <h1 className="text-lg font-semibold text-slate-900">
          {result.duplicate ? "Bu davet zaten kabul edilmiş" : "Organizasyona katıldınız"}
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          {preview !== null ? (
            <>
              <span className="font-medium text-slate-900">{preview.organizationName}</span>{" "}
              organizasyonuna{" "}
              <span className="font-medium text-slate-900">{invitationRoleLabel(result.role)}</span>{" "}
              rolüyle erişiminiz var.
            </>
          ) : (
            <>Erişiminiz hazır.</>
          )}
        </p>
        <div className="mt-4">
          <ButtonLink href={dashboardHref}>Panele git</ButtonLink>
        </div>
      </Panel>
    );
  }

  // Önizleme hatası (geçersiz / bulunamadı / süresi dolmuş / servis).
  if (previewError !== null) {
    const messages: Record<AcceptPreviewError, string> = {
      invalid: "Bu davet bağlantısı geçersiz veya artık kullanılamıyor.",
      not_found: "Bu davet geçerli değil veya bulunamadı.",
      expired: "Bu davetin süresi dolmuş. Yeni bir davet isteyin.",
      unavailable: "Davet şu anda getirilemedi. Lütfen birkaç dakika sonra tekrar deneyin.",
    };
    return (
      <Panel>
        <h1 className="text-lg font-semibold text-slate-900">Davet</h1>
        <div className="mt-3">
          <Alert tone={previewError === "unavailable" ? "info" : "error"}>
            {messages[previewError]}
          </Alert>
        </div>
        <div className="mt-4">
          <ButtonLink href={dashboardHref} variant="secondary">
            Panele git
          </ButtonLink>
        </div>
      </Panel>
    );
  }

  if (preview === null) {
    return null;
  }

  // Zaten kabul edilmiş davet (token sahibine güvenli önizleme).
  if (preview.status === "accepted") {
    return (
      <Panel>
        <h1 className="text-lg font-semibold text-slate-900">Davet zaten kabul edilmiş</h1>
        <p className="mt-2 text-sm text-slate-600">
          <span className="font-medium text-slate-900">{preview.organizationName}</span>{" "}
          organizasyonuna bu davet daha önce kabul edilmiş.
        </p>
        <div className="mt-4">
          <ButtonLink href={dashboardHref}>Organizasyona git</ButtonLink>
        </div>
      </Panel>
    );
  }

  // Bekleyen davet (pending) — kabul akışı.
  return (
    <Panel>
      <h1 className="text-lg font-semibold text-slate-900">Organizasyona davet edildiniz</h1>
      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-slate-500">Organizasyon</dt>
          <dd className="font-medium text-slate-900">{preview.organizationName}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-slate-500">Rol</dt>
          <dd className="font-medium text-slate-900">{invitationRoleLabel(preview.role)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-slate-500">Son geçerlilik</dt>
          <dd className="text-slate-700">{formatDateTime(preview.expiresAt)}</dd>
        </div>
      </dl>

      {result.status === "error" ? (
        <div className="mt-4">
          <Alert tone="error">{result.message}</Alert>
        </div>
      ) : null}

      <div className="mt-5">
        {result.status === "error" && result.kind === "requires_login" ? (
          <ButtonLink href={loginHref}>Giriş yapıp kabul et</ButtonLink>
        ) : isAuthenticated ? (
          <form action={formAction}>
            <SubmitButton pendingLabel="Kabul ediliyor…">Daveti kabul et</SubmitButton>
          </form>
        ) : (
          <div className="flex flex-col gap-2">
            <ButtonLink href={loginHref}>Giriş yapıp kabul et</ButtonLink>
            <p className="text-xs text-slate-500">
              Daveti kabul etmek için giriş yapmanız gerekir. Giriş sonrası bu sayfaya
              döneceksiniz.
            </p>
          </div>
        )}
      </div>
    </Panel>
  );
}
