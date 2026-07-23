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

describe("InvitationAcceptView — Idempotency-Key yaşam döngüsü", () => {
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

  function seqGen(): () => string {
    let n = 0;
    return () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`;
  }

  function recording(next: () => AcceptInvitationResult) {
    const keys: (string | null)[] = [];
    const action = async (
      _previous: AcceptInvitationResult,
      formData: FormData,
    ): Promise<AcceptInvitationResult> => {
      const raw = formData.get("idempotencyKey");
      keys.push(typeof raw === "string" && raw !== "" ? raw : null);
      return next();
    };
    return { action, keys };
  }

  const unavailable = (): AcceptInvitationResult => ({
    status: "error",
    kind: "unavailable",
    message: "geçici",
  });

  afterEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it("ilk kabul bir UUID key üretir", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(unavailable);
    render(base({ action, generateIdempotencyKey: seqGen() }));

    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));

    expect(keys).toHaveLength(1);
    expect(keys[0]).toMatch(UUID_RE);
  });

  it("network/retry AYNI key'i kullanır (gizli alan sıfırlansa da)", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(unavailable);
    render(base({ action, generateIdempotencyKey: seqGen() }));

    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));

    expect(keys).toHaveLength(2);
    expect(keys[1]).toBe(keys[0]);
  });

  it("farklı davet (yeni mount) yeni key kullanır", async () => {
    const user = userEvent.setup();
    const gen = seqGen();
    const a = recording(unavailable);
    const first = render(base({ action: a.action, generateIdempotencyKey: gen }));
    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));
    first.unmount();

    const b = recording(unavailable);
    render(base({ action: b.action, generateIdempotencyKey: gen }));
    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));

    expect(a.keys[0]).toMatch(UUID_RE);
    expect(b.keys[0]).not.toBe(a.keys[0]);
  });

  it("key browser storage'a yazılmaz", async () => {
    const user = userEvent.setup();
    const { action, keys } = recording(unavailable);
    render(base({ action, generateIdempotencyKey: seqGen() }));

    await user.click(screen.getByRole("button", { name: "Daveti kabul et" }));

    const key = keys[0] ?? "";
    expect(key).toMatch(UUID_RE);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).not.toContain(key);
  });
});
