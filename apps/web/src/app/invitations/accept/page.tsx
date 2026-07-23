import type { Metadata } from "next";

import { FlowPilotLogo } from "@/components/flowpilot-logo";
import { acceptInvitationAction } from "@/features/invitations/actions";
import {
  InvitationAcceptView,
  type AcceptPreviewError,
  type SafeInvitationPreview,
} from "@/features/invitations/invitation-accept-view";
import { getServerAccessToken } from "@/features/organizations/context";
import { previewInvitation } from "@/lib/api/resources";

export const metadata: Metadata = { title: "Daveti kabul et" };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface AcceptPageProps {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}

function firstParam(value: string | string[] | undefined): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return null;
}

export default async function AcceptInvitationPage({ searchParams }: AcceptPageProps) {
  const params = await searchParams;
  const org = firstParam(params.org);
  const token = firstParam(params.token);

  let preview: SafeInvitationPreview | null = null;
  let previewError: AcceptPreviewError | null = null;

  if (org === null || token === null || org === "" || token === "" || !UUID_RE.test(org)) {
    // org/token yok veya bozuk (ör. başarılı kabul sonrası temizlenmiş URL) → güvenli geçersiz.
    previewError = "invalid";
  } else {
    const outcome = await previewInvitation(org, token);
    switch (outcome.kind) {
      case "ok":
        preview = {
          organizationName: outcome.data.organizationName,
          role: outcome.data.role,
          expiresAt: outcome.data.expiresAt,
          status: outcome.data.status,
        };
        break;
      case "gone":
        previewError = "expired";
        break;
      case "not_found":
      case "validation_error":
        previewError = "not_found";
        break;
      default:
        previewError = "unavailable";
    }
  }

  const isAuthenticated = (await getServerAccessToken()) !== null;

  // Giriş sonrası aynı davet sayfasına dönüş (yalnız relative path; token URL'de kalır).
  const returnTo =
    org !== null && token !== null
      ? `/invitations/accept?${new URLSearchParams({ org, token }).toString()}`
      : "/invitations/accept";
  const loginHref = `/login?next=${encodeURIComponent(returnTo)}`;

  // org/token server tarafında (şifreli bound argüman) taşınır — istemci DOM'una konmaz.
  const boundAccept = acceptInvitationAction.bind(null, org ?? "", token ?? "");

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-canvas px-4 py-10">
      <FlowPilotLogo />
      <InvitationAcceptView
        preview={preview}
        previewError={previewError}
        isAuthenticated={isAuthenticated}
        loginHref={loginHref}
        dashboardHref="/dashboard"
        action={boundAccept}
      />
    </main>
  );
}
