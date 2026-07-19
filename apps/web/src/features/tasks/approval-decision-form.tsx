"use client";

/**
 * Onay kararı formu (approve / reject + isteğe bağlı yorum).
 *
 * - Onay ve ret görsel olarak net ayrılır (ikon + metin + kenar/renk) — yalnız renkle değil.
 * - Pending sırasında iki buton da disabled → çift submit engellenir.
 * - Optimistic UI YOK: karar backend'de onaylanır; başarıda action talep detayına
 *   yönlendirir. Hata (ör. 409 çakışma / ağ) satır içi güvenli mesaj olarak gösterilir.
 */

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Alert } from "@/components/alert";
import { buttonClasses } from "@/components/button";
import { CheckIcon, XIcon } from "@/components/icons";
import type { DecideTaskResult } from "@/features/tasks/actions";

interface ApprovalDecisionFormProps {
  readonly taskId: string;
  readonly action: (
    previous: DecideTaskResult,
    formData: FormData,
  ) => Promise<DecideTaskResult>;
}

const IDLE: DecideTaskResult = { status: "idle" };

function DecisionButtons() {
  const { pending } = useFormStatus();
  return (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <button
        type="submit"
        name="decision"
        value="reject"
        disabled={pending}
        aria-busy={pending}
        className={buttonClasses("danger", "md")}
      >
        <XIcon className="h-4 w-4" />
        {pending ? "Gönderiliyor…" : "Reddet"}
      </button>
      <button
        type="submit"
        name="decision"
        value="approve"
        disabled={pending}
        aria-busy={pending}
        className={buttonClasses("success", "md")}
      >
        <CheckIcon className="h-4 w-4" />
        {pending ? "Gönderiliyor…" : "Onayla"}
      </button>
    </div>
  );
}

export function ApprovalDecisionForm({ taskId, action }: ApprovalDecisionFormProps) {
  const [result, formAction] = useActionState(action, IDLE);

  return (
    <form action={formAction} className="flex flex-col gap-3">
      <input type="hidden" name="taskId" value={taskId} />

      {result.status === "error" ? (
        <Alert tone="error">
          {result.message}
          {result.requiresLogin ? (
            <>
              {" "}
              <Link href="/login" className="font-medium underline">
                Giriş sayfasına git
              </Link>
            </>
          ) : null}
        </Alert>
      ) : null}

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`comment-${taskId}`} className="text-sm font-medium text-slate-700">
          Yorum <span className="font-normal text-slate-400">(isteğe bağlı)</span>
        </label>
        <textarea
          id={`comment-${taskId}`}
          name="comment"
          rows={2}
          maxLength={2000}
          placeholder="Kararınıza ilişkin kısa bir not ekleyebilirsiniz"
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
      </div>

      <DecisionButtons />
    </form>
  );
}
