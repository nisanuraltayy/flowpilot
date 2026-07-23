/**
 * CreateInvitationForm testleri — fake action; gerçek backend YOK.
 *
 * Güvenlik odak: davet URL'si (ham token içerir) YALNIZ başarı modalı AÇIKKEN görünür;
 * modal kapanınca DOM'dan kalkar. Rol seçiminde owner/Sahip YOKTUR.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CreateInvitationResult } from "@/features/invitations/actions";
import { CreateInvitationForm } from "@/features/invitations/create-invitation-form";

const INVITE_URL = "https://app.example.com/invitations/accept?org=1&token=raw-token-marker";

function succeeding(
  overrides: { duplicate?: boolean; inviteUrl?: string | null } = {},
): () => Promise<CreateInvitationResult> {
  return async () => ({
    status: "success",
    invitedEmail: "davetli@sirket.com",
    role: "admin",
    expiresAt: "2026-07-30T00:00:00Z",
    duplicate: false,
    inviteUrl: INVITE_URL,
    ...overrides,
  });
}

function failing(message: string, fieldErrors?: Record<string, string[]>): () => Promise<CreateInvitationResult> {
  return async () => ({ status: "error", message, fieldErrors });
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("E-posta"), "davetli@sirket.com");
  await user.click(screen.getByRole("button", { name: "Davet oluştur" }));
}

describe("CreateInvitationForm", () => {
  it("e-posta alanı ve rol seçimini (Üye/Yönetici) render eder; Sahip yok", () => {
    render(<CreateInvitationForm action={failing("x")} />);

    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
    const roleSelect = screen.getByLabelText("Rol");
    const options = within(roleSelect).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Üye", "Yönetici"]);
    expect(options).not.toContain("Sahip");
  });

  it("başarıda davet URL'sini modalda bir kez gösterir; kapanınca token DOM'dan kalkar", async () => {
    const user = userEvent.setup();
    const { container } = render(<CreateInvitationForm action={succeeding()} />);

    await submit(user);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(INVITE_URL)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Bağlantıyı kopyala" })).toBeInTheDocument();

    // Modalı kapat → token'lı URL artık DOM'da değil (× ve "Kapat" aynı erişilebilir ada sahip).
    await user.click(within(dialog).getAllByRole("button", { name: "Kapat" })[0]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(container.textContent).not.toContain("raw-token-marker");
  });

  it("idempotent replay (duplicate, url yok) güvenli bilgi mesajı gösterir, token göstermez", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <CreateInvitationForm action={succeeding({ duplicate: true, inviteUrl: null })} />,
    );

    await submit(user);

    expect(
      await screen.findByText(/zaten bekleyen bir davet var/i),
    ).toBeInTheDocument();
    expect(container.textContent).not.toContain("raw-token-marker");
  });

  it("alan hatasını server action'dan gösterir", async () => {
    const user = userEvent.setup();
    render(
      <CreateInvitationForm action={failing("Lütfen alanları kontrol edin.", { email: ["Geçerli bir e-posta girin."] })} />,
    );

    await submit(user);
    expect(await screen.findByText("Geçerli bir e-posta girin.")).toBeInTheDocument();
  });
});
