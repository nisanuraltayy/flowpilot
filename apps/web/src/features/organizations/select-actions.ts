"use server";

/**
 * Organizasyon seçim server action'ı.
 *
 * Cookie authorization DEĞİLDİR: seçilen org UUID'si, actor'ın AKTİF üyelikleri
 * arasında YENİDEN doğrulanır (listMyOrganizations — actor-scoped RLS). Kullanıcı
 * rastgele bir UUID gönderse bile üye değilse seçim reddedilir.
 */

import { redirect } from "next/navigation";

import {
  getServerAccessToken,
  writeActiveOrganizationCookie,
} from "@/features/organizations/context";
import { listMyOrganizations } from "@/lib/api/resources";

export type SelectOrganizationResult =
  | { readonly status: "idle" }
  | { readonly status: "error"; readonly message: string; readonly requiresLogin?: boolean };

export async function selectOrganizationAction(
  _previous: SelectOrganizationResult,
  formData: FormData,
): Promise<SelectOrganizationResult> {
  const organizationId = String(formData.get("organizationId") ?? "").trim();
  if (organizationId === "") {
    return { status: "error", message: "Lütfen bir organizasyon seçin." };
  }

  const accessToken = await getServerAccessToken();
  if (accessToken === null) {
    return { status: "error", message: "Oturumunuz sona ermiş.", requiresLogin: true };
  }

  const outcome = await listMyOrganizations(accessToken);
  if (outcome.kind === "unauthorized") {
    return { status: "error", message: "Oturumunuz doğrulanamadı.", requiresLogin: true };
  }
  if (outcome.kind !== "ok") {
    return {
      status: "error",
      message: "Organizasyonlar şu anda getirilemedi. Lütfen tekrar deneyin.",
    };
  }

  const isActiveMember = outcome.data.some(
    (organization) => organization.organizationId === organizationId,
  );
  if (!isActiveMember) {
    return { status: "error", message: "Bu organizasyon seçilemedi." };
  }

  await writeActiveOrganizationCookie(organizationId);
  redirect("/dashboard");
}
