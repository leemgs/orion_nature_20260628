#!/usr/bin/env python3
"""
Reproduce Figure 2 — Regime map and latency decomposition panels.

Generates a 2×2 subplot figure:
  (a) T_total vs R_C   (capacity-limited → coord-dominated boundary)
  (b) Latency decomposition at three operating points
  (c) T_total vs R_B   (all three regimes; shows I/O ranking inversion)
  (d) T_sync instability in coordination-dominated regime

Requires matplotlib. If unavailable, outputs CSV data for external plotting.

Usage:
    python experiments/reproduce_figure2.py [--save-csv]
    python experiments/reproduce_figure2.py --save-pdf figure2_reproduced.pdf
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orion.config import A100_80GB, THETA_C, THETA_B
from orion.profiler import HardwareProfiler
from orion.ratios import classify_regime
from experiments.simulated_backend import SimulatedBackend

RC_GRID = [0.10, 0.20, 0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.80,
           1.00, 1.20, 1.50, 1.91]
RB_GRID = [0.10, 0.20, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.80,
           1.00, 1.20, 1.61]

N_SWEEPS  = 3
N_WINDOWS = 15   # reduced for speed; use 30 for full reproduction


def collect_sweep_data(method: str, r_c_list, r_b_fixed: float, seed: int = 42):
    backend  = SimulatedBackend(hw=A100_80GB, method=method, seed=seed)
    profiler = HardwareProfiler(platform="A100-80GB")
    profiler.register_backend(backend)
    rows = []
    for rc in r_c_list:
        t_vals = []
        for s in range(N_SWEEPS):
            records = profiler.run_sweep(r_c=rc, r_b=r_b_fixed, sweep_id=s,
                                         n_windows=N_WINDOWS, warmup_sec=0)
            valid = [r for r in records if r.is_valid()]
            if valid:
                t_vals.append(statistics.mean(r.t_total for r in valid))
        rows.append({"r_c": rc, "r_b": r_b_fixed, "t_mean": statistics.mean(t_vals)
                     if t_vals else 0.0})
    return rows


def collect_decomposition(r_c: float, r_b: float, method: str = "orion"):
    backend  = SimulatedBackend(hw=A100_80GB, method=method, seed=99)
    profiler = HardwareProfiler()
    profiler.register_backend(backend)
    records = profiler.run_sweep(r_c=r_c, r_b=r_b, n_windows=N_WINDOWS, warmup_sec=0)
    valid = [r for r in records if r.is_valid()]
    if not valid:
        return {}
    return {
        "t_comp": statistics.mean(r.t_comp for r in valid),
        "t_mem":  statistics.mean(r.t_mem  for r in valid),
        "t_swap": statistics.mean(r.t_swap for r in valid),
        "t_sync": statistics.mean(r.t_sync for r in valid),
    }


def save_csv(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Panel (a): T_total vs R_C
    print("Collecting panel (a): T_total vs R_C …")
    panel_a = collect_sweep_data("orion", RC_GRID, r_b_fixed=1.61)
    with open(out_dir / "fig2a_rc_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["r_c", "r_b", "t_mean"])
        w.writeheader(); w.writerows(panel_a)

    # Panel (b): latency decomposition at 3 operating points
    print("Collecting panel (b): latency decomposition …")
    points = [
        ("capacity-limited",       0.30, 1.61),
        ("coordination-dominated", 0.75, 1.61),
        ("io-limited",             0.75, 0.25),
    ]
    with open(out_dir / "fig2b_decomposition.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["regime","r_c","r_b",
                                           "t_comp","t_mem","t_swap","t_sync"])
        w.writeheader()
        for label, rc, rb in points:
            d = collect_decomposition(rc, rb)
            w.writerow({"regime": label, "r_c": rc, "r_b": rb, **d})

    # Panel (c): T_total vs R_B (ranking inversion)
    print("Collecting panel (c): T_total vs R_B (multi-method) …")
    with open(out_dir / "fig2c_rb_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["method","r_b","t_mean"])
        w.writeheader()
        for method in ["pytorch", "flexgen", "orion"]:
            rows = []
            backend  = SimulatedBackend(hw=A100_80GB, method=method, seed=11)
            profiler = HardwareProfiler()
            profiler.register_backend(backend)
            for rb in RB_GRID:
                t_vals = []
                for s in range(N_SWEEPS):
                    records = profiler.run_sweep(r_c=0.75, r_b=rb, sweep_id=s,
                                                  n_windows=N_WINDOWS, warmup_sec=0)
                    valid = [r for r in records if r.is_valid()]
                    if valid:
                        t_vals.append(statistics.mean(r.t_total for r in valid))
                rows.append({"method": method, "r_b": rb,
                             "t_mean": statistics.mean(t_vals) if t_vals else 0.0})
            w.writerows(rows)

    print(f"\nCSV data saved to {out_dir}/")
    print("Use matplotlib / R / gnuplot to plot; see src/README.md §Plotting.")


def plot_figure(save_pdf: str = "") -> None:
    try:
        import matplotlib
        matplotlib.use("Agg" if save_pdf else "TkAgg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.lines import Line2D
    except ImportError:
        print("matplotlib not available — falling back to CSV output.")
        save_csv(Path("results/figure2"))
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle("Figure 2 — Regime map and latency decomposition (reproduced)",
                 fontsize=13)

    # --- Panel (a) T_total vs R_C ---
    ax = axes[0, 0]
    data_a = collect_sweep_data("orion", RC_GRID, r_b_fixed=1.61)
    rc_vals = [d["r_c"] for d in data_a]
    t_vals  = [d["t_mean"] for d in data_a]
    ax.plot(rc_vals, t_vals, "o-", color="steelblue")
    ax.axvline(THETA_C, color="red", linestyle="--", label=f"θ_C={THETA_C}")
    ax.set_xlabel("R_C = C_fast / W"); ax.set_ylabel("T_total [s]")
    ax.set_title("(a) Capacity-limited → Coord-dominated")
    ax.legend()

    # --- Panel (b) Decomposition ---
    ax = axes[0, 1]
    labels = ["cap-lim\n(0.30,1.61)", "coord-dom\n(0.75,1.61)", "io-lim\n(0.75,0.25)"]
    points = [(0.30, 1.61), (0.75, 1.61), (0.75, 0.25)]
    decomps = [collect_decomposition(rc, rb) for rc, rb in points]
    terms = ["t_comp", "t_mem", "t_swap", "t_sync"]
    colors = ["#4878cf", "#6acc65", "#d65f5f", "#b47cc7"]
    bottoms = [0.0] * 3
    for term, col in zip(terms, colors):
        vals = [d.get(term, 0) for d in decomps]
        ax.bar(labels, vals, bottom=bottoms, color=col, label=term)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax.set_ylabel("Latency [s]")
    ax.set_title("(b) Latency decomposition by regime")
    ax.legend(loc="upper right", fontsize=8)

    # --- Panel (c) R_B sweep multi-method ---
    ax = axes[1, 0]
    colors_m = {"pytorch": "gray", "flexgen": "orange", "orion": "steelblue"}
    for method in ["pytorch", "flexgen", "orion"]:
        backend  = SimulatedBackend(hw=A100_80GB, method=method, seed=11)
        profiler = HardwareProfiler()
        profiler.register_backend(backend)
        t_list = []
        for rb in RB_GRID:
            records = profiler.run_sweep(r_c=0.75, r_b=rb, n_windows=N_WINDOWS,
                                          warmup_sec=0)
            valid = [r for r in records if r.is_valid()]
            t_list.append(statistics.mean(r.t_total for r in valid) if valid else 0)
        ax.plot(RB_GRID, t_list, "o-", label=method, color=colors_m[method])
    ax.axvline(THETA_B, color="red", linestyle="--", label=f"θ_B={THETA_B}")
    ax.set_xlabel("R_B = B_slow·Δt / D"); ax.set_ylabel("T_total [s]")
    ax.set_title("(c) I/O-limited → Coord-dominated (ranking inversion)")
    ax.legend()

    # --- Panel (d) T_sync instability ---
    ax = axes[1, 1]
    backend  = SimulatedBackend(hw=A100_80GB, method="orion", seed=77)
    profiler = HardwareProfiler()
    profiler.register_backend(backend)
    records = profiler.run_sweep(r_c=0.75, r_b=1.61, n_windows=60, warmup_sec=0)
    t_sync_series = [r.t_sync for r in records if r.is_valid()]
    ax.plot(t_sync_series, color="purple", linewidth=0.8)
    ax.set_xlabel("Window index"); ax.set_ylabel("T_sync [s]")
    ax.set_title("(d) Synchronisation instability (coord-dominated)")

    plt.tight_layout()
    if save_pdf:
        plt.savefig(save_pdf, dpi=300, bbox_inches="tight")
        print(f"Figure saved → {save_pdf}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproduce Figure 2")
    parser.add_argument("--save-csv", action="store_true",
                        help="Save CSV data instead of plotting")
    parser.add_argument("--save-pdf", default="",
                        help="Save figure as PDF instead of showing interactively")
    args = parser.parse_args()

    if args.save_csv:
        save_csv(Path("results/figure2"))
    else:
        plot_figure(save_pdf=args.save_pdf)


if __name__ == "__main__":
    main()
