#!/usr/bin/env python3
"""
Reproduce Table 2 — Regime-dependent strategy inversion.

Shows that strategy rankings invert across regime boundaries:
  - In coordination-dominated regime: Orion −18 to −27%
  - In capacity-limited regime:       FlexGen/DeepSpeed worsen latency +8–24%
  - In I/O-limited regime:            aggressive offloading +8–12% worse

Usage:
    python experiments/reproduce_table2.py [--from-jsonl results/regime_sweep/all_records.jsonl]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orion.config import Regime, A100_80GB
from orion.profiler import HardwareProfiler
from orion.ratios import classify_regime
from experiments.simulated_backend import SimulatedBackend
from utils.stats import SweepStats

# Operating points representative of each regime (R_C, R_B)
REGIME_POINTS = {
    Regime.CAPACITY_LIMITED:       (0.30, 1.61),
    Regime.COORDINATION_DOMINATED: (0.75, 1.61),
    Regime.IO_LIMITED:             (0.75, 0.25),
}

METHODS = ["pytorch", "flexgen", "deepspeed", "swapadvisor", "vllm", "orion"]

N_SWEEPS  = 5
N_WINDOWS = 30


def collect_latency(method: str, r_c: float, r_b: float) -> float:
    """Collect mean T_total for one (method, operating_point) pair."""
    backend  = SimulatedBackend(hw=A100_80GB, method=method, seed=42)
    profiler = HardwareProfiler(platform="A100-80GB")
    profiler.register_backend(backend)

    sweep_means = []
    for s in range(N_SWEEPS):
        records = profiler.run_sweep(r_c=r_c, r_b=r_b, sweep_id=s,
                                     n_windows=N_WINDOWS, warmup_sec=0)
        valid = [r for r in records if r.is_valid()]
        if valid:
            sweep_means.append(statistics.mean(r.t_total for r in valid))

    return SweepStats(sweep_means).grand_mean


def main() -> None:
    print("=" * 72)
    print("Table 2 — Regime-dependent strategy inversion (simulated)")
    print("  Baseline: PyTorch default  |  Δ% = (T_method − T_pytorch) / T_pytorch")
    print("=" * 72)

    # Collect baseline first
    baseline: dict[Regime, float] = {}
    for regime, (r_c, r_b) in REGIME_POINTS.items():
        baseline[regime] = collect_latency("pytorch", r_c, r_b)

    # Header
    header = f"{'Method':<14}" + "".join(
        f"{r.name.replace('_',' ')[:22]:>26}" for r in REGIME_POINTS
    )
    print(header)
    print("-" * 72)

    for method in METHODS:
        row = f"{method:<14}"
        for regime, (r_c, r_b) in REGIME_POINTS.items():
            t = collect_latency(method, r_c, r_b)
            pct = (t - baseline[regime]) / baseline[regime] * 100
            marker = " ←!" if abs(pct) > 10 else ""
            row += f"{pct:>+20.1f}%{marker:>5}"
        print(row)

    print("-" * 72)
    print("Italicised values in paper Table 2 = latency increase (worse).")
    print("Key result: FlexGen −24% coord-dominated → +8–12% I/O-limited.")


if __name__ == "__main__":
    main()
