/**
 * ApprovalRoleList testleri — 3 sabit rol kartı; atanmış/atanmamış; null email; aday yokluğu.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ApprovalRoleMutationResult } from "@/features/approval-roles/actions";
import { ApprovalRoleList } from "@/features/approval-roles/approval-role-list";
import type { ApprovalRoleAssignment, MemberListItem } from "@/lib/api/resources";

const noop = async (): Promise<ApprovalRoleMutationResult> => ({ status: "idle" });

function assignment(o: Partial<ApprovalRoleAssignment>): ApprovalRoleAssignment {
  return {
    assignmentId: `asg-${o.roleKey}`,
    roleKey: o.roleKey ?? "team_manager",
    assignedUserId: o.assignedUserId ?? "u1",
    assignedUserEmail: "assignedUserEmail" in o ? (o.assignedUserEmail as string | null) : "a@b.com",
    status: "active",
    version: o.version ?? 1,
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  };
}

function activeMember(userId: string, email: string | null): MemberListItem {
  return {
    membershipId: `mem-${userId}`,
    userId,
    email,
    role: "member",
    status: "active",
    version: 1,
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  };
}

describe("ApprovalRoleList", () => {
  it("3 sabit rolü ad + açıklama ile listeler", () => {
    render(<ApprovalRoleList assignments={[]} members={[activeMember("u1", "a@b.com")]} actorEmail={null} action={noop} />);
    expect(screen.getByRole("heading", { name: "Takım Yöneticisi" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Finans Sorumlusu" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Genel Müdür" })).toBeInTheDocument();
    expect(screen.getByText(/ilk onayı verir/i)).toBeInTheDocument();
  });

  it("atanmış rol assignee e-postasını, atanmamış rol 'atanmadı' gösterir", () => {
    render(
      <ApprovalRoleList
        assignments={[assignment({ roleKey: "team_manager", assignedUserEmail: "manager@x.com" })]}
        members={[activeMember("u1", "manager@x.com")]}
        actorEmail={null}
        action={noop}
      />,
    );
    expect(screen.getByText("manager@x.com")).toBeInTheDocument();
    // finance ve general_manager atanmamış → en az 2 "atanmadı"
    expect(screen.getAllByText("Henüz kullanıcı atanmadı.").length).toBe(2);
  });

  it("null email assignee güvenli yer tutucu gösterir", () => {
    render(
      <ApprovalRoleList
        assignments={[assignment({ roleKey: "finance", assignedUserEmail: null })]}
        members={[activeMember("u1", "x@x.com")]}
        actorEmail={null}
        action={noop}
      />,
    );
    expect(screen.getByText("E-posta bilgisi yok")).toBeInTheDocument();
  });

  it("atanmış rolde 'Değiştir', atanmamış rolde 'Ata' butonu", () => {
    render(
      <ApprovalRoleList
        assignments={[assignment({ roleKey: "team_manager", assignedUserEmail: "m@x.com" })]}
        members={[activeMember("u1", "m@x.com")]}
        actorEmail={null}
        action={noop}
      />,
    );
    const tm = screen.getByRole("heading", { name: "Takım Yöneticisi" }).closest("li") as HTMLElement;
    expect(within(tm).getByRole("button", { name: "Değiştir" })).toBeInTheDocument();
    const fin = screen.getByRole("heading", { name: "Finans Sorumlusu" }).closest("li") as HTMLElement;
    expect(within(fin).getByRole("button", { name: "Ata" })).toBeInTheDocument();
  });

  it("aktif aday yoksa uyarı + üye yönetimi bağlantısı gösterir, atama butonu göstermez", () => {
    render(<ApprovalRoleList assignments={[]} members={[]} actorEmail={null} action={noop} />);
    expect(screen.getByText(/atanabilecek aktif bir üye bulunmuyor/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Üyeleri yönet" })).toHaveAttribute(
      "href",
      "/settings/team/members",
    );
    expect(screen.queryByRole("button", { name: "Ata" })).not.toBeInTheDocument();
  });
});
