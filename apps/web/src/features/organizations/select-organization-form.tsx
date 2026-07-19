"use client";

/**
 * Organizasyon seçim formu. Seçim server action ile cookie'ye yazılır ve backend'de
 * yeniden doğrulanır (cookie authorization değildir). UUID ana görsel bilgi DEĞİLDİR;
 * organizasyon adı + üyelik türü gösterilir.
 */

import Link from "next/link";
import { useActionState } from "react";

import { Alert } from "@/components/alert";
import { SubmitButton } from "@/components/submit-button";
import type { SelectOrganizationResult } from "@/features/organizations/select-actions";
import { membershipKindLabel } from "@/features/organizations/labels";
import type { MyOrganization } from "@/lib/api/resources";

interface SelectOrganizationFormProps {
  readonly organizations: readonly MyOrganization[];
  readonly action: (
    previous: SelectOrganizationResult,
    formData: FormData,
  ) => Promise<SelectOrganizationResult>;
}

const IDLE: SelectOrganizationResult = { status: "idle" };

export function SelectOrganizationForm({ organizations, action }: SelectOrganizationFormProps) {
  const [result, formAction] = useActionState(action, IDLE);

  return (
    <form action={formAction} className="flex flex-col gap-4">
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

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium text-slate-700">
          Devam etmek istediğin organizasyonu seç
        </legend>
        {organizations.map((organization, index) => (
          <label
            key={organization.organizationId}
            className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 transition-colors hover:border-blue-300 has-[:checked]:border-blue-500 has-[:checked]:ring-2 has-[:checked]:ring-blue-100"
          >
            <input
              type="radio"
              name="organizationId"
              value={organization.organizationId}
              defaultChecked={index === 0}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500"
            />
            <span className="flex flex-col">
              <span className="text-sm font-medium text-slate-900">{organization.name}</span>
              <span className="text-xs text-slate-500">
                {membershipKindLabel(organization.membershipKind)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <SubmitButton pendingLabel="Seçiliyor…">Bu organizasyonda devam et</SubmitButton>
    </form>
  );
}
