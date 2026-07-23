/**
 * MemberMutationModal testleri — onaylı mutasyon modalı; fake action, gerçek backend YOK.
 * Rol/durum gönderimi, başarı/duplicate mesajı, stale (resubmit engeli), hata, çift submit, a11y.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MemberMutationResult } from "@/features/members/actions";
import { MemberMutationModal } from "@/features/members/member-mutation-modal";

const U = "11111111-1111-4111-8111-111111111111";

function recording(next: () => MemberMutationResult) {
  const calls: Record<string, string>[] = [];
  const action = async (
    _previous: MemberMutationResult,
    formData: FormData,
  ): Promise<MemberMutationResult> => {
    const entry: Record<string, string> = {};
    for (const [k, v] of formData.entries()) entry[k] = String(v);
    calls.push(entry);
    return next();
  };
  return { action, calls };
}

function deferred() {
  let release: (r: MemberMutationResult) => void = () => {};
  const action = () => new Promise<MemberMutationResult>((r) => (release = r));
  return { action, release: (r: MemberMutationResult) => release(r) };
}

const ok = (o: Partial<Extract<MemberMutationResult, { status: "success" }>> = {}): MemberMutationResult => ({
  status: "success",
  role: "admin",
  memberStatus: "active",
  version: 3,
  duplicate: false,
  ...o,
});

function renderStatusModal(action: MemberMutationModalProps["action"]) {
  return render(
    <MemberMutationModal
      triggerLabel="Askıya al"
      triggerVariant="secondary"
      title="Üyeyi askıya al"
      confirmLabel="Evet, askıya al"
      pendingLabel="Askıya alınıyor…"
      confirmVariant="danger"
      successMessage="Üye askıya alındı."
      duplicateMessage="Üye zaten askıda; değişiklik yapılmadı."
      targetUserId={U}
      expectedVersion={4}
      status="suspended"
      action={action}
    >
      <p>Bu üye askıya alınacak.</p>
    </MemberMutationModal>,
  );
}

type MemberMutationModalProps = Parameters<typeof MemberMutationModal>[0];

async function open(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole("button", { name }));
  return screen.findByRole("dialog");
}

describe("MemberMutationModal — durum değişimi", () => {
  it("tetikleyici dialog açar, açıklamayı gösterir (role=dialog)", async () => {
    const user = userEvent.setup();
    const { action } = recording(ok);
    renderStatusModal(action);

    const dialog = await open(user, "Askıya al");
    expect(within(dialog).getByText("Bu üye askıya alınacak.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Evet, askıya al" })).toBeInTheDocument();
  });

  it("onayda status + expected_version + targetUserId gönderir; başarı mesajı gösterir", async () => {
    const user = userEvent.setup();
    const { action, calls } = recording(ok);
    renderStatusModal(action);

    await open(user, "Askıya al");
    await user.click(screen.getByRole("button", { name: "Evet, askıya al" }));

    expect(await screen.findByText("Üye askıya alındı.")).toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ targetUserId: U, expectedVersion: "4", status: "suspended" });
  });

  it("duplicate=true güvenli 'değişiklik yok' mesajı gösterir", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ok({ duplicate: true }));
    renderStatusModal(action);

    await open(user, "Askıya al");
    await user.click(screen.getByRole("button", { name: "Evet, askıya al" }));

    expect(await screen.findByText(/değişiklik yapılmadı/i)).toBeInTheDocument();
  });

  it("stale (409 concurrency): mesaj gösterir, RESUBMIT engellenir (yalnız Kapat)", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ({
      status: "error",
      kind: "stale",
      message: "Bu üye başka bir işlem tarafından güncellendi. Liste yenilendi; lütfen tekrar deneyin.",
    }));
    renderStatusModal(action);

    await open(user, "Askıya al");
    await user.click(screen.getByRole("button", { name: "Evet, askıya al" }));

    expect(await screen.findByText(/başka bir işlem tarafından güncellendi/i)).toBeInTheDocument();
    const dialog = screen.getByRole("dialog");
    // Resubmit engellenir: onay butonu yok. (Kapat: hem header × hem footer aynı ada sahip.)
    expect(within(dialog).queryByRole("button", { name: "Evet, askıya al" })).not.toBeInTheDocument();
    expect(within(dialog).getAllByRole("button", { name: "Kapat" }).length).toBeGreaterThanOrEqual(1);
  });

  it("stale olmayan çakışma: mesaj gösterir ve yeniden denemeye izin verir", async () => {
    const user = userEvent.setup();
    const { action } = recording(() => ({
      status: "error",
      kind: "final_owner",
      message: "Organizasyonda en az bir aktif sahip bulunmalıdır. Önce başka bir kullanıcıyı sahip yapın.",
    }));
    renderStatusModal(action);

    await open(user, "Askıya al");
    await user.click(screen.getByRole("button", { name: "Evet, askıya al" }));

    expect(await screen.findByText(/en az bir aktif sahip/i)).toBeInTheDocument();
    // Yeniden deneme mümkün (submit hâlâ var).
    expect(screen.getByRole("button", { name: "Evet, askıya al" })).toBeInTheDocument();
  });

  it("pending sırasında submit disabled (çift submit engeli)", async () => {
    const user = userEvent.setup();
    const { action, release } = deferred();
    renderStatusModal(action);

    await open(user, "Askıya al");
    await user.click(screen.getByRole("button", { name: "Evet, askıya al" }));

    const pending = await screen.findByRole("button", { name: "Askıya alınıyor…" });
    expect(pending).toBeDisabled();
    release(ok());
    await screen.findByText("Üye askıya alındı.");
  });
});

describe("MemberMutationModal — rol değişimi (children'daki select)", () => {
  it("seçilen rolü form ile gönderir", async () => {
    const user = userEvent.setup();
    const { action, calls } = recording(() => ok({ role: "admin" }));
    render(
      <MemberMutationModal
        triggerLabel="Rol değiştir"
        triggerVariant="secondary"
        title="Üyenin rolünü değiştir"
        confirmLabel="Rolü güncelle"
        pendingLabel="Güncelleniyor…"
        confirmVariant="primary"
        successMessage="Üyenin rolü güncellendi."
        duplicateMessage="Üye zaten bu role sahip; değişiklik yapılmadı."
        targetUserId={U}
        expectedVersion={2}
        action={action}
      >
        <label htmlFor="role-x">Yeni rol</label>
        <select id="role-x" name="role" defaultValue="admin">
          <option value="admin">Yönetici</option>
          <option value="owner">Sahip</option>
        </select>
      </MemberMutationModal>,
    );

    await open(user, "Rol değiştir");
    await user.selectOptions(screen.getByLabelText("Yeni rol"), "owner");
    await user.click(screen.getByRole("button", { name: "Rolü güncelle" }));

    expect(await screen.findByText("Üyenin rolü güncellendi.")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ targetUserId: U, expectedVersion: "2", role: "owner" });
    // Status GÖNDERİLMEZ (rol modu).
    expect(calls[0].status).toBeUndefined();
  });
});
