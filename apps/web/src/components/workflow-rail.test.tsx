import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkflowRail, type WorkflowStepData } from "@/components/workflow-rail";

const STEPS: WorkflowStepData[] = [
  { key: "req", label: "Talep", state: "completed" },
  { key: "tm", label: "Ekip yöneticisi", state: "completed" },
  { key: "fin", label: "Finans", state: "active" },
  { key: "res", label: "Sonuç", sublabel: "Bekliyor", state: "upcoming" },
];

describe("WorkflowRail", () => {
  it("tüm adım etiketlerini gösterir (yatay + dikey varyant)", () => {
    render(<WorkflowRail steps={STEPS} />);
    for (const label of ["Talep", "Ekip yöneticisi", "Finans", "Sonuç"]) {
      // exact:false — sr-only durum metni etikete eklidir.
      expect(screen.getAllByText(label, { exact: false }).length).toBeGreaterThan(0);
    }
  });

  it("durum YALNIZ renkle değil, ekran-okuyucu metniyle de anlatılır", () => {
    render(<WorkflowRail steps={STEPS} />);
    // Her durum için görünmez metin bulunur.
    expect(screen.getAllByText(/tamamlandı/).length).toBeGreaterThan(0); // completed
    expect(screen.getAllByText(/sırada/).length).toBeGreaterThan(0); // active
    expect(screen.getAllByText(/bekliyor/).length).toBeGreaterThan(0); // upcoming
  });

  it("rejected durumu için 'reddedildi' metni bulunur", () => {
    render(
      <WorkflowRail
        steps={[
          { key: "req", label: "Talep", state: "completed" },
          { key: "tm", label: "Ekip yöneticisi", state: "rejected" },
        ]}
      />,
    );
    expect(screen.getAllByText(/reddedildi/).length).toBeGreaterThan(0);
  });

  it("boş adım listesinde hiçbir şey render etmez", () => {
    const { container } = render(<WorkflowRail steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
