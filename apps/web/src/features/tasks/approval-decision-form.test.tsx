/**
 * ApprovalDecisionForm testleri — fake action; gerçek backend çağrısı YOK.
 * Onay/ret butonları, pending çift-submit engeli, 409 çakışma güvenli mesajı.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { DecideTaskResult } from "@/features/tasks/actions";
import { ApprovalDecisionForm } from "@/features/tasks/approval-decision-form";

const TASK = "task-123";

function conflictAction(): () => Promise<DecideTaskResult> {
  return async () => ({ status: "error", message: "Karar çakışması: bu görev zaten karara bağlandı." });
}

function capturingAction(): {
  action: (p: DecideTaskResult, f: FormData) => Promise<DecideTaskResult>;
  captured: { decision?: string; comment?: string; taskId?: string };
} {
  const captured: { decision?: string; comment?: string; taskId?: string } = {};
  const action = async (_p: DecideTaskResult, formData: FormData): Promise<DecideTaskResult> => {
    captured.decision = String(formData.get("decision") ?? "");
    captured.comment = String(formData.get("comment") ?? "");
    captured.taskId = String(formData.get("taskId") ?? "");
    return { status: "idle" };
  };
  return { action, captured };
}

function deferred(): {
  action: () => Promise<DecideTaskResult>;
  release: (r: DecideTaskResult) => void;
} {
  let release: (r: DecideTaskResult) => void = () => {};
  const action = () => new Promise<DecideTaskResult>((resolve) => (release = resolve));
  return { action, release: (r) => release(r) };
}

describe("ApprovalDecisionForm", () => {
  it("onayla ve reddet butonlarını + yorum alanını render eder", () => {
    render(<ApprovalDecisionForm taskId={TASK} action={conflictAction()} />);
    expect(screen.getByRole("button", { name: /Onayla/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reddet/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/Yorum/)).toBeInTheDocument();
  });

  it("onayla → decision=approve, taskId ve yorumu action'a iletir", async () => {
    const user = userEvent.setup();
    const { action, captured } = capturingAction();
    render(<ApprovalDecisionForm taskId={TASK} action={action} />);

    await user.type(screen.getByLabelText(/Yorum/), "uygundur");
    await user.click(screen.getByRole("button", { name: /Onayla/ }));

    expect(captured.decision).toBe("approve");
    expect(captured.taskId).toBe(TASK);
    expect(captured.comment).toBe("uygundur");
  });

  it("reddet → decision=reject iletir", async () => {
    const user = userEvent.setup();
    const { action, captured } = capturingAction();
    render(<ApprovalDecisionForm taskId={TASK} action={action} />);

    await user.click(screen.getByRole("button", { name: /Reddet/ }));

    expect(captured.decision).toBe("reject");
  });

  it("409 çakışmayı güvenli alert mesajı olarak gösterir", async () => {
    const user = userEvent.setup();
    render(<ApprovalDecisionForm taskId={TASK} action={conflictAction()} />);

    await user.click(screen.getByRole("button", { name: /Onayla/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Karar çakışması");
  });

  it("pending sırasında her iki buton da disabled (çift submit engeli)", async () => {
    const user = userEvent.setup();
    const { action, release } = deferred();
    render(<ApprovalDecisionForm taskId={TASK} action={action} />);

    await user.click(screen.getByRole("button", { name: /Onayla/ }));

    // Pending'de her iki buton da "Gönderiliyor…" gösterir ve disabled olur.
    const pendingButtons = await screen.findAllByRole("button", { name: /Gönderiliyor/ });
    expect(pendingButtons).toHaveLength(2);
    for (const button of pendingButtons) {
      expect(button).toBeDisabled();
    }

    release({ status: "idle" });
    await screen.findByRole("button", { name: /Onayla/ });
  });
});
