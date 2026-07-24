/**
 * Engellenen görev çözümleme server action imza tipi (yalnız TİP; değer importu yok).
 * Client bileşenleri bu tip üzerinden action prop'u alır; fake action enjekte edilebilir.
 */

import type { BlockedTaskResolveResult } from "@/features/blocked-tasks/actions";

export type ResolveBlockedTaskAction = (
  previous: BlockedTaskResolveResult,
  formData: FormData,
) => Promise<BlockedTaskResolveResult>;
