/**
 * ResolveBlockedTaskModal testleri — fake action; gerçek backend YOK.
 * Onay diyaloğu (aday SEÇİMİ YOK), taskId gönderimi, başarı, çakışma → resubmit engeli,
 * çift submit, dialog a11y.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { BlockedTaskResolveResult } from "@/features/blocked-tasks/actions";
import { ResolveBlockedTaskModal } from "@/features/blocked-tasks/resolve-blocked-task-modal";

const TASK = "22222222-2222-4222-8222-222222222222";

function recording(next: () => BlockedTaskResolveResult) {
  const calls: Record<string, string>[] = [];
  const action = async (
    _previous: BlockedTaskResolveResult,
    formData: FormData,
  ): Promise<BlockedTaskResolveResult> => {
    const entry: Record<string, string> = {};
    for (const [k, v] of formData.entries()) entry[k] = String(v);
    calls.push(entry);
    return next();
  };
  return { action, calls };
}

function deferred() {
  let release: (r: BlockedTaskResolveResult) => void = () => {};
  const action = () => new Promise<BlockedTaskResolveResult>((r) => (release = r));
  return { action, release: (r: BlockedTaskResolveResult) => release(r) };
}

const success = (): BlockedTaskResolveResult => ({
  status: "success",
  approverRole: "finance",
  taskStatus: "active",
  version: 3,
});

function renderModal(
  action: (p: BlockedTaskResolveResult, fd: FormData) => Promise<BlockedTaskResolveResult>,
) {
  return render(
    <ResolveBlockedTaskModal
      taskId={TASK}
      approverRole="finance"
      blockedReason="self_approval_no_eligible_assignee"
      action={action}
    />,
  );
}

async function openModal(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Atamayı çöz" }));
  return screen.findByRole("dialog");
}

describe("ResolveBlockedTaskModal", () => {
  it("dialog açar; rol/neden + pinning notunu gösterir; aday SEÇİMİ YOK (role=dialog)", async () => {
    const user = userEvent.setup();
    const { action } = recording(success);
    renderModal(action);

    const dialog = await openModal(user);
    // "Finans Sorumlusu" hem rol alanında hem pinning notunda geçer.
    expect(within(dialog).getAllByText("Finans Sorumlusu").length).toBeGreaterThanOrEqual(1);
    expect(within(dialog).getByText("Kendi talebini onaylama engeli")).toBeInTheDocument();
    expect(within(dialog).getByText(/onay rolü yapılandırmasını\s+değiştirmez/i)).toBeInTheDocument();
    // Seçim kontrolü YOK (backend adayı kendisi seçer).
    expect(within(dialog).queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("onayda yalnız taskId gönderir; başarı mesajı gösterir", async () => {
    const user = userEvent.setup();
    const { action, calls } = recording(success);
    renderModal(action);

    const dialog = await openModal(user);
    await user.click(within(dialog).getByRole("button", { name: "Atamayı çöz" }));

    expect(await screen.findByText("Onay görevinin atama sorunu çözüldü.")).toBeInTheDocument();
    expect(calls[0]).toEqual({ taskId: TASK });
  });

  it("çakışma (not_blocked): mesaj gösterir, resubmit engellenir (yalnız Kapat)", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ({
      status: "error",
      kind: "not_blocked",
      message: "Bu onay görevi artık atama beklemiyor. Liste yenilendi.",
    }));
    renderModal(action);

    const dialog = await openModal(user);
    await user.click(within(dialog).getByRole("button", { name: "Atamayı çöz" }));

    expect(await screen.findByText(/artık atama beklemiyor/i)).toBeInTheDocument();
    const open = screen.getByRole("dialog");
    // Onay butonu artık yok (yalnız Kapat).
    expect(within(open).queryByRole("button", { name: "Atamayı çöz" })).not.toBeInTheDocument();
    expect(within(open).getAllByRole("button", { name: "Kapat" }).length).toBeGreaterThanOrEqual(1);
  });

  it("no_assignment çakışması: yeniden denenebilir (submit korunur)", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ({
      status: "error",
      kind: "no_assignment",
      message: "Bu görev için gerekli onay rolüne atanmış aktif bir kullanıcı yok. Önce Onay Rolleri sayfasından bir kullanıcı atayın.",
    }));
    renderModal(action);

    const dialog = await openModal(user);
    await user.click(within(dialog).getByRole("button", { name: "Atamayı çöz" }));

    expect(await screen.findByText(/gerekli onay rolüne atanmış aktif bir kullanıcı yok/i)).toBeInTheDocument();
    // no_assignment stale değildir → onay butonu korunur (rol atandıktan sonra tekrar denenebilir).
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Atamayı çöz" })).toBeInTheDocument();
  });

  it("pending sırasında submit disabled (çift submit engeli)", async () => {
    const user = userEvent.setup();
    const { action, release } = deferred();
    renderModal(action);

    const dialog = await openModal(user);
    await user.click(within(dialog).getByRole("button", { name: "Atamayı çöz" }));

    const pending = await screen.findByRole("button", { name: "Çözülüyor…" });
    expect(pending).toBeDisabled();
    release(success());
    await screen.findByText("Onay görevinin atama sorunu çözüldü.");
  });
});
