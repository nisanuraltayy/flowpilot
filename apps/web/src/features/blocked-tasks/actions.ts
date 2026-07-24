"use server";

/**
 * Engellenen onay görevi çözümleme server action'ı.
 *
 * Güvenlik / sözleşme:
 * - Access token YALNIZ server tarafında okunur; browser/log'a taşınmaz.
 * - Actor/tenant kullanıcı formundan alınmaz; doğrulanmış oturum + aktif org context'ten gelir.
 * - Resolve request KULLANICI SEÇİMİ / version / idempotency ALMAZ — backend adayı mevcut aktif
 *   rol atamasından kendisi seçer (keyfi user_id kabul etmez). Yalnız task_id gönderilir.
 * - Backend 409 ham detay'ı KULLANICIYA GÖSTERİLMEZ; güvenli sınıflandırılmış mesajlara eşlenir.
 *   Herhangi bir çakışmada liste yeniden fetch edilir (state değişmiştir); otomatik retry YOK.
 */

import { revalidatePath } from "next/cache";

import {
  classifyBlockedTaskConflict,
  GENERIC_CONFLICT_MESSAGE,
} from "@/features/blocked-tasks/conflict";
import { requireActiveOrganization } from "@/features/organizations/context";
import { resolveBlockedApprovalTaskAssignment } from "@/lib/api/resources";

const BLOCKED_TASKS_PATH = "/settings/team/blocked-approval-tasks";

const SERVICE_MESSAGE =
  "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.";
const NETWORK_MESSAGE = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.";
const UNEXPECTED_MESSAGE = "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.";
const FORBIDDEN_MESSAGE = "Bu onay görevinin atamasını çözme yetkiniz bulunmuyor.";
const NOT_FOUND_MESSAGE = "Bu onay görevi bulunamadı. Liste yenilendi.";
const SESSION_MESSAGE = "Oturumunuz sona ermiş.";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type BlockedTaskErrorKind =
  | "validation"
  | "forbidden"
  | "not_found"
  | "not_blocked"
  | "no_assignment"
  | "candidate_inactive"
  | "conflict"
  | "unavailable"
  | "unexpected";

export type BlockedTaskResolveResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly kind: BlockedTaskErrorKind;
      readonly message: string;
      readonly requiresLogin?: boolean;
    }
  | {
      readonly status: "success";
      readonly approverRole: string;
      readonly taskStatus: string;
      readonly version: number;
    };

export async function resolveBlockedTaskAction(
  _previous: BlockedTaskResolveResult,
  formData: FormData,
): Promise<BlockedTaskResolveResult> {
  const taskId = String(formData.get("taskId") ?? "");
  if (!UUID_RE.test(taskId)) {
    return { status: "error", kind: "validation", message: UNEXPECTED_MESSAGE };
  }

  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return { status: "error", kind: "unavailable", message: SERVICE_MESSAGE };
  }

  const outcome = await resolveBlockedApprovalTaskAssignment(
    context.accessToken,
    context.organization.organizationId,
    taskId,
  );

  switch (outcome.kind) {
    case "ok":
      revalidatePath(BLOCKED_TASKS_PATH);
      return {
        status: "success",
        approverRole: outcome.data.approverRole,
        taskStatus: outcome.data.status,
        version: outcome.data.version,
      };
    case "conflict": {
      // Her çözümleme çakışmasında liste değişmiştir → yeniden fetch (otomatik retry YOK).
      revalidatePath(BLOCKED_TASKS_PATH);
      const { kind, message } = classifyBlockedTaskConflict(outcome.message);
      return { status: "error", kind, message };
    }
    case "not_found":
      revalidatePath(BLOCKED_TASKS_PATH);
      return { status: "error", kind: "not_found", message: NOT_FOUND_MESSAGE };
    case "forbidden":
      return { status: "error", kind: "forbidden", message: FORBIDDEN_MESSAGE };
    case "unauthorized":
      return { status: "error", kind: "unexpected", message: SESSION_MESSAGE, requiresLogin: true };
    case "validation_error":
      return { status: "error", kind: "validation", message: UNEXPECTED_MESSAGE };
    case "gone":
      return { status: "error", kind: "conflict", message: GENERIC_CONFLICT_MESSAGE };
    case "service_unavailable":
      return { status: "error", kind: "unavailable", message: SERVICE_MESSAGE };
    case "network_error":
      return { status: "error", kind: "unavailable", message: NETWORK_MESSAGE };
    case "server_error":
      return { status: "error", kind: "unexpected", message: UNEXPECTED_MESSAGE };
  }
}
