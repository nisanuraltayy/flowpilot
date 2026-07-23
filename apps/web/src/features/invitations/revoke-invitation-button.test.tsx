/** RevokeInvitationButton testleri — onay diyaloğu; fake action. */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { RevokeInvitationResult } from "@/features/invitations/actions";
import { RevokeInvitationButton } from "@/features/invitations/revoke-invitation-button";

const noop = async (): Promise<RevokeInvitationResult> => ({ status: "idle" });

function renderButton(action: () => Promise<RevokeInvitationResult> = noop) {
  return render(
    <RevokeInvitationButton invitationId="inv-1" invitedEmail="davetli@sirket.com" action={action} />,
  );
}

describe("RevokeInvitationButton", () => {
  it("tıklanınca onay diyaloğu açar; davetliyi ve uyarıyı gösterir", async () => {
    const user = userEvent.setup();
    renderButton();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "İptal et" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("davetli@sirket.com")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Evet, iptal et" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Vazgeç" })).toBeInTheDocument();
  });

  it("Vazgeç diyaloğu kapatır (iptal işlemi yapılmadan)", async () => {
    const user = userEvent.setup();
    renderButton();

    await user.click(screen.getByRole("button", { name: "İptal et" }));
    await user.click(await screen.findByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("hata sonucunu diyalog içinde erişilebilir alert olarak gösterir", async () => {
    const user = userEvent.setup();
    renderButton(async () => ({ status: "error", message: "Davet bulunamadı." }));

    await user.click(screen.getByRole("button", { name: "İptal et" }));
    await user.click(await screen.findByRole("button", { name: "Evet, iptal et" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Davet bulunamadı.");
  });
});
