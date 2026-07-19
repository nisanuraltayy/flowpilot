"""Approval role key + decision type allow-list'leri (owner-approved MVP kararı)."""

from __future__ import annotations

from enum import StrEnum


class ApprovalRoleKey(StrEnum):
    """Tenant başına üç approval role key (owner kararı #1)."""

    TEAM_MANAGER = "team_manager"
    FINANCE = "finance"
    GENERAL_MANAGER = "general_manager"


class ApprovalDecisionType(StrEnum):
    """MVP kararları: approve / reject (changes_requested MVP dışı)."""

    APPROVE = "approve"
    REJECT = "reject"


ALL_ROLE_KEYS: tuple[ApprovalRoleKey, ...] = (
    ApprovalRoleKey.TEAM_MANAGER,
    ApprovalRoleKey.FINANCE,
    ApprovalRoleKey.GENERAL_MANAGER,
)
