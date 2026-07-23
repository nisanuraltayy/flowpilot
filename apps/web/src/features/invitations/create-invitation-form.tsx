"use client";

/**
 * Davet oluşturma formu + başarı modalı.
 *
 * Güvenlik:
 * - Ham token YALNIZ `inviteUrl` içinde, modal AÇIKKEN gösterilir. Modal kapanınca
 *   (dismissed) URL artık render edilmez; log/analytics/storage'a hiç yazılmaz.
 * - Çift submit `SubmitButton` (useFormStatus) ile engellenir.
 * - Idempotency-Key ve token istemci storage'ına yazılmaz (server action üretir).
 */

import { useState } from "react";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { CopyButton } from "@/components/copy-button";
import { FormField } from "@/components/form-field";
import { Modal } from "@/components/modal";
import { SubmitButton } from "@/components/submit-button";
import type { CreateInvitationResult } from "@/features/invitations/actions";
import { invitationRoleLabel } from "@/features/invitations/display";

const IDLE: CreateInvitationResult = { status: "idle" };

interface CreateInvitationFormProps {
  readonly action: (
    previous: CreateInvitationResult,
    formData: FormData,
  ) => Promise<CreateInvitationResult>;
}

export function CreateInvitationForm({ action }: CreateInvitationFormProps) {
  const [result, formAction] = useActionState(action, IDLE);
  // Kapatılan sonuç referansı: modal yalnız GÜNCEL success için açık kalır. Yeni davet
  // (yeni result nesnesi) modalı yeniden açar; kapatınca token'lı URL artık gösterilmez.
  const [closedResult, setClosedResult] = useState<CreateInvitationResult | null>(null);
  const dismiss = () => setClosedResult(result);

  const showSuccess = result.status === "success" && result !== closedResult;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <form action={formAction} className="flex flex-col gap-4" noValidate>
        {result.status === "error" ? <Alert tone="error">{result.message}</Alert> : null}

        <FormField
          label="E-posta"
          name="email"
          type="email"
          autoComplete="email"
          required
          placeholder="ornek@sirket.com"
          hint="Davet edilen kişiye özel, tek kullanımlık bir bağlantı oluşturulur."
          errors={result.status === "error" ? result.fieldErrors?.email : undefined}
        />

        <div className="flex flex-col gap-1.5">
          <label htmlFor="role" className="text-sm font-medium text-slate-700">
            Rol
          </label>
          <select
            id="role"
            name="role"
            defaultValue="member"
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
          >
            <option value="member">Üye</option>
            <option value="admin">Yönetici</option>
          </select>
        </div>

        <div className="sm:max-w-[14rem]">
          <SubmitButton pendingLabel="Davet oluşturuluyor…">Davet oluştur</SubmitButton>
        </div>
      </form>

      {result.status === "success" && result.duplicate && result.inviteUrl === null ? (
        <div className="mt-4">
          <Alert tone="info">
            Bu e-posta için zaten bekleyen bir davet var. Güvenlik gereği bağlantı yeniden
            gösterilmez; gerekirse mevcut daveti iptal edip yeniden oluşturabilirsiniz.
          </Alert>
        </div>
      ) : null}

      <Modal
        open={showSuccess}
        onClose={dismiss}
        title="Davet oluşturuldu"
      >
        {result.status === "success" ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-slate-600">
              <span className="font-medium text-slate-900">{result.invitedEmail}</span> adresine{" "}
              <span className="font-medium text-slate-900">{invitationRoleLabel(result.role)}</span>{" "}
              rolüyle davet hazır. Aşağıdaki bağlantıyı davet edilen kişiyle paylaşın —{" "}
              <span className="font-medium">bu bağlantı yalnız bir kez gösterilir.</span>
            </p>
            {result.inviteUrl !== null ? (
              <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <code className="block break-all text-xs text-slate-700">{result.inviteUrl}</code>
                <CopyButton value={result.inviteUrl} />
              </div>
            ) : (
              <Alert tone="info">Bu davet için bağlantı yeniden gösterilemiyor.</Alert>
            )}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={dismiss}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
              >
                Kapat
              </button>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
