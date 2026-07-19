import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RoleBadge } from "@/components/role-badge";

describe("RoleBadge", () => {
  it("rolleri Türkçe etiketle gösterir", () => {
    const { rerender } = render(<RoleBadge role="team_manager" />);
    expect(screen.getByText("Ekip yöneticisi")).toBeInTheDocument();
    rerender(<RoleBadge role="finance" />);
    expect(screen.getByText("Finans")).toBeInTheDocument();
    rerender(<RoleBadge role="general_manager" />);
    expect(screen.getByText("Genel müdür")).toBeInTheDocument();
  });

  it("prefix'i etiketten önce gösterir", () => {
    render(<RoleBadge role="finance" prefix="Gereken:" />);
    expect(screen.getByText("Gereken:")).toBeInTheDocument();
    expect(screen.getByText("Finans")).toBeInTheDocument();
  });

  it("null rol → hiçbir şey render etmez", () => {
    const { container } = render(<RoleBadge role={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
