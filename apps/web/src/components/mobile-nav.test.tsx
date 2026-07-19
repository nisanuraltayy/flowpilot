import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

// usePathname sabit bir route döndürsün (drawer aynı route'ta açık kalır).
vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));

import { MobileNav } from "@/components/mobile-nav";

describe("MobileNav", () => {
  it("başlangıçta çekmece kapalı; menü butonu aria-expanded=false", () => {
    render(
      <MobileNav>
        <div>Kenar çubuğu içeriği</div>
      </MobileNav>,
    );
    const toggle = screen.getByRole("button", { name: "Menüyü aç" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog", { name: "Menü" })).not.toBeInTheDocument();
  });

  it("menü butonu çekmeceyi açar (dialog + içerik görünür), aria-expanded=true olur", async () => {
    const user = userEvent.setup();
    render(
      <MobileNav>
        <div>Kenar çubuğu içeriği</div>
      </MobileNav>,
    );

    await user.click(screen.getByRole("button", { name: "Menüyü aç" }));

    expect(screen.getByRole("dialog", { name: "Menü" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Menüyü aç" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getAllByText("Kenar çubuğu içeriği").length).toBeGreaterThan(0);
  });

  it("kapat butonu çekmeceyi kapatır", async () => {
    const user = userEvent.setup();
    render(
      <MobileNav>
        <div>Kenar çubuğu içeriği</div>
      </MobileNav>,
    );

    await user.click(screen.getByRole("button", { name: "Menüyü aç" }));
    // Panel içindeki kapat butonu (üst köşedeki).
    const closeButtons = screen.getAllByRole("button", { name: "Menüyü kapat" });
    await user.click(closeButtons[closeButtons.length - 1]);

    expect(screen.queryByRole("dialog", { name: "Menü" })).not.toBeInTheDocument();
  });
});
