/**
 * OrganizationForm testleri — fake action ile; backend'e gerçek çağrı YOK.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CreateOrganizationActionResult } from "@/features/organizations/actions";
import { OrganizationForm } from "@/features/organizations/organization-form";

type Action = (
  previous: CreateOrganizationActionResult,
  formData: FormData,
) => Promise<CreateOrganizationActionResult>;

function staticAction(result: CreateOrganizationActionResult): Action {
  return async () => result;
}

async function submitName(user: ReturnType<typeof userEvent.setup>, name: string) {
  const input = screen.getByLabelText("Organizasyon adı");
  if (name) {
    await user.type(input, name);
  }
  await user.click(screen.getByRole("button", { name: "Şirketini oluştur" }));
}

describe("OrganizationForm", () => {
  it("ad alanını, açıklamayı ve submit butonunu render eder", () => {
    render(<OrganizationForm action={staticAction({ status: "idle" })} />);

    expect(screen.getByLabelText("Organizasyon adı")).toBeInTheDocument();
    expect(screen.getByText(/1–200 karakter/)).toBeInTheDocument();
    // Actor/owner/tenant ID form alanı BULUNMAZ.
    expect(screen.queryByLabelText(/actor/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/owner/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/tenant/i)).not.toBeInTheDocument();
    const form = screen.getByRole("button", { name: "Şirketini oluştur" }).closest("form");
    expect(form?.querySelectorAll("input")).toHaveLength(1);
  });

  it("boş ad hatasını gösterir", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationForm
        action={staticAction({
          status: "error",
          message: "Lütfen organizasyon adını kontrol edin.",
          fieldErrors: { name: ["Organizasyon adı boş olamaz."] },
        })}
      />,
    );

    await submitName(user, "x");
    expect(await screen.findByText("Organizasyon adı boş olamaz.")).toBeInTheDocument();
  });

  it("backend 422 mesajını güvenli biçimde gösterir", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationForm
        action={staticAction({
          status: "error",
          message: "Organizasyon adi en fazla 200 karakter olabilir.",
          fieldErrors: { name: ["Organizasyon adi en fazla 200 karakter olabilir."] },
        })}
      />,
    );

    await submitName(user, "Acme");
    // Backend 422 hem üst Alert'te hem alan hatasında görünür (2 alert).
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
    expect(
      alerts.some((a) =>
        a.textContent?.includes("Organizasyon adi en fazla 200 karakter olabilir."),
      ),
    ).toBe(true);
    for (const alert of alerts) {
      expect(alert.textContent).not.toMatch(/Traceback|sqlalchemy|psycopg/i);
    }
  });

  it("backend 503 mesajını güvenli biçimde gösterir", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationForm
        action={staticAction({
          status: "error",
          message:
            "Kimlik doğrulama servisine şu anda erişilemiyor. Lütfen birkaç dakika sonra tekrar deneyin.",
        })}
      />,
    );

    await submitName(user, "Acme");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Kimlik doğrulama servisine şu anda erişilemiyor/,
    );
  });

  it("başarılı sonuçta organizasyon adı ve owner bilgisi görünür", async () => {
    const user = userEvent.setup();
    render(
      <OrganizationForm
        action={staticAction({
          status: "success",
          organizationId: "11111111-1111-4111-8111-111111111111",
          ownerMembershipId: "22222222-2222-4222-8222-222222222222",
          name: "Acme Teknoloji",
        })}
      />,
    );

    await submitName(user, "Acme Teknoloji");

    expect(await screen.findByRole("status")).toHaveTextContent(
      /"Acme Teknoloji" organizasyonu oluşturuldu/,
    );
    expect(screen.getByText(/Owner üyeliğin de oluşturuldu/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Panele devam et" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    // UUID'ler ana görsel öğe DEĞİL — katlanmış teknik detay içinde.
    expect(screen.getByText("Teknik detaylar")).toBeInTheDocument();
  });

  it("pending durumda buton disabled olur (çift submit engeli)", async () => {
    const user = userEvent.setup();
    let release: (r: CreateOrganizationActionResult) => void = () => {};
    const action: Action = () =>
      new Promise<CreateOrganizationActionResult>((resolve) => {
        release = resolve;
      });
    render(<OrganizationForm action={action} />);

    await submitName(user, "Acme");

    const pendingButton = await screen.findByRole("button", { name: "Oluşturuluyor…" });
    expect(pendingButton).toBeDisabled();

    release({ status: "idle" });
    await screen.findByRole("button", { name: "Şirketini oluştur" });
  });

  it("pending sırasında ikinci tıklama action'ı tekrar çağırmaz", async () => {
    const user = userEvent.setup();
    let release: (r: CreateOrganizationActionResult) => void = () => {};
    const spy = vi.fn(
      (): Promise<CreateOrganizationActionResult> =>
        new Promise<CreateOrganizationActionResult>((resolve) => {
          release = resolve;
        }),
    );
    render(<OrganizationForm action={spy} />);

    await submitName(user, "Acme");
    const pendingButton = await screen.findByRole("button", { name: "Oluşturuluyor…" });
    await user.click(pendingButton); // disabled — etkisiz

    expect(spy).toHaveBeenCalledTimes(1);

    release({ status: "idle" });
    await screen.findByRole("button", { name: "Şirketini oluştur" });
  });
});
