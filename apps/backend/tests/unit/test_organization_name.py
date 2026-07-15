"""OrganizationName value object doğrulama testleri."""

from __future__ import annotations

import pytest

from flowpilot.modules.organization.domain.errors import (
    EmptyOrganizationNameError,
    OrganizationNameTooLongError,
)
from flowpilot.modules.organization.domain.organization_name import OrganizationName


def test_valid_name_is_accepted() -> None:
    name = OrganizationName("Acme A.S.")
    assert str(name) == "Acme A.S."


def test_name_is_trimmed() -> None:
    assert OrganizationName("  Acme  ").value == "Acme"


def test_empty_name_is_rejected() -> None:
    with pytest.raises(EmptyOrganizationNameError):
        OrganizationName("")


def test_whitespace_only_name_is_rejected() -> None:
    with pytest.raises(EmptyOrganizationNameError):
        OrganizationName("   \t  ")


def test_name_at_max_length_is_accepted() -> None:
    value = "a" * OrganizationName.MAX_LENGTH
    assert OrganizationName(value).value == value


def test_name_over_max_length_is_rejected() -> None:
    with pytest.raises(OrganizationNameTooLongError):
        OrganizationName("a" * (OrganizationName.MAX_LENGTH + 1))
