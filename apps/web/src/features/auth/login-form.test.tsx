/**
 * LoginForm testleri — fake action ile; gerçek Supabase ağına çağrı YOK.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ActionResult } from "@/features/auth/action-result";
import { LoginForm } from "@/features/auth/login-form";

function failingAction(message: string, fieldErrors?: Record<string, string[]>) {
  return async (): Promise<ActionResult> => ({ status: "error", message, fieldErrors });
}

/** Kontrollü deferred — pending durumu test sonunda çözülür, sızıntı bırakmaz. */
function deferredAction(): {
  action: () => Promise<ActionResult>;
  release: (result: ActionResult) => void;
} {
  let release: (result: ActionResult) => void = () => {};
  const action = () =>
    new Promise<ActionResult>((resolve) => {
      release = resolve;
    });
  return { action, release: (result) => release(result) };
}

describe("LoginForm", () => {
  it("e-posta ve şifre alanları ile giriş butonunu render eder", () => {
    render(<LoginForm action={failingAction("x")} />);

    expect(screen.getByLabelText("E-posta")).toBeInTheDocument();
    expect(screen.getByLabelText("Şifre")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Giriş yap" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Kayıt ol" })).toBeInTheDocument();
  });

  it("server action'dan gelen e-posta alan hatasını gösterir", async () => {
    const user = userEvent.setup();
    render(
      <LoginForm
        action={failingAction("Lütfen alanları kontrol edin.", {
          email: ["Geçerli bir e-posta adresi girin."],
        })}
      />,
    );

    await user.type(screen.getByLabelText("E-posta"), "gecersiz");
    await user.type(screen.getByLabelText("Şifre"), "sifre123");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    expect(
      await screen.findByText("Geçerli bir e-posta adresi girin."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("E-posta")).toHaveAttribute("aria-invalid", "true");
  });

  it("server action'dan gelen şifre alan hatasını gösterir", async () => {
    const user = userEvent.setup();
    render(
      <LoginForm
        action={failingAction("Lütfen alanları kontrol edin.", {
          password: ["Şifre gerekli."],
        })}
      />,
    );

    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.type(screen.getByLabelText("Şifre"), "x");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    expect(await screen.findByText("Şifre gerekli.")).toBeInTheDocument();
  });

  it("generic hata mesajı erişilebilir alert alanında görünür", async () => {
    const user = userEvent.setup();
    render(<LoginForm action={failingAction("E-posta veya şifre hatalı.")} />);

    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.type(screen.getByLabelText("Şifre"), "yanlis-sifre");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("E-posta veya şifre hatalı.");
  });

  it("pending durumda submit butonu disabled olur (çift submit engeli)", async () => {
    const user = userEvent.setup();
    const { action, release } = deferredAction();
    render(<LoginForm action={action} />);

    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.type(screen.getByLabelText("Şifre"), "sifre123");
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));

    const pendingButton = await screen.findByRole("button", {
      name: "Giriş yapılıyor…",
    });
    expect(pendingButton).toBeDisabled();

    // Pending'i çöz ve state güncellemesini flush et — sızıntı bırakma.
    release({ status: "idle" });
    await screen.findByRole("button", { name: "Giriş yap" });
  });

  it("şifre değeri ekrana/DOM metnine sızmaz", async () => {
    const user = userEvent.setup();
    const secret = "cok-gizli-sifre-marker";
    const { container } = render(
      <LoginForm action={failingAction("E-posta veya şifre hatalı.")} />,
    );

    await user.type(screen.getByLabelText("E-posta"), "a@b.com");
    await user.type(screen.getByLabelText("Şifre"), secret);
    await user.click(screen.getByRole("button", { name: "Giriş yap" }));
    await screen.findByRole("alert");

    // Input type=password kalır; şifre görünür metin olarak DOM'da yer almaz.
    expect(screen.getByLabelText("Şifre")).toHaveAttribute("type", "password");
    expect(container.textContent).not.toContain(secret);
  });
});
