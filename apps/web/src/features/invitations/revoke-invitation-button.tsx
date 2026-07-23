"use client";

/**
 * Davet iptal (revoke) butonu — onay diyaloğu ile. Yalnız bekleyen davetlerde gösterilir.
 * Başarılı iptalde liste server tarafında tazelenir (revalidatePath).
 */

import { useState } from "react";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { buttonClasses } from "@/components/button";
import { Modal } from "@/components/modal";
import { SubmitButton } from "@/components/submit-button";
import type { RevokeInvitationResult } from "@/features/invitations/actions";

const IDLE: RevokeInvitationResult = { status: "idle" };

interface RevokeInvitationButtonProps {
  readonly invitationId: string;
  readonly invitedEmail: string;
  readonly action: (
    previous: RevokeInvitationResult,
    formData: FormData,
  ) => Promise<RevokeInvitationResult>;
}

export function RevokeInvitationButton({
  invitationId,
  invitedEmail,
  action,
}: RevokeInvitationButtonProps) {
  const [open, setOpen] = useState(false);
  const [result, formAction] = useActionState(action, IDLE);

  // Başarılı iptalde diyalog gizlenir (liste server tarafında tazelenir; satır kaybolur).
  const modalOpen = open && result.status !== "success";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={buttonClasses("danger", "sm")}
      >
        İptal et
      </button>

      <Modal open={modalOpen} onClose={() => setOpen(false)} title="Daveti iptal et">
        <div className="flex flex-col gap-4">
          {result.status === "error" ? <Alert tone="error">{result.message}</Alert> : null}
          <p className="text-sm text-slate-600">
            <span className="font-medium text-slate-900">{invitedEmail}</span> adresine gönderilen
            bekleyen daveti iptal etmek istediğinize emin misiniz? Bu bağlantı bir daha
            kullanılamaz.
          </p>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className={buttonClasses("secondary", "md")}
            >
              Vazgeç
            </button>
            <form action={formAction}>
              <input type="hidden" name="invitationId" value={invitationId} />
              <SubmitButton pendingLabel="İptal ediliyor…" variant="danger" fullWidth={false}>
                Evet, iptal et
              </SubmitButton>
            </form>
          </div>
        </div>
      </Modal>
    </>
  );
}
