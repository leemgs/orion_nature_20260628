#!/usr/bin/env python3
"""
Regime probing sweep (Methods §Regime probing methodology).

Varies R_C ∈ [0.1, 2.0] and R_B ∈ [0.1, 2.0] independently,
collecting N_SWEEPS × N_WINDOWS latency records at each grid point.
Identifies regime boundaries as the R value where the dominant latency
term changes by > 1 s.d. across sweeps.

Usage:
    # Simulated (no GPU required):
    python experiments/run_regime_sweep.py --mode simulate

    # Live hardware (A100):
    python experiments/run_regime_sweep.py --mode live --platform A100-80GB

Output:
    results/regime_sweep/
      sweep_XX.jsonl    — raw measurement logs
      summary.json      — boundary estimates + sharpness coefficients
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from src/ root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statistics
from orion.config import N_SWEEPS, N_WINDOWS, THETA_C, THETA_B, A100_80GB
from orion.profiler import HardwareProfiler, validate_completeness
from orion.ratios import classify_regime
from orion.lower_bound import sharpness_coefficient
from utils.stats import SweepStats, bootstrap_ci, wilcoxon_one_sided
from experiments.simulated_backend import SimulatedBackend


# R_C sweep grid (covering capacity-limited → coordination-dominated boundary)
RC_GRID = [0.10, 0.20, 0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.80, 1.00,
           1.20, 1.50, 1.91, 2.00]

# R_B sweep grid (covering I/O-limited → coordination-dominated boundary)
RB_GRID = [0.10, 0.20, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.80, 1.00,
           1.20, 1.50, 1.61, 2.00]


def run_rc_sweep(
    profiler: HardwareProfiler,
    r_b_fixed: float = 1.61,
    n_sweeps: int = N_SWEEPS,
    n_windows: int = N_WINDOWS,
) -> dict:
    """Sweep R_C at fixed R_B, return latency and sharpness statistics."""
    results = []
    for rc in RC_GRID:
        sweep_means = []
        for s in range(n_sweeps):
            records = profiler.run_sweep(
                r_c=rc, r_b=r_b_fixed, sweep_id=s, n_windows=n_windows,
                warmup_sec=0,    # skip warmup in grid sweep for speed
            )
            valid = [r for r in records if r.is_valid()]
            if valid:
                sweep_means.append(statistics.mean(r.t_total for r in valid))

        stats = SweepStats(sweep_means)
        regime = classify_regime(rc, r_b_fixed)
        results.append({
            "r_c":    rc,
            "r_b":    r_b_fixed,
            "regime": regime.name,
            "t_mean": stats.grand_mean,
            "t_std":  stats.std,
            "ci95_lo": stats.ci95[0],
            "ci95_hi": stats.ci95[1],
        })
        print(f"  R_C={rc:.2f}  regime={regime.name:24s}  "
              f"T={stats.grand_mean:.4f}s ± {stats.std:.4f}s")

    # Sharpness coefficient S across R_C boundary
    t_vals = [r["t_mean"] for r in results]
    r_vals = [r["r_c"] for r in results]
    s_boundary = sharpness_coefficient(t_vals, r_vals)
    print(f"\n  Sharpness S at θ_C boundary: {s_boundary:.2f} "
          f"(paper: 4.12, S* = 2.0)")

    return {"rc_sweep": results, "s_at_theta_c": s_boundary}


def run_rb_sweep(
    profiler: HardwareProfiler,
    r_c_fixed: float = 0.75,
    n_sweeps: int = N_SWEEPS,
    n_windows: int = N_WINDOWS,
) -> dict:
    """Sweep R_B at fixed R_C, return latency and sharpness statistics."""
    results = []
    for rb in RB_GRID:
        sweep_means = []
        for s in range(n_sweeps):
            records = profiler.run_sweep(
                r_c=r_c_fixed, r_b=rb, sweep_id=s, n_windows=n_windows,
                warmup_sec=0,
            )
            valid = [r for r in records if r.is_valid()]
            if valid:
                sweep_means.append(statistics.mean(r.t_total for r in valid))

        stats = SweepStats(sweep_means)
        regime = classify_regime(r_c_fixed, rb)
        results.append({
            "r_c":    r_c_fixed,
            "r_b":    rb,
            "regime": regime.name,
            "t_mean": stats.grand_mean,
            "t_std":  stats.std,
            "ci95_lo": stats.ci95[0],
            "ci95_hi": stats.ci95[1],
        })
        print(f"  R_B={rb:.2f}  regime={regime.name:24s}  "
              f"T={stats.grand_mean:.4f}s ± {stats.std:.4f}s")

    t_vals = [r["t_mean"] for r in results]
    r_vals = [r["r_b"] for r in results]
    s_boundary = sharpness_coefficient(t_vals, r_vals)
    print(f"\n  Sharpness S at θ_B boundary: {s_boundary:.2f}")

    return {"rb_sweep": results, "s_at_theta_b": s_boundary}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orion regime probing sweep",
    )
    parser.add_argument("--mode", choices=["simulate", "live"],
                        default="simulate",
                        help="'simulate' for offline reproduction; "
                             "'live' requires CUDA + NVML")
    parser.add_argument("--platform", default="A100-80GB",
                        help="Hardware platform label")
    parser.add_argument("--method", default="orion",
                        help="Orchestration method (simulate mode only)")
    parser.add_argument("--output-dir", default="results/regime_sweep",
                        help="Directory for output JSONL and summary")
    parser.add_argument("--n-sweeps", type=int, default=N_SWEEPS)
    parser.add_argument("--n-windows", type=int, default=N_WINDOWS)
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    profiler = HardwareProfiler(platform=args.platform, output_dir=out)

    if args.mode == "simulate":
        backend = SimulatedBackend(hw=A100_80GB, method=args.method)
        profiler.register_backend(backend)
        print(f"[Simulated] platform={args.platform}  method={args.method}")
    else:
        try:
            from experiments.cuda_backend import CUDABackend
            backend = CUDABackend(platform=args.platform)
            profiler.register_backend(backend)
            print(f"[Live CUDA] platform={args.platform}")
        except ImportError:
            print("ERROR: cuda_backend not available. Use --mode simulate.")
            sys.exit(1)

    print("\n=== R_C sweep (R_B fixed at 1.61) ===")
    rc_results = run_rc_sweep(profiler, n_sweeps=args.n_sweeps,
                               n_windows=args.n_windows)

    print("\n=== R_B sweep (R_C fixed at 0.75) ===")
    rb_results = run_rb_sweep(profiler, n_sweeps=args.n_sweeps,
                               n_windows=args.n_windows)

    summary = {
        "platform": args.platform,
        "method":   args.method,
        "theta_c":  THETA_C,
        "theta_b":  THETA_B,
        **rc_results,
        **rb_results,
    }

    summary_path = out / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved → {summary_path}")

    # Save all raw records
    jsonl_path = out / "all_records.jsonl"
    profiler.save_jsonl(jsonl_path)
    print(f"Raw records  → {jsonl_path}  ({len(profiler.records)} windows)")


if __name__ == "__main__":
    main()
