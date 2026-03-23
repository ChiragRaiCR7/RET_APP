"""Tests for simplified preview column classification helpers."""

from __future__ import annotations

from api.services.conversion_service import _classify_columns


def test_classify_columns_empty_inputs_returns_none_tuple():
    assert _classify_columns([], []) == (None, None)
    assert _classify_columns(["A"], []) == (None, None)


def test_classify_columns_detects_low_value_reasons():
    headers = ["mostly_empty", "all_same", "trivial_bool", "two_digit_flag", "high_value"]
    rows = [
        ["", "X", "true", "12", "alpha"],
        ["", "X", "false", "99", "beta"],
        ["", "X", "true", "12", "gamma"],
        ["", "X", "false", "99", "delta"],
        ["", "X", "true", "12", "epsilon"],
    ]

    meta, order = _classify_columns(headers, rows)

    assert meta is not None
    assert order is not None

    by_header = {m["header"]: m for m in meta}

    assert by_header["mostly_empty"]["classification"] == "low_value"
    assert by_header["mostly_empty"]["reason"] == "mostly_empty"

    assert by_header["all_same"]["classification"] == "low_value"
    assert by_header["all_same"]["reason"] == "all_same"

    assert by_header["trivial_bool"]["classification"] == "low_value"
    assert by_header["trivial_bool"]["reason"] == "trivial_boolean"

    # Regression guard: two-digit low-variance flags (e.g., 12 / 99) are treated as low-value.
    assert by_header["two_digit_flag"]["classification"] == "low_value"
    assert by_header["two_digit_flag"]["reason"] == "low_variance_flag"

    assert by_header["high_value"]["classification"] == "high_value"


def test_simplified_order_puts_high_value_columns_first():
    headers = ["A", "B", "C"]
    rows = [
        ["1", "same", "foo"],
        ["2", "same", "bar"],
        ["3", "same", "baz"],
    ]

    meta, order = _classify_columns(headers, rows)

    assert meta is not None
    assert order is not None

    # B is low-value (all_same); A and C should come first in the returned order.
    assert order[:2] == [0, 2]
    assert order[-1] == 1
