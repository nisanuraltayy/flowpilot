/**
 * InvitationAcceptView testleri — public kabul ekranı; fake action, gerçek backend YOK.
 *
 * Kapsam: pending (authenticated/unauthenticated), accepted, preview hataları
 * (expired/not_found), başarılı kabul + URL temizliği, e-posta uyuşmazlığı mesajı.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AcceptInvitationResult } from "@/features/invitations/actions";
import {
  InvitationAcceptView,
  type SafeInvitationPreview,
} from "@/features/invitations/invitation-accept-view";

const PENDING: SafeInvitationPreview = {
  organizationName: "Acme Ltd",
  role: "member",
  expiresAt: "2026-07-30T00:00:00Z",
  status: "pending",
};

const idleAction = async (): Promise<AcceptInvitationResult> => ({ status: "idle" });

function base(overrides: Partial<Parameters<typeof InvitationAcceptView>[0]> = {}) {
  return (
    <InvitationAcceptView
      preview={PENDING}
      previewError={null}
      isAuthenticated={true}
      loginHref="/login?next=%2Finvitations%2Faccept"
      dashboardHref="/dashboard"
      action={idleAction}
      {...overrides}
    />
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("InvitationAcceptView", () => {
  it("pending + authenticated: org/rol gösterir ve kabul formu sunar", () => {
    render(base());
    expect(screen.getByText("Acme Ltd")).toBeInTheDocument();
    expect(screen.getByText("Üye")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Daveti kabul et" })).toBeInTheDocument();
  });

  it("pending + unauthenticated: kabul yerine giriş bağlantısı sunar", () => {
    render(base({ isAuthenticated: false }));
    const login = screen.getByRole("link", { name: "Giriş yapıp kabul et" });
    expect(login).toHaveAttribute("href", "/login?next=%2Finvitations%2Faccept");
    expect(screen.queryByRole("button", { name: "Daveti kabul et" })).not.toBeInTheDocument();
  });

  it("accepted önizleme: zaten kabul edilmiş bilgisini ve org bağlantısını gösterir", () => {
    render(base({ preview: { ...PENDING, status: "accepted" } }));
    expect(screen.getByText("Davet zaten kabul edilmiş")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Organizasyona git" })).toBeInTheDocument();
  });

  it("expired preview hatası: süre doldu mesajı; kabul aksiyonu yok", () => {
    render(base({ preview: null, previewError: "expired" }));
    expect(screen.getByText(/süresi dolmuş/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Daveti kabul et" })).not.toBeInTheDocument();
  });

  it("not_found preview hatası: geçersiz davet mesajı (bilgi sızdırmaz)", () => {
    const { container } = render(base({ preview: null, previewError: "not_found" }));
    expect(screen.getByText(/geçerli değil veya bulunamadı/i)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/token/i);
  });

  it("başarılı kabulde katılım mesajı gösterir ve URL'den token'ı temizler", async () => {
    const user = userEvent.setup();
    const replaceState = vi.spyOn(window.history, "replaceState");
    const action = async (): Promise<AcceptInvitationResult> => ({
      status: "success",
      organizationId: "org-1",
      role: "member",
      duplicate: false,
    });
    render(base({ action }));

    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));

    expect(await screen.findByText("Organizasyona katıldınız")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Panele git" })).toBeInTheDocument();
    expect(replaceState).toHaveBeenCalledWith(null, "", "/invitations/accept");
  });

  it("e-posta uyuşmazlığında gerçek e-postayı ifşa etmeyen güvenli mesaj gösterir", async () => {
    const user = userEvent.setup();
    const action = async (): Promise<AcceptInvitationResult> => ({
      status: "error",
      kind: "email_mismatch",
      message: "Bu davet farklı bir e-posta adresi için oluşturulmuş.",
    });
    render(base({ action }));

    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Bu davet farklı bir e-posta adresi için oluşturulmuş.");
  });
});
