/** Engellenen görev yönetimi görünürlüğü (SAF). */

import { describe, expect, it } from "vitest";

import { canManageBlockedTasks } from "@/features/blocked-tasks/permissions";

describe("canManageBlockedTasks", () => {
  it("owner/admin görebilir ve çözebilir; member ve bilinmeyen göremez", () => {
    expect(canManageBlockedTasks("owner")).toBe(true);
    expect(canManageBlockedTasks("admin")).toBe(true);
    expect(canManageBlockedTasks("member")).toBe(false);
    expect(canManageBlockedTasks("guest")).toBe(false);
  });
});
