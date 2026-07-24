"use client";

/**
 * Engellenen görevin atamasını çözme onay modalı (aday SEÇİMİ YOK).
 *
 * Backend adayı mevcut aktif rol atamasından kendisi seçer — bu yüzden modal bir ONAY diyaloğudur,
 * kullanıcı seçimi içermez. Görevin yalnız bu adımı etkilendiği ve onay rolü yapılandırmasının
 * DEĞİŞMEDİĞİ açıkça belirtilir. Çift submit `SubmitButton` (useFormStatus) ile engellenir.
 * Başarıdan sonra liste server tarafında tazelenir (revalidatePath) ve görev listeden düşer.
 * Çakışma/stale durumunda otomatik retry YOK — mesaj gösterilir, liste tazelenir; kullanıcı
 * kapatıp güncel durumu görür.
 */

import { useState } from "react";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { buttonClasses } from "@/components/button";
import { Modal } from "@/components/modal";
import { SubmitButton } from "@/components/submit-button";
import type { BlockedTaskResolveResult } from "@/features/blocked-tasks/actions";
import type { ResolveBlockedTaskAction } from "@/features/blocked-tasks/action-types";
import { blockedReasonDescription, blockedReasonLabel } from "@/features/blocked-tasks/display";
import { approvalRoleLabel } from "@/features/approval-roles/display";

const IDLE: BlockedTaskResolveResult = { status: "idle" };

interface ResolveBlockedTaskModalProps {
  readonly taskId: string;
  readonly approverRole: string;
  readonly blockedReason: string | null;
  readonly action: ResolveBlockedTaskAction;
}

export function ResolveBlockedTaskModal({
  taskId,
  approverRole,
  blockedReason,
  action,
}: ResolveBlockedTaskModalProps) {
  const [open, setOpen] = useState(false);
  const [result, formAction] = useActionState(action, IDLE);
  const [dismissed, setDismissed] = useState<BlockedTaskResolveResult | null>(null);
  const active = result === dismissed ? IDLE : result;

  const close = () => {
    setOpen(false);
    setDismissed(result);
  };

  const isSuccess = active.status === "success";
  // Çakışma/bulunamadı: görev durumu değişmiştir (liste tazelendi) → resubmit engellenir.
  const isStaleConflict =
    active.status === "error" &&
    (active.kind === "not_blocked" ||
      active.kind === "not_found" ||
      active.kind === "conflict" ||
      active.kind === "candidate_inactive");

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className={buttonClasses("secondary", "sm")}>
        Atamayı çöz
      </button>

      <Modal open={open} onClose={close} title="Onay görevinin atamasını çöz">
        {isSuccess ? (
          <div className="flex flex-col gap-4">
            <Alert tone="success">Onay görevinin atama sorunu çözüldü.</Alert>
            <div className="flex justify-end">
              <button type="button" onClick={close} className={buttonClasses("secondary", "md")}>
                Kapat
              </button>
            </div>
          </div>
        ) : isStaleConflict ? (
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

            <dl className="flex flex-col gap-1.5 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Gereken onay rolü</dt>
                <dd className="font-medium text-slate-900">{approvalRoleLabel(approverRole)}</dd>
              </div>
              <div className="flex flex-col gap-0.5">
                <dt className="text-slate-500">Engellenme nedeni</dt>
                <dd className="text-slate-700">{blockedReasonLabel(blockedReason)}</dd>
              </div>
            </dl>

            <p className="text-sm text-slate-600">{blockedReasonDescription(blockedReason)}</p>

            <p className="text-sm text-slate-600">
              Görev, <span className="font-medium">{approvalRoleLabel(approverRole)}</span> rolüne
              atanmış uygun kullanıcıya verilecek. Bu işlem yalnız{" "}
              <span className="font-medium">bu görevi</span> etkiler ve onay rolü yapılandırmasını
              değiştirmez.
            </p>

            <input type="hidden" name="taskId" value={taskId} />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={close} className={buttonClasses("secondary", "md")}>
                Vazgeç
              </button>
              <SubmitButton pendingLabel="Çözülüyor…" fullWidth={false}>
                Atamayı çöz
              </SubmitButton>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
