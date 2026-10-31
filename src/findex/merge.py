from __future__ import annotations


def intersect_sorted(left: list[int], right: list[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    n_l, n_r = len(left), len(right)
    while i < n_l and j < n_r:
        a, b = left[i], right[j]
        if a == b:
            out.append(a)
            i += 1
            j += 1
        elif a < b:
            i += 1
        else:
            j += 1
    return out


def union_sorted(left: list[int], right: list[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    n_l, n_r = len(left), len(right)
    while i < n_l and j < n_r:
        a, b = left[i], right[j]
        if a == b:
            out.append(a)
            i += 1
            j += 1
        elif a < b:
            out.append(a)
            i += 1
        else:
            out.append(b)
            j += 1
    if i < n_l:
        out.extend(left[i:])
    if j < n_r:
        out.extend(right[j:])
    return out


def difference_sorted(left: list[int], right: list[int]) -> list[int]:
    i = j = 0
    out: list[int] = []
    n_l, n_r = len(left), len(right)
    while i < n_l and j < n_r:
        a, b = left[i], right[j]
        if a == b:
            i += 1
            j += 1
        elif a < b:
            out.append(a)
            i += 1
        else:
            j += 1
    if i < n_l:
        out.extend(left[i:])
    return out


def intersect_set(left: list[int], right: list[int]) -> list[int]:
    return sorted(set(left).intersection(right))


def union_set(left: list[int], right: list[int]) -> list[int]:
    return sorted(set(left).union(right))


def difference_set(left: list[int], right: list[int]) -> list[int]:
    return sorted(set(left).difference(right))
