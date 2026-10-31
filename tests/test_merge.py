from __future__ import annotations

import pytest

from findex.merge import (
    difference_set,
    difference_sorted,
    intersect_set,
    intersect_sorted,
    union_set,
    union_sorted,
)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 2, 3], [2, 3, 4], [2, 3]),
        ([], [1], []),
        ([1, 5], [2, 5], [5]),
    ],
)
def test_intersect_sorted(left: list[int], right: list[int], expected: list[int]) -> None:
    assert intersect_sorted(left, right) == expected
    assert intersect_set(left, right) == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 3], [2, 3], [1, 2, 3]),
        ([], [4], [4]),
    ],
)
def test_union_sorted(left: list[int], right: list[int], expected: list[int]) -> None:
    assert union_sorted(left, right) == expected
    assert union_set(left, right) == expected


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 2, 3], [2], [1, 3]),
        ([1, 2], [3, 4], [1, 2]),
    ],
)
def test_difference_sorted(left: list[int], right: list[int], expected: list[int]) -> None:
    assert difference_sorted(left, right) == expected
    assert difference_set(left, right) == expected
