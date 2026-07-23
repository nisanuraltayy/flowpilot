/**
 * Onay rolü atama server action imza tipi (yalnız TİP; değer importu yok).
 * Client bileşenleri bu tip üzerinden action prop'u alır; fake action enjekte edilebilir.
 */

import type { ApprovalRoleMutationResult } from "@/features/approval-roles/actions";

export type AssignApprovalRoleAction = (
  previous: ApprovalRoleMutationResult,
  formData: FormData,
) => Promise<ApprovalRoleMutationResult>;
