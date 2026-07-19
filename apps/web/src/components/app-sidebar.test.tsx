import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Server action modülünü stub'la (supabase/next-navigation import etmeden).
vi.mock("@/features/auth/actions", () => ({ signOutAction: async () => {} }));

import { AppSidebar } from "@/components/app-sidebar";

describe("AppSidebar", () => {
  it("tüm navigasyon bağlantılarını ve aktif organizasyon adını gösterir", () => {
    render(<AppSidebar userEmail="demo@example.com" organizationName="Acme Ltd" activeNav="overview" />);

    const nav = screen.getByRole("navigation", { name: "Ana menü" });
    for (const label of ["Genel Bakış", "Yeni Talep", "Taleplerim", "Onay Kutusu"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText("Acme Ltd")).toBeInTheDocument();
    expect(screen.getByText("demo@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Çıkış yap" })).toBeInTheDocument();
  });

  it("aktif route aria-current=page ile işaretlenir; diğerleri değil", () => {
    render(<AppSidebar userEmail={null} organizationName="Acme" activeNav="inbox" />);

    const active = screen.getByRole("link", { name: "Onay Kutusu" });
    expect(active).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Genel Bakış" })).not.toHaveAttribute("aria-current");
  });

  it("UUID gösterilmez (yalnız organizasyon adı)", () => {
    const { container } = render(
      <AppSidebar userEmail={null} organizationName="Acme" activeNav="overview" />,
    );
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it("uzun e-posta ve organizasyon adı taşmaz (truncate + title)", () => {
    const longEmail = "cok.uzun.bir.eposta.adresi.demo.kullanici@ornek-sirket-alan-adi.example.com";
    const longOrg = "Çok Uzun Bir Organizasyon Adı Anonim Şirketi ve Ortakları Limited";
    render(<AppSidebar userEmail={longEmail} organizationName={longOrg} activeNav="overview" />);

    const emailEl = screen.getByText(longEmail);
    expect(emailEl).toHaveClass("truncate");
    expect(emailEl).toHaveAttribute("title", longEmail);

    const orgEl = screen.getByText(longOrg);
    expect(orgEl).toHaveClass("truncate");
    expect(orgEl).toHaveAttribute("title", longOrg);
  });
});
