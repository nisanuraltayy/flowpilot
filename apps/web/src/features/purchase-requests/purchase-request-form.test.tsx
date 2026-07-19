/**
 * PurchaseRequestForm testleri — fake action; gerçek backend çağrısı YOK.
 * Actor/organization/workflow/approver alanı BULUNMAMALI (kimlik server context'ten).
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { CreatePurchaseRequestResult } from "@/features/purchase-requests/actions";
import { PurchaseRequestForm } from "@/features/purchase-requests/purchase-request-form";

function failing(
  message: string,
  fieldErrors?: Record<string, string[]>,
): () => Promise<CreatePurchaseRequestResult> {
  return async () => ({ status: "error", message, fieldErrors });
}

function deferred(): {
  action: () => Promise<CreatePurchaseRequestResult>;
  release: (r: CreatePurchaseRequestResult) => void;
} {
  let release: (r: CreatePurchaseRequestResult) => void = () => {};
  const action = () => new Promise<CreatePurchaseRequestResult>((resolve) => (release = resolve));
  return { action, release: (r) => release(r) };
}

describe("PurchaseRequestForm", () => {
  it("başlık, açıklama ve tutar alanlarını render eder; kimlik alanı içermez", () => {
    render(<PurchaseRequestForm action={failing("x")} />);

    expect(screen.getByLabelText(/Başlık/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Açıklama/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tutar/)).toBeInTheDocument();
    // Actor/org/workflow/approver form alanı YOK.
    expect(screen.queryByLabelText(/organizasyon/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/approver|onaycı|actor/i)).not.toBeInTheDocument();
  });

  it("tutar alan hatasını (server action'dan) gösterir", async () => {
    const user = userEvent.setup();
    render(
      <PurchaseRequestForm
        action={failing("Lütfen tutarı kontrol edin.", {
          amount: ["Tutar sıfırdan büyük olmalı."],
        })}
      />,
    );

    await user.type(screen.getByLabelText(/Başlık/), "Talep");
    await user.type(screen.getByLabelText(/Tutar/), "0");
    await user.click(screen.getByRole("button", { name: "Talebi oluştur" }));

    expect(await screen.findByText("Tutar sıfırdan büyük olmalı.")).toBeInTheDocument();
  });

  it("genel hata mesajını erişilebilir alert'te gösterir", async () => {
    const user = userEvent.setup();
    render(<PurchaseRequestForm action={failing("Servise şu anda erişilemiyor.")} />);

    await user.type(screen.getByLabelText(/Başlık/), "Talep");
    await user.type(screen.getByLabelText(/Tutar/), "12500");
    await user.click(screen.getByRole("button", { name: "Talebi oluştur" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Servise şu anda erişilemiyor.");
  });

  it("pending durumda submit butonu disabled (çift submit engeli)", async () => {
    const user = userEvent.setup();
    const { action, release } = deferred();
    render(<PurchaseRequestForm action={action} />);

    await user.type(screen.getByLabelText(/Başlık/), "Talep");
    await user.type(screen.getByLabelText(/Tutar/), "12500");
    await user.click(screen.getByRole("button", { name: "Talebi oluştur" }));

    const pending = await screen.findByRole("button", { name: "Oluşturuluyor…" });
    expect(pending).toBeDisabled();

    release({ status: "idle" });
    await screen.findByRole("button", { name: "Talebi oluştur" });
  });
});
