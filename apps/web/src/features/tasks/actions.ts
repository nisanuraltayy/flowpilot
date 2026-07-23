"use server";

/**
 * Onay kararı (approve/reject) server action'ı.
 *
 * Idempotency-Key server tarafında üretilir (kullanıcıdan İSTENMEZ, token/actor'dan
 * TÜRETİLMEZ). Karar yetkisi backend'de task assignee'ye göre zorlanır; UI güvenliği
 * esas değildir. Optimistic UI YOK — sonuç backend yanıtından sonra gösterilir.
 */

import { randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireActiveOrganization } from "@/features/organizations/context";
import { decideApprovalTask } from "@/lib/api/resources";

export type DecideTaskResult =
  | { readonly status: "idle" }
  | { readonly status: "error"; readonly message: string; readonly requiresLogin?: boolean };

export async function decideApprovalTaskAction(
  _previous: DecideTaskResult,
  formData: FormData,
): Promise<DecideTaskResult> {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return {
      status: "error",
      message: "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.",
    };
  }

  const taskId = String(formData.get("taskId") ?? "").trim();
  const decisionRaw = String(formData.get("decision") ?? "");
  const comment = String(formData.get("comment") ?? "").trim();

  if (taskId === "" || (decisionRaw !== "approve" && decisionRaw !== "reject")) {
    return { status: "error", message: "Geçersiz karar isteği." };
  }
  const decision = decisionRaw;

  const outcome = await decideApprovalTask(
    context.accessToken,
    context.organization.organizationId,
    taskId,
    { decision, comment: comment === "" ? null : comment, idempotencyKey: randomUUID() },
  );

  if (outcome.kind === "ok") {
    // Server-confirmed state: görev kutusu ve talep sayfası tazelenir, kullanıcı
    // güncel durum + timeline'ı görmek için talep detayına yönlendirilir.
    revalidatePath("/tasks/inbox");
    revalidatePath(`/purchase-requests/${outcome.data.purchaseRequestId}`);
    redirect(`/purchase-requests/${outcome.data.purchaseRequestId}`);
  }

  switch (outcome.kind) {
    case "conflict":
      return { status: "error", message: outcome.message };
    case "not_found":
      return { status: "error", message: "Bu görev artık sizde değil veya bulunamadı." };
    case "gone":
      return { status: "error", message: "Bu görev artık geçerli değil. Sayfayı yenileyin." };
    case "validation_error":
      return { status: "error", message: outcome.message };
    case "unauthorized":
      return { status: "error", message: "Oturumunuz sona ermiş.", requiresLogin: true };
    case "forbidden":
      return { status: "error", message: "Bu işlem için yetkiniz yok." };
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
