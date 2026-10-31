from __future__ import annotations

import gc
import logging
import os
import platform
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter, process_time

from findex.corpus import read_text
from findex.index import DEFAULT_CORPUS, WITH_POSITIONS_DEFAULT, build_parallel

log = logging.getLogger(__name__)

RUNS = 3
EXECUTORS = ("serial", "threads", "processes")
COUNTS = sorted({1, 2, 4, 8, os.cpu_count() or 1})


def gil_enabled() -> bool:
    fn = getattr(sys, "_is_gil_enabled", None)
    return True if fn is None else bool(fn())


def cpu_label() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return str(name).strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def median(xs: list[float]) -> float:
    ys = sorted(xs)
    return ys[len(ys) // 2]


def rss_bytes() -> int:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PMC),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)
        ok = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(pmc.WorkingSetSize)

    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def peak_rss[T](fn: object) -> tuple[object, int]:
    box = [0]
    stop = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            box[0] = max(box[0], rss_bytes())
            stop.wait(0.05)

    sampler = threading.Thread(target=watch, daemon=True)
    sampler.start()
    try:
        out = fn()  # type: ignore[operator]
    finally:
        stop.set()
        sampler.join()
    return out, box[0]


def once(executor: str, workers: int) -> tuple[float, float, int, float]:
    gc.collect()
    paths = sorted(DEFAULT_CORPUS.glob("*.txt"))

    def run() -> tuple[float, float, float]:
        c0 = process_time()
        t0 = perf_counter()
        _index, merge_s, worker_cpu = build_parallel(
            paths, workers, executor, WITH_POSITIONS_DEFAULT  # type: ignore[arg-type]
        )
        wall = perf_counter() - t0
        cpu = process_time() - c0
        if executor == "processes":
            cpu += worker_cpu
        return wall, cpu, merge_s

    (wall, cpu, merge_s), rss = peak_rss(run)
    return float(wall), float(cpu), int(rss), float(merge_s)


def save_plot(rows: list[tuple[object, ...]]) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib missing; skip plot")
        return None

    fig, ax = plt.subplots()
    names: list[str] = []
    xs_all: list[int] = []
    for row in rows:
        name = str(row[0])
        if name not in names:
            names.append(name)
    for name in names:
        pts = [row for row in rows if str(row[0]) == name]
        xs = [int(row[1]) for row in pts]  # type: ignore[arg-type]
        ys = [float(row[6]) for row in pts]
        xs_all.extend(xs)
        ax.plot(xs, ys, marker="o", label=name)
    top = max(xs_all) if xs_all else 1
    ax.plot([1, top], [1.0, float(top)], linestyle="--", color="gray", label="ideal")
    ax.set_xlabel("workers")
    ax.set_ylabel("speedup")
    ax.legend()
    filename = "speedup_free.png" if not gil_enabled() else "speedup.png"
    path = Path(__file__).resolve().parents[2] / filename
    fig.savefig(path, dpi=120, bbox_inches="tight")
    log.info("wrote %s", path)
    return path


_shared = 0


def _bump() -> None:
    global _shared
    for _ in range(10**6):
        _shared += 1


def race_demo() -> None:
    global _shared
    _shared = 0
    threads = [threading.Thread(target=_bump) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"race shared={_shared}", flush=True)

    lock = threading.Lock()
    _shared = 0

    def bump_locked() -> None:
        global _shared
        for _ in range(10**6):
            with lock:
                _shared += 1

    threads = [threading.Thread(target=bump_locked) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"locked shared={_shared}", flush=True)


def io_demo() -> None:
    paths = sorted(DEFAULT_CORPUS.glob("*.txt"))
    reps: list[Path] = []
    while len(reps) < 60:
        reps.extend(paths)
    reps = reps[:60]

    def nbytes(path: Path) -> int:
        return len(read_text(path))

    t0 = perf_counter()
    for path in reps:
        nbytes(path)
    serial_s = perf_counter() - t0

    t0 = perf_counter()
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(nbytes, reps))
    thread_s = perf_counter() - t0
    print(f"io serial={serial_s:.4f}s threads={thread_s:.4f}s", flush=True)


def main() -> None:
    if hasattr(sys, "_is_gil_enabled"):
        print("sys._is_gil_enabled()", sys._is_gil_enabled(), flush=True)
    else:
        print("sys._is_gil_enabled() missing; GIL is on", flush=True)
    print(f"cpu {cpu_label()} cores {os.cpu_count()}", flush=True)

    rows: list[tuple[object, ...]] = []
    serial_wall = 0.0
    for executor in EXECUTORS:
        counts = (1,) if executor == "serial" else COUNTS
        for n in counts:
            once(executor, n)  # warmup
            samples = [once(executor, n) for _ in range(RUNS)]
            wall = median([s[0] for s in samples])
            cpu = median([s[1] for s in samples])
            rss = median([float(s[2]) for s in samples])
            merge_s = median([s[3] for s in samples])
            if executor == "serial":
                serial_wall = wall
            speedup = serial_wall / wall if wall else 0.0
            rows.append((executor, n, wall, cpu, rss, merge_s, speedup))
            print(
                f"{executor:10} {n:2}  wall={wall:.3f}  cpu={cpu:.3f}  "
                f"rss={rss / 1048576:.1f}MiB  merge={merge_s:.3f}  speedup={speedup:.2f}",
                flush=True,
            )
    plot = save_plot(rows)
    if plot is not None:
        print("plot", plot, flush=True)
    race_demo()
    io_demo()


if __name__ == "__main__":
    main()
