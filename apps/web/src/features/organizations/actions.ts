"use server";

/**
 * Organization onboarding server action'ı.
 *
 * Akış: session'daki access token YALNIZ server tarafında okunur ve YALNIZ
 * FastAPI'ye iletilir. FastAPI token'ı kendi JWT adapter'ıyla YENİDEN doğrular;
 * session'daki user nesnesi backend authorization kararı için KULLANILMAZ.
 * Token browser component'e, form state'e veya log'a DÖNMEZ.
 *
 * Actor/owner/tenant ID kullanıcı formundan ALINMAZ — kimlik yalnız
 * doğrulanmış token'dan gelir.
 */

import {
  errorResult,
  SUPABASE_NOT_CONFIGURED_MESSAGE,
} from "@/features/auth/action-result";
import { writeActiveOrganizationCookie } from "@/features/organizations/context";
import { organizationNameSchema } from "@/features/organizations/schemas";
import { createOrganization } from "@/lib/api/flowpilot-api";
import { createClient } from "@/lib/supabase/server";

export type CreateOrganizationActionResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly message: string;
      readonly fieldErrors?: Readonly<Record<string, readonly string[]>>;
      readonly requiresLogin?: boolean;
    }
  | {
      readonly status: "success";
      readonly organizationId: string;
      readonly ownerMembershipId: string;
      readonly name: string;
    };

export async function createOrganizationAction(
  _previous: CreateOrganizationActionResult,
  formData: FormData,
): Promise<CreateOrganizationActionResult> {
  // Hızlı istemci-yakın doğrulama; NİHAİ kaynak backend'dir.
  const parsed = organizationNameSchema.safeParse({ name: formData.get("name") });
  if (!parsed.success) {
    return errorResult("Lütfen organizasyon adını kontrol edin.", {
      name: parsed.error.issues.map((issue) => issue.message),
    });
  }

  const supabase = await createClient();
  if (supabase === null) {
    return errorResult(SUPABASE_NOT_CONFIGURED_MESSAGE);
  }

  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (session === null) {
    return {
      status: "error",
      message: "Oturumunuz sona ermiş. Lütfen yeniden giriş yapın.",
      requiresLogin: true,
    };
  }

  const outcome = await createOrganization(session.access_token, parsed.data.name);

  switch (outcome.kind) {
    case "created":
      // Yeni organizasyon oluşturulunca aktif org context'i olarak yazılır
      // (owner #4/#5 tek-kullanıcı akışının doğrudan dashboard'a geçebilmesi için).
      await writeActiveOrganizationCookie(outcome.organization.organizationId);
      return {
        status: "success",
        organizationId: outcome.organization.organizationId,
        ownerMembershipId: outcome.organization.ownerMembershipId,
        name: outcome.organization.name,
      };
    case "unauthorized":
      return {
        status: "error",
        message: "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.",
        requiresLogin: true,
      };
    case "validation_error":
      return errorResult(outcome.message, { name: [outcome.message] });
    case "service_unavailable":
      return errorResult(
        "Kimlik doğrulama servisine şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.",
      );
    case "network_error":
      return errorResult(
        "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.",
      );
    case "server_error":
      return errorResult("Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.");
  }
}
