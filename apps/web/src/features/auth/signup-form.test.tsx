/**
 * SignupForm testleri — fake action ile; gerçek Supabase ağına çağrı YOK.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ActionResult } from "@/features/auth/action-result";
import { SignupForm } from "@/features/auth/signup-form";

function failingAction(message: string, fieldErrors?: Record<string, string[]>) {
  return async (): Promise<ActionResult> => ({ status: "error", message, fieldErrors });
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("E-posta"), "a@b.com");
  await user.type(screen.getByLabelText("Şifre"), "yeterince-uzun");
  await user.type(screen.getByLabelText("Şifre (tekrar)"), "farkli-sifre");
  await user.click(screen.getByRole("button", { name: "Kayıt ol" }));
}

describe("SignupForm", () => {
  it("tüm alanları render eder", () => {
    render(<SignupForm action={failingAction("x")} />);

    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
    expect(screen.getByLabelText("Şifre")).toBeInTheDocument();
    expect(screen.getByLabelText("Şifre (tekrar)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Giriş yap" })).toBeInTheDocument();
  });

  it("şifre tekrarı uyuşmazlığı hatasını gösterir", async () => {
    const user = userEvent.setup();
    render(
      <SignupForm
        action={failingAction("Lütfen alanları kontrol edin.", {
          passwordConfirm: ["Şifreler eşleşmiyor."],
        })}
      />,
    );

    await fillAndSubmit(user);

    expect(await screen.findByText("Şifreler eşleşmiyor.")).toBeInTheDocument();
  });

  it("generic auth hatası kullanıcı varlığını sızdırmadan gösterilir", async () => {
    const user = userEvent.setup();
    const genericMessage = "Kayıt işlemi şu anda tamamlanamadı. Lütfen tekrar deneyin.";
    render(<SignupForm action={failingAction(genericMessage)} />);

    await fillAndSubmit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(genericMessage);
    // "Bu e-posta zaten kayıtlı" benzeri sızdıran metin YOK.
    expect(alert.textContent).not.toMatch(/zaten|kayıtlı|mevcut/i);
  });

  it("şifre alanları password tipinde kalır", () => {
    render(<SignupForm action={failingAction("x")} />);

    expect(screen.getByLabelText("Şifre")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Şifre (tekrar)")).toHaveAttribute("type", "password");
  });
});
