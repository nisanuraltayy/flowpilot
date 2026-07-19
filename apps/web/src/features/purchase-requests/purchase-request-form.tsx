"use client";

/**
 * Satın alma talebi formu.
 *
 * - Actor/organization/workflow/approver FORM ALANI DEĞİLDİR (server context'ten gelir).
 * - Tutar TL biçiminde girilir; kuruşa dönüşüm ve nihai doğrulama server'da.
 * - Pending sırasında SubmitButton disabled → çift submit engellenir.
 * - Başarıda action detay sayfasına yönlendirir (redirect); burada success dalı yok.
 */

import Link from "next/link";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { FormField } from "@/components/form-field";
import { SubmitButton } from "@/components/submit-button";
import type { CreatePurchaseRequestResult } from "@/features/purchase-requests/actions";
import {
  DESCRIPTION_MAX_LENGTH,
  TITLE_MAX_LENGTH,
} from "@/features/purchase-requests/schemas";

interface PurchaseRequestFormProps {
  readonly action: (
    previous: CreatePurchaseRequestResult,
    formData: FormData,
  ) => Promise<CreatePurchaseRequestResult>;
}

const IDLE: CreatePurchaseRequestResult = { status: "idle" };

export function PurchaseRequestForm({ action }: PurchaseRequestFormProps) {
  const [result, formAction] = useActionState(action, IDLE);
  const fieldErrors = result.status === "error" ? result.fieldErrors : undefined;

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
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

      <FormField
        label="Başlık"
        name="title"
        type="text"
        required
        maxLength={TITLE_MAX_LENGTH}
        placeholder="Örn. Yeni dizüstü bilgisayar"
        hint={`Kısa ve açıklayıcı bir başlık (1–${TITLE_MAX_LENGTH} karakter).`}
        errors={fieldErrors?.title}
      />

      <div className="flex flex-col gap-1.5">
        <label htmlFor="description" className="text-sm font-medium text-slate-700">
          Açıklama <span className="font-normal text-slate-400">(isteğe bağlı)</span>
        </label>
        <textarea
          id="description"
          name="description"
          rows={3}
          maxLength={DESCRIPTION_MAX_LENGTH}
          placeholder="Talebin gerekçesi veya ayrıntıları"
          aria-invalid={fieldErrors?.description ? true : undefined}
          aria-describedby={fieldErrors?.description ? "description-error" : undefined}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />
        {fieldErrors?.description ? (
          <p id="description-error" role="alert" className="text-xs font-medium text-red-600">
            {fieldErrors.description.join(" ")}
          </p>
        ) : null}
      </div>

      <FormField
        label="Tutar (₺)"
        name="amount"
        type="text"
        inputMode="decimal"
        required
        placeholder="Örn. 12.500,50"
        hint="Türk Lirası. Kuruş için virgül kullanın (örn. 12500,50)."
        errors={fieldErrors?.amount}
      />

      <aside className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-600">
        <p className="font-medium text-slate-700">Onay zinciri (bilgi)</p>
        <ul className="mt-1 space-y-0.5">
          <li>10.000 ₺ altı: Ekip yöneticisi</li>
          <li>10.000–50.000 ₺: Ekip yöneticisi + Finans</li>
          <li>50.000 ₺ üzeri: Ekip yöneticisi + Finans + Genel müdür</li>
        </ul>
        <p className="mt-1 text-slate-400">
          Zincir, tutara göre süreç tarafından otomatik belirlenir.
        </p>
      </aside>

      <SubmitButton pendingLabel="Oluşturuluyor…">Talebi oluştur</SubmitButton>
    </form>
  );
}
