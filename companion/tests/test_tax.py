"""GE tax reference cases from HANDOFF §4.2."""

from companion.tax import ge_tax

_CFG = {
    "rate": 0.02,
    "per_item_cap": 5_000_000,
    "free_below": 50,
    "exempt_items": ["Old school bond"],
}


def test_tax_normal() -> None:
    assert ge_tax(1250, "Magic logs", _CFG) == 25


def test_tax_below_free_threshold() -> None:
    assert ge_tax(49, "Feather", _CFG) == 0


def test_tax_cap() -> None:
    assert ge_tax(300_000_000, "Twisted bow", _CFG) == 5_000_000


def test_tax_exempt_bond() -> None:
    assert ge_tax(100_000_000, "Old school bond", _CFG) == 0
