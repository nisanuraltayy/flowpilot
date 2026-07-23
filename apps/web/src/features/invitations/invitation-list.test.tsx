/**
 * InvitationList testleri — durum rozeti + rol etiketi metinle; iptal butonu yalnız pending.
 * Ham token liste verisinde YOKTUR (tip zaten içermez; regresyon guard'ı olarak da kontrol edilir).
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RevokeInvitationResult } from "@/features/invitations/actions";
import { InvitationList } from "@/features/invitations/invitation-list";
import type { InvitationListItem } from "@/lib/api/resources";

const noopRevoke = async (): Promise<RevokeInvitationResult> => ({ status: "idle" });

function item(overrides: Partial<InvitationListItem> = {}): InvitationListItem {
  return {
    invitationId: "inv-1",
    invitedEmail: "davetli@sirket.com",
    role: "member",
    status: "pending",
    expiresAt: "2026-07-30T00:00:00Z",
    createdAt: "2026-07-23T00:00:00Z",
    ...overrides,
  };
}

describe("InvitationList", () => {
  it("davet satırını rol etiketi ve durum rozetiyle (metin) render eder", () => {
    render(<InvitationList items={[item()]} revokeAction={noopRevoke} />);

    expect(screen.getByText("davetli@sirket.com")).toBeInTheDocument();
    expect(screen.getByText("Üye")).toBeInTheDocument();
    expect(screen.getByText("Bekliyor")).toBeInTheDocument();
  });

  it("bekleyen davette iptal butonu gösterir", () => {
    render(<InvitationList items={[item({ status: "pending" })]} revokeAction={noopRevoke} />);
    expect(screen.getByRole("button", { name: "İptal et" })).toBeInTheDocument();
  });

  it("kabul edilmiş/iptal edilmiş davette iptal butonu göstermez", () => {
    render(
      <InvitationList
        items={[item({ invitationId: "a", status: "accepted" }), item({ invitationId: "b", status: "revoked" })]}
        revokeAction={noopRevoke}
      />,
    );
    expect(screen.queryByRole("button", { name: "İptal et" })).not.toBeInTheDocument();
    expect(screen.getByText("Kabul edildi")).toBeInTheDocument();
    expect(screen.getByText("İptal edildi")).toBeInTheDocument();
  });

  it("tablo başlıkları scope='col' ile erişilebilir", () => {
    render(<InvitationList items={[item()]} revokeAction={noopRevoke} />);
    const headers = screen.getAllByRole("columnheader");
    expect(headers.length).toBeGreaterThanOrEqual(5);
    for (const h of headers) {
      expect(h).toHaveAttribute("scope", "col");
    }
  });

  it("liste render'ında ham token benzeri veri sızmaz", () => {
    const { container } = render(<InvitationList items={[item()]} revokeAction={noopRevoke} />);
    expect(container.textContent).not.toMatch(/token/i);
  });
});
