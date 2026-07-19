"use server";

/**
 * Satın alma talebi oluşturma server action'ı.
 *
 * Actor, organization, workflow ve approver chain KULLANICI FORMUNDAN ALINMAZ:
 * kimlik doğrulanmış oturumdan, aktif organizasyon server-side cookie context'inden
 * (backend'de yeniden doğrulanan) gelir. Tutar TL metninden float ÜRETMEDEN kuruşa
 * çevrilir; nihai doğrulama backend'dedir.
 */

import { redirect } from "next/navigation";

import { requireActiveOrganization } from "@/features/organizations/context";
import { purchaseRequestFormSchema } from "@/features/purchase-requests/schemas";
import { CURRENCY_TRY, parseTryToMinor } from "@/lib/money";
import { createPurchaseRequest } from "@/lib/api/resources";

export type CreatePurchaseRequestResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly message: string;
      readonly fieldErrors?: Readonly<Record<string, readonly string[]>>;
      readonly requiresLogin?: boolean;
    };

const MONEY_ERROR: Record<"empty" | "format" | "non_positive", string> = {
  empty: "Tutar gerekli.",
  format: "Geçerli bir tutar girin (örn. 12.500,50).",
  non_positive: "Tutar sıfırdan büyük olmalı.",
};

function fieldErrorsFromZod(error: {
  issues: readonly { path: readonly PropertyKey[]; message: string }[];
}): Record<string, string[]> {
  const fields: Record<string, string[]> = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "form");
    fields[key] = [...(fields[key] ?? []), issue.message];
  }
  return fields;
}

export async function createPurchaseRequestAction(
  _previous: CreatePurchaseRequestResult,
  formData: FormData,
): Promise<CreatePurchaseRequestResult> {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return {
      status: "error",
      message: "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.",
    };
  }

  const parsed = purchaseRequestFormSchema.safeParse({
    title: formData.get("title"),
    description: formData.get("description"),
    amount: formData.get("amount"),
  });
  if (!parsed.success) {
    return {
      status: "error",
      message: "Lütfen alanları kontrol edin.",
      fieldErrors: fieldErrorsFromZod(parsed.error),
    };
  }

  const money = parseTryToMinor(parsed.data.amount);
  if (!money.ok) {
    return {
      status: "error",
      message: "Lütfen tutarı kontrol edin.",
      fieldErrors: { amount: [MONEY_ERROR[money.reason]] },
    };
  }

  const description = parsed.data.description.trim();
  const outcome = await createPurchaseRequest(
    context.accessToken,
    context.organization.organizationId,
    {
      title: parsed.data.title,
      description: description === "" ? null : description,
      amountMinor: money.amountMinor,
      currency: CURRENCY_TRY,
    },
  );

  if (outcome.kind === "ok") {
    // redirect() never döndürür; sonrası çalışmaz. TS `outcome`'u non-ok'a daraltır.
    redirect(`/purchase-requests/${outcome.data.purchaseRequestId}`);
  }

  switch (outcome.kind) {
    case "validation_error":
      return {
        status: "error",
        message: outcome.message,
        fieldErrors: { amount: [outcome.message] },
      };
    case "conflict":
      return { status: "error", message: outcome.message };
    case "unauthorized":
      return { status: "error", message: "Oturumunuz sona ermiş.", requiresLogin: true };
    case "not_found":
      return { status: "error", message: "Organizasyon bulunamadı." };
    case "service_unavailable":
      return {
        status: "error",
        message: "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.",
      };
    case "network_error":
      return {
        status: "error",
        message: "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.",
      };
    case "server_error":
      return { status: "error", message: "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin." };
  }
}
