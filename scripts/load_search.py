from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/search?q=alice")
    ap.add_argument("-c", type=int, default=50)
    ap.add_argument("-n", type=int, default=400)
    args = ap.parse_args()

    def one(_: int) -> float | None:
        t0 = time.perf_counter()
        try:
            r = httpx.get(args.url, timeout=30.0)
            ms = (time.perf_counter() - t0) * 1000.0
            return ms if r.status_code == 200 else None
        except Exception:
            return None

    t0 = time.perf_counter()
    lats: list[float] = []
    fail = 0
    with ThreadPoolExecutor(max_workers=args.c) as pool:
        futs = [pool.submit(one, i) for i in range(args.n)]
        for fut in as_completed(futs):
            ms = fut.result()
            if ms is None:
                fail += 1
            else:
                lats.append(ms)
    wall = time.perf_counter() - t0
    ok = len(lats)
    rps = ok / wall if wall else 0.0
    print(f"ok={ok} fail={fail} wall={wall:.2f}s RPS={rps:.2f}")
    print(f"p50={percentile(lats, 50):.2f} p95={percentile(lats, 95):.2f} p99={percentile(lats, 99):.2f}")


if __name__ == "__main__":
    main()
