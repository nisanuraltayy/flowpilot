"use server";

/**
 * Onay rolü atama server action'ı.
 *
 * Güvenlik:
 * - Access token YALNIZ server tarafında okunur; browser/log'a taşınmaz.
 * - Actor/tenant kullanıcı formundan alınmaz; doğrulanmış oturum + aktif org context'ten gelir.
 * - Atama optimistic concurrency (expected_version) ile yapılır; stale çakışma otomatik retry
 *   EDİLMEZ — liste yenilenir, kullanıcı güncel durumu görüp kararı tekrar verir.
 * - Backend 409/422 ham detay'ı KULLANICIYA GÖSTERİLMEZ; güvenli sınıflandırılmış mesajlara
 *   eşlenir. Mevcut açık workflow görevleri DEĞİŞMEZ (backend pinning); yalnız yeni görevler
 *   yeni atamayı kullanır.
 */

import { revalidatePath } from "next/cache";

import { APPROVAL_ROLE_KEYS } from "@/features/approval-roles/display";
import {
  classifyApprovalRoleConflict,
  GENERIC_CONFLICT_MESSAGE,
} from "@/features/approval-roles/conflict";
import { requireActiveOrganization } from "@/features/organizations/context";
import { assignApprovalRole } from "@/lib/api/resources";

const APPROVAL_ROLES_PATH = "/settings/team/approval-roles";

const SERVICE_MESSAGE =
  "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.";
const NETWORK_MESSAGE = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.";
const UNEXPECTED_MESSAGE = "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.";
const FORBIDDEN_MESSAGE = "Bu onay rolünü yönetme yetkiniz bulunmuyor.";
const MEMBER_UNAVAILABLE_MESSAGE = "Seçilen kullanıcı bu organizasyonda kullanılamıyor.";
const SESSION_MESSAGE = "Oturumunuz sona ermiş.";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ROLE_KEYS = new Set<string>(APPROVAL_ROLE_KEYS);

export type ApprovalRoleErrorKind =
  | "validation"
  | "forbidden"
  | "member_unavailable"
  | "stale"
  | "invalid_member_status"
  | "invalid_role"
  | "conflict"
  | "unavailable"
  | "unexpected";

export type ApprovalRoleMutationResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly kind: ApprovalRoleErrorKind;
      readonly message: string;
      readonly requiresLogin?: boolean;
    }
  | {
      readonly status: "success";
      readonly roleKey: string;
      readonly assignedUserEmail: string | null;
      readonly version: number;
      readonly duplicate: boolean;
    };

interface ParsedAssign {
  readonly roleKey: string;
  readonly userId: string;
  readonly expectedVersion?: number;
}

function parseAssign(formData: FormData): ParsedAssign | null {
  const roleKey = String(formData.get("roleKey") ?? "");
  const userId = String(formData.get("userId") ?? "");
  if (!ROLE_KEYS.has(roleKey) || !UUID_RE.test(userId)) {
    return null;
  }
  const rawVersion = formData.get("expectedVersion");
  if (typeof rawVersion === "string" && rawVersion !== "") {
    const expectedVersion = Number.parseInt(rawVersion, 10);
    if (!Number.isInteger(expectedVersion) || expectedVersion < 0) {
      return null;
    }
    return { roleKey, userId, expectedVersion };
  }
  return { roleKey, userId };
}

export async function assignApprovalRoleAction(
  _previous: ApprovalRoleMutationResult,
  formData: FormData,
): Promise<ApprovalRoleMutationResult> {
  const parsed = parseAssign(formData);
  if (parsed === null) {
    return { status: "error", kind: "validation", message: UNEXPECTED_MESSAGE };
  }

  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return { status: "error", kind: "unavailable", message: SERVICE_MESSAGE };
  }

  const outcome = await assignApprovalRole(
    context.accessToken,
    context.organization.organizationId,
    parsed.roleKey,
    { userId: parsed.userId, expectedVersion: parsed.expectedVersion },
  );

  switch (outcome.kind) {
    case "ok":
      revalidatePath(APPROVAL_ROLES_PATH);
      return {
        status: "success",
        roleKey: outcome.data.roleKey,
        assignedUserEmail: outcome.data.assignedUserEmail,
        version: outcome.data.version,
        duplicate: outcome.data.duplicate,
      };
    case "conflict":
    case "validation_error": {
      // 409 ve 422 (geçersiz role_key / expected_version gerekli) aynı sınıflandırıcıdan geçer.
      const { kind, message } = classifyApprovalRoleConflict(outcome.message);
      if (kind === "stale") {
        revalidatePath(APPROVAL_ROLES_PATH);
      }
      return { status: "error", kind, message };
    }
    case "forbidden":
      return { status: "error", kind: "forbidden", message: FORBIDDEN_MESSAGE };
    case "not_found":
      return { status: "error", kind: "member_unavailable", message: MEMBER_UNAVAILABLE_MESSAGE };
    case "unauthorized":
      return { status: "error", kind: "unexpected", message: SESSION_MESSAGE, requiresLogin: true };
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
