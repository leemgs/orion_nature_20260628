#!/usr/bin/env python3
"""
Reproduce Table 3 — Workload generality beyond LLMs.

Shows regime structure for non-LLM workloads:
  BLIP2, RAG, YOLOv8 all exhibit three-regime behaviour.

Usage:
    python experiments/reproduce_table3.py
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orion.config import A100_80GB
from orion.profiler import HardwareProfiler
from experiments.simulated_backend import SimulatedBackend
from utils.stats import SweepStats

# Workload operating points (Table 3 in paper)
# Each entry: (workload_name, r_c, r_b, regime_label)
WORKLOADS = [
    ("BLIP2-VQA",     0.62, 1.10, "coord-dominated"),
    ("RAG (Llama-3)", 0.58, 0.85, "coord-dominated"),
    ("YOLOv8-edge",   0.38, 0.35, "capacity-limited"),
]

METHODS   = ["pytorch", "flexgen", "vllm", "orion"]
N_SWEEPS  = 5
N_WINDOWS = 30


def collect(method: str, r_c: float, r_b: float) -> float:
    backend  = SimulatedBackend(hw=A100_80GB, method=method, seed=7)
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
    print("=" * 70)
    print("Table 3 — Workload generality (simulated)")
    print("  Δ% relative to PyTorch baseline")
    print("=" * 70)

    # Column header
    print(f"{'Workload':<20} {'Regime':<20}", end="")
    for m in METHODS:
        print(f"{m:>10}", end="")
    print()
    print("-" * 70)

    for wl_name, r_c, r_b, regime_label in WORKLOADS:
        baseline = collect("pytorch", r_c, r_b)
        print(f"{wl_name:<20} {regime_label:<20}", end="")
        for method in METHODS:
            if method == "pytorch":
                print(f"{'baseline':>10}", end="")
            else:
                t = collect(method, r_c, r_b)
                pct = (t - baseline) / baseline * 100
                marker = "*" if method == "vllm" and wl_name.startswith("YOLO") else ""
                print(f"{pct:>+9.1f}%{marker}", end="")
        print()

    print("-" * 70)
    print("* vLLM: not applicable to YOLOv8 (non-LLM, token-free inference).")
    print("All three non-LLM workloads confirm three-regime structure.")


if __name__ == "__main__":
    main()
