"use server";

/**
 * Üye yönetimi server action'ları (rol değiştirme + durum değiştirme).
 *
 * Güvenlik:
 * - Access token YALNIZ server tarafında okunur; browser/log'a taşınmaz.
 * - Actor/tenant kullanıcı formundan alınmaz; doğrulanmış oturum + aktif org context'ten gelir.
 * - Mutasyon optimistic concurrency (expected_version) ile yapılır; stale çakışma otomatik
 *   retry EDİLMEZ — liste yenilenir, kullanıcı yeni durumu görüp kararı tekrar verir.
 * - Backend 409 ham detay'ı KULLANICIYA GÖSTERİLMEZ; güvenli, sınıflandırılmış mesajlara
 *   eşlenir (self / son-owner / onay-sorumluluğu / removed / geçersiz-geçiş / stale / genel).
 */

import { revalidatePath } from "next/cache";

import {
  classifyMemberConflict,
  GENERIC_CONFLICT_MESSAGE,
} from "@/features/members/conflict";
import { requireActiveOrganization } from "@/features/organizations/context";
import { updateOrganizationMember } from "@/lib/api/resources";

const MEMBERS_PATH = "/settings/team/members";

const SERVICE_MESSAGE =
  "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.";
const NETWORK_MESSAGE = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.";
const UNEXPECTED_MESSAGE = "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.";
const VALIDATION_MESSAGE = "Bu işlem uygulanamadı. Lütfen seçiminizi kontrol edin.";
const FORBIDDEN_MESSAGE = "Bu işlem için yetkiniz yok.";
const NOT_FOUND_MESSAGE = "Üye bulunamadı.";
const SESSION_MESSAGE = "Oturumunuz sona ermiş.";

const ROLES = new Set(["owner", "admin", "member"]);
const STATUSES = new Set(["active", "suspended", "removed"]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type MemberErrorKind =
  | "validation"
  | "forbidden"
  | "not_found"
  | "self"
  | "final_owner"
  | "approval_responsibility"
  | "removed"
  | "invalid_transition"
  | "stale"
  | "conflict"
  | "unavailable"
  | "unexpected";

export type MemberMutationResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly kind: MemberErrorKind;
      readonly message: string;
      readonly requiresLogin?: boolean;
    }
  | {
      readonly status: "success";
      readonly role: string;
      readonly memberStatus: string;
      readonly version: number;
      readonly duplicate: boolean;
    };

interface ParsedPatch {
  readonly targetUserId: string;
  readonly expectedVersion: number;
  readonly role?: string;
  readonly status?: string;
}

function parsePatch(formData: FormData): ParsedPatch | null {
  const targetUserId = String(formData.get("targetUserId") ?? "");
  const expectedRaw = String(formData.get("expectedVersion") ?? "");
  const expectedVersion = Number.parseInt(expectedRaw, 10);
  if (!UUID_RE.test(targetUserId) || !Number.isInteger(expectedVersion) || expectedVersion < 0) {
    return null;
  }
  const roleRaw = formData.get("role");
  const statusRaw = formData.get("status");
  const role = typeof roleRaw === "string" && roleRaw !== "" ? roleRaw : undefined;
  const status = typeof statusRaw === "string" && statusRaw !== "" ? statusRaw : undefined;
  if (role === undefined && status === undefined) {
    return null;
  }
  if (role !== undefined && !ROLES.has(role)) {
    return null;
  }
  if (status !== undefined && !STATUSES.has(status)) {
    return null;
  }
  return { targetUserId, expectedVersion, role, status };
}

async function runPatch(formData: FormData): Promise<MemberMutationResult> {
  const parsed = parsePatch(formData);
  if (parsed === null) {
    return { status: "error", kind: "validation", message: VALIDATION_MESSAGE };
  }

  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return { status: "error", kind: "unavailable", message: SERVICE_MESSAGE };
  }

  const outcome = await updateOrganizationMember(
    context.accessToken,
    context.organization.organizationId,
    parsed.targetUserId,
    { role: parsed.role, status: parsed.status, expectedVersion: parsed.expectedVersion },
  );

  switch (outcome.kind) {
    case "ok":
      revalidatePath(MEMBERS_PATH);
      return {
        status: "success",
        role: outcome.data.role,
        memberStatus: outcome.data.status,
        version: outcome.data.version,
        duplicate: outcome.data.duplicate,
      };
    case "conflict": {
      const { kind, message } = classifyMemberConflict(outcome.message);
      // Stale çakışmada listeyi yenile ki kullanıcı güncel version'ı görsün (otomatik retry YOK).
      if (kind === "stale") {
        revalidatePath(MEMBERS_PATH);
      }
      return { status: "error", kind, message };
    }
    case "validation_error":
      return { status: "error", kind: "validation", message: VALIDATION_MESSAGE };
    case "forbidden":
      return { status: "error", kind: "forbidden", message: FORBIDDEN_MESSAGE };
    case "not_found":
      return { status: "error", kind: "not_found", message: NOT_FOUND_MESSAGE };
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

/** Üye rolünü değiştir (formData: targetUserId, role, expectedVersion). */
export async function changeMemberRoleAction(
  _previous: MemberMutationResult,
  formData: FormData,
): Promise<MemberMutationResult> {
  return runPatch(formData);
}

/** Üye durumunu değiştir — suspend/reactivate/remove (formData: targetUserId, status, expectedVersion). */
export async function setMemberStatusAction(
  _previous: MemberMutationResult,
  formData: FormData,
): Promise<MemberMutationResult> {
  return runPatch(formData);
}
