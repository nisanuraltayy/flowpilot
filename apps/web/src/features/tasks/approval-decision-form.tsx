"use client";

/**
 * Onay kararı formu (approve / reject + isteğe bağlı yorum).
 *
 * - Onay ve ret görsel olarak net ayrılır (ikon + metin + kenar rengi) — yalnız
 *   renkle değil.
 * - Pending sırasında iki buton da disabled → çift submit engellenir.
 * - Optimistic UI YOK: karar backend'de onaylanır; başarıda action talep detayına
 *   yönlendirir. Hata (ör. 409 çakışma) satır içi güvenli mesaj olarak gösterilir.
 */

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Alert } from "@/components/alert";
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
    <div className="flex flex-wrap gap-2">
      <button
        type="submit"
        name="decision"
        value="approve"
        disabled={pending}
        className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-green-300"
      >
        <span aria-hidden="true">✓</span>
        {pending ? "Gönderiliyor…" : "Onayla"}
      </button>
      <button
        type="submit"
        name="decision"
        value="reject"
        disabled={pending}
        className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 shadow-sm transition-colors hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span aria-hidden="true">✕</span>
        {pending ? "Gönderiliyor…" : "Reddet"}
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
          placeholder="Kararınıza ilişkin not"
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />
      </div>

      <DecisionButtons />
    </form>
  );
}
