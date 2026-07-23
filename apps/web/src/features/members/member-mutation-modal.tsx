"use client";

/**
 * Üye mutasyonu için onaylı, erişilebilir modal (rol değiştirme + durum değiştirme paylaşır).
 *
 * - Optimistic concurrency: gizli `expectedVersion` güncel satırdan gelir.
 * - Çift submit `SubmitButton` (useFormStatus) ile engellenir.
 * - Başarı: modal içinde erişilebilir başarı mesajı (aria-live) gösterilir; liste server
 *   tarafında tazelenmiştir (revalidatePath). Duplicate (no-op) güvenli mesajla gösterilir.
 * - Stale (409 concurrency): otomatik retry YOK — mesaj gösterilir, resubmit engellenir; liste
 *   tazelendiği için kullanıcı kapatıp güncel version ile yeniden dener.
 */

import { useState } from "react";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { buttonClasses, type ButtonVariant } from "@/components/button";
import { Modal } from "@/components/modal";
import { SubmitButton } from "@/components/submit-button";
import type { MemberMutationResult } from "@/features/members/actions";

const IDLE: MemberMutationResult = { status: "idle" };

interface MemberMutationModalProps {
  readonly triggerLabel: string;
  readonly triggerVariant: ButtonVariant;
  readonly title: string;
  readonly confirmLabel: string;
  readonly pendingLabel: string;
  readonly confirmVariant: ButtonVariant;
  readonly successMessage: string;
  readonly duplicateMessage: string;
  readonly targetUserId: string;
  readonly expectedVersion: number;
  /** Durum değişimi için gönderilecek status; rol değişiminde undefined (children'daki select). */
  readonly status?: string;
  readonly action: (
    previous: MemberMutationResult,
    formData: FormData,
  ) => Promise<MemberMutationResult>;
  /** Açıklama + (rol modunda) rol seçici. */
  readonly children: React.ReactNode;
}

export function MemberMutationModal({
  triggerLabel,
  triggerVariant,
  title,
  confirmLabel,
  pendingLabel,
  confirmVariant,
  successMessage,
  duplicateMessage,
  targetUserId,
  expectedVersion,
  status,
  action,
  children,
}: MemberMutationModalProps) {
  const [open, setOpen] = useState(false);
  const [result, formAction] = useActionState(action, IDLE);
  // Kapatılan sonucu izle: aynı sonuç yeniden açılışta "taze" (idle) sayılır.
  const [dismissed, setDismissed] = useState<MemberMutationResult | null>(null);
  const active = result === dismissed ? IDLE : result;

  const close = () => {
    setOpen(false);
    setDismissed(result);
  };

  const isSuccess = active.status === "success";
  const isStale = active.status === "error" && active.kind === "stale";

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={buttonClasses(triggerVariant, "sm")}>
        {triggerLabel}
      </button>

      <Modal open={open} onClose={close} title={title}>
        {isSuccess ? (
          <div className="flex flex-col gap-4">
            <Alert tone="success">
              {active.status === "success" && active.duplicate ? duplicateMessage : successMessage}
            </Alert>
            <div className="flex justify-end">
              <button type="button" onClick={close} className={buttonClasses("secondary", "md")}>
                Kapat
              </button>
            </div>
          </div>
        ) : isStale ? (
          <div className="flex flex-col gap-4">
            {active.status === "error" ? <Alert tone="error">{active.message}</Alert> : null}
            <div className="flex justify-end">
              <button type="button" onClick={close} className={buttonClasses("secondary", "md")}>
                Kapat
              </button>
            </div>
          </div>
        ) : (
          <form action={formAction} className="flex flex-col gap-4">
            {active.status === "error" ? <Alert tone="error">{active.message}</Alert> : null}
            {/* Rol modunda children rol seçicisini (name="role") içerir; form içinde gönderilir. */}
            {children}
            <input type="hidden" name="targetUserId" value={targetUserId} />
            <input type="hidden" name="expectedVersion" value={expectedVersion} />
            {status !== undefined ? <input type="hidden" name="status" value={status} /> : null}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={close} className={buttonClasses("secondary", "md")}>
                Vazgeç
              </button>
              <SubmitButton pendingLabel={pendingLabel} variant={confirmVariant} fullWidth={false}>
                {confirmLabel}
              </SubmitButton>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
