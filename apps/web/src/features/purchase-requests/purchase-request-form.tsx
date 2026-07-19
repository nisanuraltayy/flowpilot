"use client";

/**
 * Satın alma talebi formu.
 *
 * - Actor/organization/workflow/approver FORM ALANI DEĞİLDİR (server context'ten gelir).
 * - Tutar TL biçiminde girilir (₺ göstergesi); kuruşa dönüşüm + nihai doğrulama server'da.
 * - Pending sırasında SubmitButton disabled → çift submit engellenir.
 * - Başarıda action detay sayfasına yönlendirir (redirect); burada success dalı yok.
 */

import Link from "next/link";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { buttonClasses } from "@/components/button";
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
  const amountError = fieldErrors?.amount;

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
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
        {fieldErrors?.description ? (
          <p id="description-error" role="alert" className="text-xs font-medium text-red-600">
            {fieldErrors.description.join(" ")}
          </p>
        ) : null}
      </div>

      {/* Tutar — ₺ göstergeli */}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="amount" className="text-sm font-medium text-slate-700">
          Tutar
        </label>
        <div
          className={`flex items-center rounded-lg border bg-white shadow-sm transition-colors focus-within:ring-2 ${
            amountError
              ? "border-red-400 focus-within:border-red-500 focus-within:ring-red-100"
              : "border-slate-300 focus-within:border-brand-500 focus-within:ring-brand-100"
          }`}
        >
          <span
            aria-hidden="true"
            className="select-none pl-3 pr-1 text-sm font-medium text-slate-500"
          >
            ₺
          </span>
          <input
            id="amount"
            name="amount"
            type="text"
            inputMode="decimal"
            required
            placeholder="12.500,50"
            aria-invalid={amountError ? true : undefined}
            aria-describedby={`amount-hint${amountError ? " amount-error" : ""}`}
            className="w-full rounded-lg border-0 bg-transparent px-2 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400"
          />
        </div>
        <p id="amount-hint" className="text-xs text-slate-500">
          Türk Lirası. Kuruş için virgül kullanın (örn. 12500,50).
        </p>
        {amountError ? (
          <p id="amount-error" role="alert" className="text-xs font-medium text-red-600">
            {amountError.join(" ")}
          </p>
        ) : null}
      </div>

      <div className="flex flex-col-reverse gap-3 pt-1 sm:flex-row sm:items-center sm:justify-end">
        <Link href="/purchase-requests" className={buttonClasses("secondary", "md")}>
          İptal
        </Link>
        <SubmitButton pendingLabel="Oluşturuluyor…" fullWidth={false}>
          Talebi oluştur
        </SubmitButton>
      </div>
    </form>
  );
}
