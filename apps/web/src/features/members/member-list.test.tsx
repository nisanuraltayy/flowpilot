/**
 * MemberList testleri — fake action; gerçek backend YOK. Filtre/arama, self göstergesi,
 * null email, removed durum, owner aksiyon görünürlüğü.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MemberMutationResult } from "@/features/members/actions";
import { MemberList } from "@/features/members/member-list";
import type { MemberListItem } from "@/lib/api/resources";

const noop = async (): Promise<MemberMutationResult> => ({ status: "idle" });

function member(o: Partial<MemberListItem> = {}): MemberListItem {
  return {
    membershipId: `mem-${o.userId ?? "1"}`,
    userId: o.userId ?? "11111111-1111-4111-8111-111111111111",
    email: "email" in o ? (o.email as string | null) : "user@x.com",
    role: o.role ?? "member",
    status: o.status ?? "active",
    version: o.version ?? 1,
    createdAt: o.createdAt ?? "2026-07-01T00:00:00Z",
    updatedAt: o.updatedAt ?? "2026-07-10T00:00:00Z",
  };
}

const OWNER = member({ userId: "aaaaaaaa-1111-4111-8111-111111111111", email: "owner@x.com", role: "owner" });
const ADMIN = member({ userId: "bbbbbbbb-2222-4222-8222-222222222222", email: "admin@x.com", role: "admin" });
const MEMBER = member({ userId: "cccccccc-3333-4333-8333-333333333333", email: "worker@x.com", role: "member" });
const NULL_EMAIL = member({ userId: "dddddddd-4444-4444-8444-444444444444", email: null, role: "member" });
const REMOVED = member({ userId: "eeeeeeee-5555-4555-8555-555555555555", email: "gone@x.com", role: "member", status: "removed" });

function renderList(actorEmail = "owner@x.com", actorRole = "owner") {
  return render(
    <MemberList
      members={[OWNER, ADMIN, MEMBER, NULL_EMAIL, REMOVED]}
      actorRole={actorRole}
      actorEmail={actorEmail}
      roleAction={noop}
      statusAction={noop}
    />,
  );
}

describe("MemberList", () => {
  it("üyeleri e-posta/rol/durum ile listeler; null email güvenli gösterilir; sayaç doğru", () => {
    renderList();
    expect(screen.getByText("owner@x.com")).toBeInTheDocument();
    expect(screen.getByText("worker@x.com")).toBeInTheDocument();
    expect(screen.getByText("E-posta bilgisi yok")).toBeInTheDocument();
    // "Sahip" hem owner satırında hem filtre option'unda geçer → satır içinde doğrula.
    const ownerRow = screen.getByText("owner@x.com").closest("tr") as HTMLElement;
    expect(within(ownerRow).getByText("Sahip")).toBeInTheDocument();
    expect(screen.getAllByText("Kaldırıldı").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("5 üye")).toBeInTheDocument();
  });

  it("self satırında 'Siz' göstergesi ve aksiyon yok (Kendi hesabınız)", () => {
    renderList("owner@x.com", "owner");
    expect(screen.getByText("Siz")).toBeInTheDocument();
    // Owner kendi satırında aksiyon görmez.
    const ownerRow = screen.getByText("owner@x.com").closest("tr") as HTMLElement;
    expect(within(ownerRow).getByText("Kendi hesabınız")).toBeInTheDocument();
    expect(within(ownerRow).queryByRole("button")).not.toBeInTheDocument();
  });

  it("owner aktif member satırında rol/askı/kaldır aksiyonlarını gösterir", () => {
    renderList();
    const row = screen.getByText("worker@x.com").closest("tr") as HTMLElement;
    expect(within(row).getByRole("button", { name: "Rol değiştir" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Askıya al" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Üyeliği kaldır" })).toBeInTheDocument();
  });

  it("removed satırda aksiyon yok (terminal)", () => {
    renderList();
    const row = screen.getByText("gone@x.com").closest("tr") as HTMLElement;
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
    // Hem durum rozeti hem aksiyon notu "Kaldırıldı" gösterir.
    expect(within(row).getAllByText("Kaldırıldı").length).toBeGreaterThanOrEqual(1);
  });

  it("rol filtresi listeyi daraltır", async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(screen.getByLabelText("Role göre filtrele"), "admin");
    expect(screen.getByText("admin@x.com")).toBeInTheDocument();
    expect(screen.queryByText("worker@x.com")).not.toBeInTheDocument();
    expect(screen.getByText("1 / 5 üye")).toBeInTheDocument();
  });

  it("durum filtresi removed üyeleri gösterebilir", async () => {
    const user = userEvent.setup();
    renderList();
    await user.selectOptions(screen.getByLabelText("Duruma göre filtrele"), "removed");
    expect(screen.getByText("gone@x.com")).toBeInTheDocument();
    expect(screen.queryByText("owner@x.com")).not.toBeInTheDocument();
  });

  it("arama e-postaya göre filtreler; eşleşme yoksa boş durum", async () => {
    const user = userEvent.setup();
    renderList();
    await user.type(screen.getByLabelText("E-posta ara"), "worker");
    expect(screen.getByText("worker@x.com")).toBeInTheDocument();
    expect(screen.queryByText("owner@x.com")).not.toBeInTheDocument();

    await user.clear(screen.getByLabelText("E-posta ara"));
    await user.type(screen.getByLabelText("E-posta ara"), "yokboyle");
    expect(screen.getByText("Filtreye uygun üye yok")).toBeInTheDocument();
  });

  it("admin actor owner/admin satırlarında aksiyon göstermez, member satırında gösterir", () => {
    render(
      <MemberList
        members={[OWNER, ADMIN, MEMBER]}
        actorRole="admin"
        actorEmail="admin@x.com"
        roleAction={noop}
        statusAction={noop}
      />,
    );
    const ownerRow = screen.getByText("owner@x.com").closest("tr") as HTMLElement;
    expect(within(ownerRow).queryByRole("button")).not.toBeInTheDocument();
    const memberRow = screen.getByText("worker@x.com").closest("tr") as HTMLElement;
    expect(within(memberRow).getByRole("button", { name: "Rol değiştir" })).toBeInTheDocument();
  });
});
