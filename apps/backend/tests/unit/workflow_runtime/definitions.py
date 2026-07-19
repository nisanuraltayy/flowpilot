"""Test-only workflow definition fixture'ları (production kodu DEĞİL).

Runtime engine'i kanıtlamak için minimal satın-alma-benzeri akış. Onay eşikleri
BURADA (definition'da), Python koduna hard-code EDİLMEZ — Purchase Request eşikleri
sonraki story'de bağlanacak. Tutarlar minor unit (kuruş) + TRY.
"""

from __future__ import annotations

from typing import Any


def purchase_like_v1() -> dict[str, Any]:
    """3 bantlı koşul: <10.000 → 1 adım, 10.000-50.000 → 2 adım, >50.000 → 3 adım."""
    return {
        "workflow_key": "test-purchase-like",
        "nodes": [
            {"id": "start", "type": "start", "next": "form"},
            {"id": "form", "type": "form", "next": "amount", "config": {"fields": []}},
            {
                "id": "amount",
                "type": "condition",
                "config": {
                    "branches": [
                        {
                            "branch_id": "low",
                            "when": {
                                "field": "amount_minor",
                                "op": "lt",
                                "value": 1_000_000,
                                "currency": "TRY",
                            },
                            "next": "approval_low",
                        },
                        {
                            "branch_id": "mid",
                            "when": {
                                "field": "amount_minor",
                                "op": "lte",
                                "value": 5_000_000,
                                "currency": "TRY",
                            },
                            "next": "approval_mid",
                        },
                        {"branch_id": "high", "when": {"op": "otherwise"}, "next": "approval_high"},
                    ]
                },
            },
            {
                "id": "approval_low",
                "type": "sequential_approval",
                "next": "notify",
                "config": {"approver_chain": ["team_manager"]},
            },
            {
                "id": "approval_mid",
                "type": "sequential_approval",
                "next": "notify",
                "config": {"approver_chain": ["team_manager", "finance"]},
            },
            {
                "id": "approval_high",
                "type": "sequential_approval",
                "next": "notify",
                "config": {"approver_chain": ["team_manager", "finance", "general_manager"]},
            },
            {
                "id": "notify",
                "type": "notification",
                "next": "end",
                "config": {"recipient_role": "requester", "message_key": "purchase.finished"},
            },
            {"id": "end", "type": "end"},
        ],
    }


def purchase_like_v2() -> dict[str, Any]:
    """Eşik 20.000'e çekilmiş, zincirler değişmiş v2 (version pinning testi)."""
    return {
        "workflow_key": "test-purchase-like",
        "nodes": [
            {"id": "start", "type": "start", "next": "form"},
            {"id": "form", "type": "form", "next": "amount", "config": {"fields": []}},
            {
                "id": "amount",
                "type": "condition",
                "config": {
                    "branches": [
                        {
                            "branch_id": "low",
                            "when": {
                                "field": "amount_minor",
                                "op": "lt",
                                "value": 2_000_000,
                                "currency": "TRY",
                            },
                            "next": "approval_low",
                        },
                        {"branch_id": "high", "when": {"op": "otherwise"}, "next": "approval_high"},
                    ]
                },
            },
            {
                "id": "approval_low",
                "type": "sequential_approval",
                "next": "notify",
                "config": {"approver_chain": ["finance"]},
            },
            {
                "id": "approval_high",
                "type": "sequential_approval",
                "next": "notify",
                "config": {"approver_chain": ["finance", "general_manager"]},
            },
            {
                "id": "notify",
                "type": "notification",
                "next": "end",
                "config": {"recipient_role": "requester", "message_key": "purchase.finished"},
            },
            {"id": "end", "type": "end"},
        ],
    }
