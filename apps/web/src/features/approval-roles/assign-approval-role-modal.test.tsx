/**
 * AssignApprovalRoleModal testleri — fake action; gerçek backend YOK.
 * Aday select, ilk atama (expected_version yok) / değiştirme (var), no-op engeli, başarı/duplicate,
 * stale resubmit engeli, invalid_member_status, çift submit, dialog a11y.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ApprovalRoleMutationResult } from "@/features/approval-roles/actions";
import { AssignApprovalRoleModal } from "@/features/approval-roles/assign-approval-role-modal";
import type { MemberListItem } from "@/lib/api/resources";

const U1 = "11111111-1111-4111-8111-111111111111";
const U2 = "22222222-2222-4222-8222-222222222222";

function activeMember(userId: string, email: string): MemberListItem {
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

const CANDIDATES = [activeMember(U1, "one@x.com"), activeMember(U2, "two@x.com")];

function recording(next: () => ApprovalRoleMutationResult) {
  const calls: Record<string, string>[] = [];
  const action = async (
    _previous: ApprovalRoleMutationResult,
    formData: FormData,
  ): Promise<ApprovalRoleMutationResult> => {
    const entry: Record<string, string> = {};
    for (const [k, v] of formData.entries()) entry[k] = String(v);
    calls.push(entry);
    return next();
  };
  return { action, calls };
}

function deferred() {
  let release: (r: ApprovalRoleMutationResult) => void = () => {};
  const action = () => new Promise<ApprovalRoleMutationResult>((r) => (release = r));
  return { action, release: (r: ApprovalRoleMutationResult) => release(r) };
}

const success = (o: Partial<Extract<ApprovalRoleMutationResult, { status: "success" }>> = {}): ApprovalRoleMutationResult => ({
  status: "success",
  roleKey: "finance",
  assignedUserEmail: "one@x.com",
  version: 2,
  duplicate: false,
  ...o,
});

function renderModal(
  action: (p: ApprovalRoleMutationResult, fd: FormData) => Promise<ApprovalRoleMutationResult>,
  opts: { currentAssigneeId?: string | null; currentVersion?: number | null } = {},
) {
  return render(
    <AssignApprovalRoleModal
      roleKey="finance"
      roleLabel="Finans Sorumlusu"
      triggerLabel={opts.currentAssigneeId ? "Değiştir" : "Ata"}
      successMessage="Onay rolüne kullanıcı atandı."
      currentAssigneeId={opts.currentAssigneeId ?? null}
      currentVersion={opts.currentVersion ?? null}
      candidates={CANDIDATES}
      actorEmail={null}
      action={action}
    />,
  );
}

async function openModal(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole("button", { name }));
  return screen.findByRole("dialog");
}

describe("AssignApprovalRoleModal", () => {
  it("dialog açar, aday select + pinning notu gösterir (role=dialog)", async () => {
    const user = userEvent.setup();
    const { action } = recording(success);
    renderModal(action);

    const dialog = await openModal(user, "Ata");
    expect(within(dialog).getByLabelText("Kullanıcı")).toBeInTheDocument();
    expect(within(dialog).getByText(/yeni oluşturulacak/i)).toBeInTheDocument();
  });

  it("ilk atama: roleKey + userId gönderir, expected_version YOK", async () => {
    const user = userEvent.setup();
    const { action, calls } = recording(success);
    renderModal(action, { currentAssigneeId: null, currentVersion: null });

    await openModal(user, "Ata");
    await user.selectOptions(screen.getByLabelText("Kullanıcı"), U1);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(await screen.findByText("Onay rolüne kullanıcı atandı.")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ roleKey: "finance", userId: U1 });
    expect(calls[0].expectedVersion).toBeUndefined();
  });

  it("değiştirme: expectedVersion gönderilir; mevcut kullanıcıyla no-op submit engellenir", async () => {
    const user = userEvent.setup();
    const { action, calls } = recording(() => success({ version: 3 }));
    renderModal(action, { currentAssigneeId: U1, currentVersion: 2 });

    await openModal(user, "Değiştir");
    // Varsayılan seçim mevcut atanan (U1) → no-op → submit disabled.
    expect(screen.getByRole("button", { name: "Kaydet" })).toBeDisabled();
    // Farklı kullanıcı seç → etkin.
    await user.selectOptions(screen.getByLabelText("Kullanıcı"), U2);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(await screen.findByText("Onay rolüne kullanıcı atandı.")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ roleKey: "finance", userId: U2, expectedVersion: "2" });
  });

  it("seçim yapılmadan submit engellenir", async () => {
    const user = userEvent.setup();
    const { action } = recording(success);
    renderModal(action, { currentAssigneeId: null, currentVersion: null });

    await openModal(user, "Ata");
    expect(screen.getByRole("button", { name: "Kaydet" })).toBeDisabled();
  });

  it("duplicate=true güvenli 'zaten atanmış' mesajı gösterir", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => success({ duplicate: true }));
    renderModal(action, { currentAssigneeId: null, currentVersion: null });

    await openModal(user, "Ata");
    await user.selectOptions(screen.getByLabelText("Kullanıcı"), U1);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(await screen.findByText(/zaten ilgili onay rolüne atanmış/i)).toBeInTheDocument();
  });

  it("stale: mesaj gösterir, resubmit engellenir (yalnız Kapat)", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ({
      status: "error",
      kind: "stale",
      message: "Bu onay rolü başka bir işlem tarafından güncellendi. Liste yenilendi; lütfen tekrar deneyin.",
    }));
    renderModal(action, { currentAssigneeId: U1, currentVersion: 2 });

    await openModal(user, "Değiştir");
    await user.selectOptions(screen.getByLabelText("Kullanıcı"), U2);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(await screen.findByText(/başka bir işlem tarafından güncellendi/i)).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByLabelText("Kullanıcı")).not.toBeInTheDocument();
    expect(within(dialog).getAllByRole("button", { name: "Kapat" }).length).toBeGreaterThanOrEqual(1);
  });

  it("invalid_member_status: güvenli mesaj gösterir, yeniden denenebilir", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ({
      status: "error",
      kind: "invalid_member_status",
      message: "Yalnızca aktif organizasyon üyeleri onay rolüne atanabilir.",
    }));
    renderModal(action, { currentAssigneeId: null, currentVersion: null });

    await openModal(user, "Ata");
    await user.selectOptions(screen.getByLabelText("Kullanıcı"), U1);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    expect(await screen.findByText(/yalnızca aktif organizasyon üyeleri/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Kullanıcı")).toBeInTheDocument();
  });

  it("pending sırasında submit disabled (çift submit engeli)", async () => {
    const user = userEvent.setup();
    const { action, release } = deferred();
    renderModal(action, { currentAssigneeId: null, currentVersion: null });

    await openModal(user, "Ata");
    await user.selectOptions(screen.getByLabelText("Kullanıcı"), U1);
    await user.click(screen.getByRole("button", { name: "Kaydet" }));

    const pending = await screen.findByRole("button", { name: "Atanıyor…" });
    expect(pending).toBeDisabled();
    release(success());
    await screen.findByText("Onay rolüne kullanıcı atandı.");
  });
});
