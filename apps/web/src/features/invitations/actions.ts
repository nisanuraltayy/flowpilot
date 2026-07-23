"use server";

/**
 * Davet yönetimi + kabul server action'ları.
 *
 * Güvenlik:
 * - Access token YALNIZ server tarafında okunur ve FastAPI'ye iletilir; browser/log'a taşınmaz.
 * - Idempotency-Key mantıksal işlem başına istemcide üretilir ve retry'da AYNI kalır (form'dan
 *   gelir); geçersiz/eksikse server tarafında güvenli biçimde üretilir. Key hassas değildir
 *   (rastgele UUID); localStorage/cookie/URL/log'a YAZILMAZ.
 * - Ham davet token'ı YALNIZ create sonucundaki davet URL'sinin içinde döner ve modal
 *   kapanınca istemci state'inden temizlenir; log/analytics/storage'a yazılmaz.
 * - Kabul URL'sinin domain kısmı env base URL convention'ından gelir (hardcode yok).
 * - Actor/tenant kullanıcı formundan alınmaz; kimlik doğrulanmış oturumdan gelir.
 */

import { randomUUID } from "node:crypto";

import { revalidatePath } from "next/cache";

import {
  getServerAccessToken,
  requireActiveOrganization,
  writeActiveOrganizationCookie,
} from "@/features/organizations/context";
import { createInvitationSchema } from "@/features/invitations/schemas";
import { getAppUrl } from "@/lib/env";
import {
  acceptInvitation,
  createInvitation,
  revokeInvitation,
} from "@/lib/api/resources";

const INVITATIONS_PATH = "/settings/team/invitations";
const SERVICE_MESSAGE =
  "Servise şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.";
const NETWORK_MESSAGE = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin.";
const UNEXPECTED_MESSAGE = "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.";

export type CreateInvitationResult =
  | { readonly status: "idle" }
  | {
      readonly status: "error";
      readonly message: string;
      readonly fieldErrors?: Readonly<Record<string, readonly string[]>>;
      readonly requiresLogin?: boolean;
    }
  | {
      readonly status: "success";
      readonly invitedEmail: string;
      readonly role: string;
      readonly expiresAt: string;
      readonly duplicate: boolean;
      /** Kabul URL'si YALNIZ ilk create'te (token mevcut); replay'de null. */
      readonly inviteUrl: string | null;
    };

export type RevokeInvitationResult =
  | { readonly status: "idle" }
  | { readonly status: "error"; readonly message: string; readonly requiresLogin?: boolean }
  | { readonly status: "success"; readonly duplicate: boolean };

export type AcceptInvitationResult =
  | { readonly status: "idle" }
  | { readonly status: "error"; readonly kind: AcceptErrorKind; readonly message: string }
  | {
      readonly status: "success";
      readonly organizationId: string;
      readonly role: string;
      readonly duplicate: boolean;
    };

export type AcceptErrorKind =
  | "requires_login"
  | "email_mismatch"
  | "not_found"
  | "expired"
  | "conflict"
  | "unavailable"
  | "unexpected";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * İstemcinin (mantıksal işlem başına üretip retry'da tekrar gönderdiği) Idempotency-Key'ini
 * form'dan alır. İstemci key'i, backend'in aynı retry'ı tek işlem olarak görmesini sağlar.
 * Eksik/biçimsiz ise (JS'siz istemci, kurcalanmış istek) güvenli fallback olarak server üretir
 * — böylece her istekte DAİMA geçerli bir key gider. Key hassas değildir; loglanmaz.
 */
function resolveIdempotencyKey(formData: FormData): string {
  const raw = formData.get("idempotencyKey");
  return typeof raw === "string" && UUID_RE.test(raw) ? raw : randomUUID();
}

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

/** Kabul sayfasına giden güvenli davet URL'si (domain env'den; token capability). */
function buildInviteUrl(organizationId: string, token: string): string {
  const query = new URLSearchParams({ org: organizationId, token });
  return `${getAppUrl()}/invitations/accept?${query.toString()}`;
}

export async function createInvitationAction(
  _previous: CreateInvitationResult,
  formData: FormData,
): Promise<CreateInvitationResult> {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return { status: "error", message: SERVICE_MESSAGE };
  }

  const parsed = createInvitationSchema.safeParse({
    email: formData.get("email"),
    role: formData.get("role"),
  });
  if (!parsed.success) {
    return {
      status: "error",
      message: "Lütfen alanları kontrol edin.",
      fieldErrors: fieldErrorsFromZod(parsed.error),
    };
  }

  const outcome = await createInvitation(
    context.accessToken,
    context.organization.organizationId,
    {
      email: parsed.data.email,
      role: parsed.data.role,
      idempotencyKey: resolveIdempotencyKey(formData),
    },
  );

  switch (outcome.kind) {
    case "ok":
      revalidatePath(INVITATIONS_PATH);
      return {
        status: "success",
        invitedEmail: outcome.data.invitedEmail,
        role: outcome.data.role,
        expiresAt: outcome.data.expiresAt,
        duplicate: outcome.data.duplicate,
        inviteUrl:
          outcome.data.token === null
            ? null
            : buildInviteUrl(context.organization.organizationId, outcome.data.token),
      };
    case "validation_error":
      return { status: "error", message: outcome.message, fieldErrors: { email: [outcome.message] } };
    case "conflict":
      return { status: "error", message: outcome.message };
    case "unauthorized":
      return { status: "error", message: "Oturumunuz sona ermiş.", requiresLogin: true };
    case "forbidden":
      return { status: "error", message: "Davet göndermek için yetkiniz yok." };
    case "not_found":
      return { status: "error", message: "Organizasyon bulunamadı." };
    case "gone":
      return { status: "error", message: UNEXPECTED_MESSAGE };
    case "service_unavailable":
      return { status: "error", message: SERVICE_MESSAGE };
    case "network_error":
      return { status: "error", message: NETWORK_MESSAGE };
    case "server_error":
      return { status: "error", message: UNEXPECTED_MESSAGE };
  }
}

export async function revokeInvitationAction(
  _previous: RevokeInvitationResult,
  formData: FormData,
): Promise<RevokeInvitationResult> {
  const context = await requireActiveOrganization();
  if (context.status === "unavailable") {
    return { status: "error", message: SERVICE_MESSAGE };
  }
  const invitationId = String(formData.get("invitationId") ?? "").trim();
  if (invitationId === "") {
    return { status: "error", message: "Geçersiz iptal isteği." };
  }

  const outcome = await revokeInvitation(
    context.accessToken,
    context.organization.organizationId,
    invitationId,
  );

  switch (outcome.kind) {
    case "ok":
      revalidatePath(INVITATIONS_PATH);
      return { status: "success", duplicate: outcome.data.duplicate };
    case "conflict":
      return { status: "error", message: outcome.message };
    case "unauthorized":
      return { status: "error", message: "Oturumunuz sona ermiş.", requiresLogin: true };
    case "forbidden":
      return { status: "error", message: "Bu işlem için yetkiniz yok." };
    case "not_found":
      return { status: "error", message: "Davet bulunamadı." };
    case "gone":
    case "validation_error":
    case "service_unavailable":
      return { status: "error", message: SERVICE_MESSAGE };
    case "network_error":
      return { status: "error", message: NETWORK_MESSAGE };
    case "server_error":
      return { status: "error", message: UNEXPECTED_MESSAGE };
  }
}

/**
 * Daveti kabul et. `organizationId` ve `token` server tarafında (şifreli bound argüman)
 * gelir — istemci DOM'una plaintext olarak konmaz. Başarıda aktif org cookie yenilenir.
 */
export async function acceptInvitationAction(
  organizationId: string,
  token: string,
  // useActionState imzası gereği alınır ama kullanılmaz (underscore → lint ignore).
  _previous: AcceptInvitationResult,
  formData: FormData,
): Promise<AcceptInvitationResult> {
  const accessToken = await getServerAccessToken();
  if (accessToken === null) {
    return {
      status: "error",
      kind: "requires_login",
      message: "Daveti kabul etmek için giriş yapın.",
    };
  }

  const outcome = await acceptInvitation(accessToken, {
    organizationId,
    token,
    idempotencyKey: resolveIdempotencyKey(formData),
  });

  switch (outcome.kind) {
    case "ok":
      // Yeni üye kabul sonrası katıldığı org'a düşsün diye aktif org context'i yenilenir.
      await writeActiveOrganizationCookie(outcome.data.organizationId);
      return {
        status: "success",
        organizationId: outcome.data.organizationId,
        role: outcome.data.role,
        duplicate: outcome.data.duplicate,
      };
    case "unauthorized":
      return {
        status: "error",
        kind: "requires_login",
        message: "Oturumunuz sona ermiş. Lütfen yeniden giriş yapın.",
      };
    case "forbidden":
      return {
        status: "error",
        kind: "email_mismatch",
        message: "Bu davet farklı bir e-posta adresi için oluşturulmuş.",
      };
    case "not_found":
      return {
        status: "error",
        kind: "not_found",
        message: "Bu davet geçerli değil veya bulunamadı.",
      };
    case "gone":
      return { status: "error", kind: "expired", message: "Davetin süresi dolmuş." };
    case "conflict":
      return {
        status: "error",
        kind: "conflict",
        message: "Bu davet şu anda kabul edilemiyor (çakışma). Lütfen tekrar deneyin.",
      };
    case "validation_error":
      return { status: "error", kind: "not_found", message: "Davet bağlantısı geçersiz." };
    case "service_unavailable":
      return { status: "error", kind: "unavailable", message: SERVICE_MESSAGE };
    case "network_error":
      return { status: "error", kind: "unavailable", message: NETWORK_MESSAGE };
    case "server_error":
      return { status: "error", kind: "unexpected", message: UNEXPECTED_MESSAGE };
  }
}
