/**
 * SelectOrganizationForm testleri — fake action. Organizasyon adı + üyelik türü
 * gösterilir; UUID ana görsel bilgi DEĞİLDİR (ekran metninde görünmez).
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { SelectOrganizationResult } from "@/features/organizations/select-actions";
import { SelectOrganizationForm } from "@/features/organizations/select-organization-form";
import type { MyOrganization } from "@/lib/api/resources";

const ORGS: MyOrganization[] = [
  {
    organizationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    name: "Acme",
    membershipKind: "owner",
    membershipStatus: "active",
  },
  {
    organizationId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    name: "Beta",
    membershipKind: "member",
    membershipStatus: "active",
  },
];

function idleAction(): () => Promise<SelectOrganizationResult> {
  return async () => ({ status: "idle" });
}

function capturingAction(): {
  action: (p: SelectOrganizationResult, f: FormData) => Promise<SelectOrganizationResult>;
  captured: { organizationId?: string };
} {
  const captured: { organizationId?: string } = {};
  const action = async (
    _p: SelectOrganizationResult,
    formData: FormData,
  ): Promise<SelectOrganizationResult> => {
    captured.organizationId = String(formData.get("organizationId") ?? "");
    return { status: "idle" };
  };
  return { action, captured };
}

describe("SelectOrganizationForm", () => {
  it("organizasyon adlarını ve üyelik türlerini gösterir; UUID metinde görünmez", () => {
    const { container } = render(
      <SelectOrganizationForm organizations={ORGS} action={idleAction()} />,
    );

    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Sahip")).toBeInTheDocument();
    expect(screen.getByText("Üye")).toBeInTheDocument();
    expect(container.textContent).not.toContain("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  });

  it("ilk organizasyon varsayılan seçilidir ve seçim action'a iletilir", async () => {
    const user = userEvent.setup();
    const { action, captured } = capturingAction();
    render(<SelectOrganizationForm organizations={ORGS} action={action} />);

    await user.click(screen.getByRole("button", { name: "Bu organizasyonda devam et" }));
    expect(captured.organizationId).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
  });

  it("ikinci organizasyon seçilebilir", async () => {
    const user = userEvent.setup();
    const { action, captured } = capturingAction();
    render(<SelectOrganizationForm organizations={ORGS} action={action} />);

    await user.click(screen.getByRole("radio", { name: /Beta/ }));
    await user.click(screen.getByRole("button", { name: "Bu organizasyonda devam et" }));
    expect(captured.organizationId).toBe("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb");
  });

  it("hata mesajını erişilebilir alert'te gösterir", async () => {
    const user = userEvent.setup();
    const action = async (): Promise<SelectOrganizationResult> => ({
      status: "error",
      message: "Bu organizasyon seçilemedi.",
    });
    render(<SelectOrganizationForm organizations={ORGS} action={action} />);

    await user.click(screen.getByRole("button", { name: "Bu organizasyonda devam et" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu organizasyon seçilemedi.");
  });
});
