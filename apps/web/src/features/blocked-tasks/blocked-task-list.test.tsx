/**
 * BlockedTaskList testleri — fake action; gerçek backend YOK. Rol/neden/durum, talep sahibi
 * e-postası (üye eşlemesi), null requester/pr, bilinmeyen reason fallback, resolve butonu.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { BlockedTaskResolveResult } from "@/features/blocked-tasks/actions";
import { BlockedTaskList } from "@/features/blocked-tasks/blocked-task-list";
import type { BlockedApprovalTask, MemberListItem } from "@/lib/api/resources";

const noop = async (): Promise<BlockedTaskResolveResult> => ({ status: "idle" });

const REQ = "44444444-4444-4444-8444-444444444444";
const PR = "33333333-3333-4333-8333-333333333333";

function task(o: Partial<BlockedApprovalTask> = {}): BlockedApprovalTask {
  return {
    taskId: o.taskId ?? "22222222-2222-4222-8222-222222222222",
    purchaseRequestId: "purchaseRequestId" in o ? (o.purchaseRequestId as string | null) : PR,
    approverRole: o.approverRole ?? "finance",
    status: o.status ?? "blocked",
    blockedReason: "blockedReason" in o ? (o.blockedReason as string | null) : "self_approval_no_eligible_assignee",
    requesterUserId: "requesterUserId" in o ? (o.requesterUserId as string | null) : REQ,
    version: o.version ?? 1,
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-10T00:00:00Z",
  };
}

function member(userId: string, email: string | null): MemberListItem {
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

describe("BlockedTaskList", () => {
  it("görev kartını rol/neden/durum + talep sahibi e-postası ile gösterir", () => {
    render(<BlockedTaskList tasks={[task()]} members={[member(REQ, "requester@x.com")]} action={noop} />);
    expect(screen.getByRole("heading", { name: "Finans Sorumlusu" })).toBeInTheDocument();
    expect(screen.getByText("Kendi talebini onaylama engeli")).toBeInTheDocument();
    expect(screen.getByText(/talebi oluşturan kişi/i)).toBeInTheDocument();
    expect(screen.getByText("Engellendi")).toBeInTheDocument();
    expect(screen.getByText("requester@x.com")).toBeInTheDocument();
    expect(screen.getByText(PR.slice(0, 8))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Atamayı çöz" })).toBeInTheDocument();
  });

  it("bilinmeyen reason güvenli fallback; null requester 'Bilinmiyor'; null pr '—'", () => {
    render(
      <BlockedTaskList
        tasks={[task({ blockedReason: "weird", requesterUserId: null, purchaseRequestId: null })]}
        members={[]}
        action={noop}
      />,
    );
    expect(screen.getByText("Atama sorunu")).toBeInTheDocument();
    expect(screen.getByText("Bilinmiyor")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("requester üye listesinde yoksa 'Bilinmiyor' gösterir (uydurmaz)", () => {
    render(<BlockedTaskList tasks={[task()]} members={[member("other-user", "other@x.com")]} action={noop} />);
    expect(screen.getByText("Bilinmiyor")).toBeInTheDocument();
    expect(screen.queryByText("other@x.com")).not.toBeInTheDocument();
  });

  it("birden fazla görevi listeler", () => {
    render(
      <BlockedTaskList
        tasks={[
          task({ taskId: "a1111111-1111-4111-8111-111111111111", approverRole: "finance" }),
          task({ taskId: "b2222222-2222-4222-8222-222222222222", approverRole: "team_manager" }),
        ]}
        members={[member(REQ, "r@x.com")]}
        action={noop}
      />,
    );
    expect(screen.getByRole("heading", { name: "Finans Sorumlusu" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Takım Yöneticisi" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Atamayı çöz" })).toHaveLength(2);
  });
});
