/**
 * Üye mutasyon server action imza tipleri (yalnız TİP; değer importu yok).
 * Client bileşenleri bu tipler üzerinden action prop'u alır; fake action enjekte edilebilir.
 */

import type { MemberMutationResult } from "@/features/members/actions";

export type MemberMutationAction = (
  previous: MemberMutationResult,
  formData: FormData,
) => Promise<MemberMutationResult>;

export type ChangeRoleAction = MemberMutationAction;
export type SetStatusAction = MemberMutationAction;
