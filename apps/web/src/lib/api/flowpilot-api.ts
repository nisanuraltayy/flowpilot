/**
 * FlowPilot FastAPI istemcisi — YALNIZ SERVER-SIDE.
 *
 * `server-only` import'u, bu modülün yanlışlıkla client bundle'a girmesini
 * DERLEME ANINDA engeller: browser'dan doğrudan Bearer isteği yapılamaz.
 *
 * Kurallar:
 * - Native fetch, `cache: "no-store"`, kontrollü timeout.
 * - Token loglanmaz; hata mesajlarına yazılmaz.
 * - Backend yanıtı KÖR GÜVENİLMEZ: Zod ile doğrulanır.
 * - Backend'in teknik detayı kullanıcıya taşınmaz; hatalar kontrollü,
 *   kullanıcı dostu sonuçlara eşlenir.
 * - Otomatik retry YOKTUR (kullanıcıya yeniden deneme önerilir).
 *
 * NOT: Şimdilik tek endpoint için küçük, lokal transport tipleri kullanılır.
 * OpenAPI'den üretilmiş TypeScript client'ı gelecekte packages/contracts
 * altında oluşturulacaktır (bkz. packages/contracts/README.md) — burada
 * paralel bir business model source-of-truth'u OLUŞTURULMAZ.
 */

import "server-only";

import { z } from "zod";

import { getApiBaseUrl } from "@/lib/env";

const REQUEST_TIMEOUT_MS = 10_000;

/** POST /v1/organizations — 201 yanıt şeması (backend sözleşmesiyle birebir). */
const createOrganizationResponseSchema = z.object({
  organization_id: z.uuid(),
  owner_membership_id: z.uuid(),
  name: z.string().min(1),
});

export type CreateOrganizationSuccess = {
  readonly organizationId: string;
  readonly ownerMembershipId: string;
  readonly name: string;
};

export type CreateOrganizationOutcome =
  | { readonly kind: "created"; readonly organization: CreateOrganizationSuccess }
  | { readonly kind: "unauthorized" }
  | { readonly kind: "validation_error"; readonly message: string }
  | { readonly kind: "service_unavailable" }
  | { readonly kind: "server_error" }
  | { readonly kind: "network_error" };

const GENERIC_VALIDATION_MESSAGE = "Organizasyon adı geçersiz. Lütfen kontrol edin.";

function extractValidationMessage(body: unknown): string {
  // Backend'in kendi 422'si kullanıcı-dostu Türkçe `detail` string'i taşır.
  // FastAPI'nin otomatik 422'si ise teknik bir dizi döndürür — o KULLANICIYA
  // GÖSTERİLMEZ, generic mesaja düşülür.
  if (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof (body as { detail: unknown }).detail === "string"
  ) {
    return (body as { detail: string }).detail;
  }
  return GENERIC_VALIDATION_MESSAGE;
}

export async function createOrganization(
  accessToken: string,
  organizationName: string,
): Promise<CreateOrganizationOutcome> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/v1/organizations`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: organizationName }),
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    // Timeout, DNS, bağlantı reddi... Token veya teknik detay taşınmaz.
    return { kind: "network_error" };
  }

  if (response.status === 201) {
    let parsed: z.infer<typeof createOrganizationResponseSchema>;
    try {
      parsed = createOrganizationResponseSchema.parse(await response.json());
    } catch {
      // Bozuk/beklenmeyen gövde kabul EDİLMEZ.
      return { kind: "server_error" };
    }
    return {
      kind: "created",
      organization: {
        organizationId: parsed.organization_id,
        ownerMembershipId: parsed.owner_membership_id,
        name: parsed.name,
      },
    };
  }

  if (response.status === 401) {
    return { kind: "unauthorized" };
  }

  if (response.status === 422) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // gövde okunamadıysa generic mesaj kullanılır
    }
    return { kind: "validation_error", message: extractValidationMessage(body) };
  }

  if (response.status === 503) {
    return { kind: "service_unavailable" };
  }

  return { kind: "server_error" };
}
