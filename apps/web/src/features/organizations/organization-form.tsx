"use client";

/**
 * Organization onboarding formu.
 *
 * - Actor/owner/tenant ID FORM ALANI DEĞİLDİR — kimlik yalnız server tarafında
 *   doğrulanmış oturumdan gelir.
 * - Başarı durumunda ID'ler ana görsel öğe yapılmaz; teknik detay olarak
 *   katlanabilir alanda gösterilir.
 */

import Link from "next/link";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { FormField } from "@/components/form-field";
import { SubmitButton } from "@/components/submit-button";
import type { CreateOrganizationActionResult } from "@/features/organizations/actions";
import { ORGANIZATION_NAME_MAX_LENGTH } from "@/features/organizations/schemas";

interface OrganizationFormProps {
  readonly action: (
    previous: CreateOrganizationActionResult,
    formData: FormData,
  ) => Promise<CreateOrganizationActionResult>;
}

const IDLE: CreateOrganizationActionResult = { status: "idle" };

export function OrganizationForm({ action }: OrganizationFormProps) {
  const [result, formAction] = useActionState(action, IDLE);

  if (result.status === "success") {
    return (
      <div className="flex flex-col gap-4">
        <Alert tone="success">
          <p className="font-semibold">&quot;{result.name}&quot; organizasyonu oluşturuldu.</p>
          <p className="mt-1">
            Owner üyeliğin de oluşturuldu — bu organizasyonun sahibi sensin.
          </p>
        </Alert>
        <details className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
          <summary className="cursor-pointer font-medium text-slate-600">
            Teknik detaylar
          </summary>
          <dl className="mt-2 space-y-1">
            <div>
              <dt className="inline font-medium">Organizasyon ID: </dt>
              <dd className="inline font-mono">{result.organizationId}</dd>
            </div>
            <div>
              <dt className="inline font-medium">Owner üyelik ID: </dt>
              <dd className="inline font-mono">{result.ownerMembershipId}</dd>
            </div>
          </dl>
        </details>
        <Link
          href="/dashboard"
          className="inline-flex w-full items-center justify-center rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Panele devam et
        </Link>
      </div>
    );
  }

  return (
    <form action={formAction} className="flex flex-col gap-4" noValidate>
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
        label="Organizasyon adı"
        name="name"
        type="text"
        required
        maxLength={ORGANIZATION_NAME_MAX_LENGTH}
        placeholder="Örn. Acme Teknoloji"
        hint={`1–${ORGANIZATION_NAME_MAX_LENGTH} karakter. Şirketinin görünen adı.`}
        errors={result.status === "error" ? result.fieldErrors?.name : undefined}
      />

      <SubmitButton pendingLabel="Oluşturuluyor…">Şirketini oluştur</SubmitButton>
    </form>
  );
}
