from findex.fuse import fuse_ranks


def test_fuse_ranks_prefers_shared_top() -> None:
    a = [1, 2, 3]
    b = [3, 1, 4]
    fused = fuse_ranks([a, b], k=60)
    ids = [doc for doc, _ in fused]
    assert ids[0] in (1, 3)
    assert set(ids) == {1, 2, 3, 4}
