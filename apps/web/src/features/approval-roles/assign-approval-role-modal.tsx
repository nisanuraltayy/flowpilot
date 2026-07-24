"use client";

/**
 * Onay rolü atama/değiştirme modalı (onaylı, erişilebilir).
 *
 * - Adaylar YALNIZ aktif üyelerdir (backend de aktif olmayanı 409 ile reddeder).
 * - Mevcut atanan kullanıcı belirgin gösterilir; onu tekrar seçmek no-op'tur (submit engellenir).
 * - Optimistic concurrency: gizli expectedVersion mevcut atamadan gelir (ilk atamada gönderilmez).
 * - Çift submit `SubmitButton` (useFormStatus) ile engellenir.
 * - Stale (409/422-refresh): otomatik retry YOK — mesaj gösterilir, resubmit engellenir; liste
 *   tazelendiği için kullanıcı kapatıp güncel version ile yeniden dener.
 */

import { useState } from "react";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { buttonClasses } from "@/components/button";
import { Modal } from "@/components/modal";
import { SubmitButton } from "@/components/submit-button";
import type { ApprovalRoleMutationResult } from "@/features/approval-roles/actions";
import type { AssignApprovalRoleAction } from "@/features/approval-roles/action-types";
import { memberEmailLabel, memberRoleLabel } from "@/features/members/display";
import type { MemberListItem } from "@/lib/api/resources";

const IDLE: ApprovalRoleMutationResult = { status: "idle" };

interface AssignApprovalRoleModalProps {
  readonly roleKey: string;
  readonly roleLabel: string;
  readonly triggerLabel: string;
  readonly successMessage: string;
  readonly currentAssigneeId: string | null;
  readonly currentVersion: number | null;
  readonly candidates: readonly MemberListItem[];
  readonly actorEmail: string | null;
  readonly action: AssignApprovalRoleAction;
}

function candidateLabel(member: MemberListItem, actorEmail: string | null): string {
  const email = memberEmailLabel(member.email);
  const role = memberRoleLabel(member.role);
  const self =
    actorEmail !== null &&
    member.email !== null &&
    actorEmail.trim().toLowerCase() === member.email.trim().toLowerCase();
  return `${email} — ${role}${self ? " (Siz)" : ""}`;
}

export function AssignApprovalRoleModal({
  roleKey,
  roleLabel,
  triggerLabel,
  successMessage,
  currentAssigneeId,
  currentVersion,
  candidates,
  actorEmail,
  action,
}: AssignApprovalRoleModalProps) {
  const [open, setOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string>(currentAssigneeId ?? "");
  const [result, formAction] = useActionState(action, IDLE);
  const [dismissed, setDismissed] = useState<ApprovalRoleMutationResult | null>(null);
  const active = result === dismissed ? IDLE : result;

  const close = () => {
    setOpen(false);
    setDismissed(result);
    setSelectedUserId(currentAssigneeId ?? "");
  };

  const isSuccess = active.status === "success";
  const isStale = active.status === "error" && active.kind === "stale";
  // No-op engeli: seçim yok ya da mevcut atananla aynı → submit edilemez.
  const noSelection = selectedUserId === "";
  const isNoop = selectedUserId === currentAssigneeId;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={buttonClasses("secondary", "sm")}
      >
        {triggerLabel}
      </button>

      <Modal open={open} onClose={close} title={`${roleLabel} — kullanıcı ata`}>
        {isSuccess ? (
          <div className="flex flex-col gap-4">
            <Alert tone="success">
              {active.status === "success" && active.duplicate
                ? "Bu kullanıcı zaten ilgili onay rolüne atanmış."
                : successMessage}
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

            <p className="text-sm text-slate-600">
              Bu değişiklik yalnız <span className="font-medium">yeni oluşturulacak</span> onay
              görevlerini etkiler; mevcut açık görevlerin ataması korunur.
            </p>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor={`assignee-${roleKey}`}
                className="text-sm font-medium text-slate-700"
              >
                Kullanıcı
              </label>
              <select
                id={`assignee-${roleKey}`}
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
              >
                <option value="">Kullanıcı seçin</option>
                {candidates.map((member) => (
                  <option key={member.userId} value={member.userId}>
                    {candidateLabel(member, actorEmail)}
                    {member.userId === currentAssigneeId ? " — mevcut" : ""}
                  </option>
                ))}
              </select>
              {isNoop && !noSelection ? (
                <p className="text-xs text-slate-500">
                  Bu kullanıcı bu role zaten atanmış. Değiştirmek için farklı bir kullanıcı seçin.
                </p>
              ) : null}
            </div>

            <input type="hidden" name="roleKey" value={roleKey} />
            <input type="hidden" name="userId" value={selectedUserId} />
            {currentVersion !== null ? (
              <input type="hidden" name="expectedVersion" value={currentVersion} />
            ) : null}

            <div className="flex justify-end gap-2">
              <button type="button" onClick={close} className={buttonClasses("secondary", "md")}>
                Vazgeç
              </button>
              <SubmitButtonGuarded disabled={noSelection || isNoop} />
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}

/**
 * Submit butonu — seçim yoksa/no-op ise disabled. `SubmitButton` pending'de zaten disabled;
 * burada ek olarak geçersiz seçimde de engellenir (çift submit + no-op koruması).
 */
function SubmitButtonGuarded({ disabled }: { readonly disabled: boolean }) {
  if (disabled) {
    return (
      <button
        type="submit"
        disabled
        className={`${buttonClasses("primary", "md")}`}
        aria-disabled="true"
      >
        Kaydet
      </button>
    );
  }
  return (
    <SubmitButton pendingLabel="Atanıyor…" fullWidth={false}>
      Kaydet
    </SubmitButton>
  );
}
