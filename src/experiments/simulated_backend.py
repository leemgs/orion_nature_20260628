"""
Simulated measurement backend for CPU-only / offline experiment reproduction.

Generates synthetic LatencyRecords that reproduce the regime-dependent
patterns reported in the paper, using the analytical model:

    T_total = T_comp + T_mem + T_swap + T_sync

Noise is drawn from a calibrated Gaussian (CV ≈ 3–5% per term)
to match the measurement variance reported in Supplementary Table B.2.

This backend allows reproducing Tables 2/3 and Figure 2 without
access to GPU hardware.  For the exact experimental numbers in the paper,
use the raw JSONL traces archived on Zenodo.
"""

from __future__ import annotations

import math
import random
import time

from orion.config import (
    THETA_C, THETA_B, Regime, HardwareProfile, A100_80GB, WINDOW_SEC,
)
from orion.profiler import LatencyRecord
from orion.ratios import classify_regime


# Regime-specific latency coefficients (calibrated on A100 80GB, Llama-3 8B)
# Format: {regime: (t_comp, t_mem, t_swap, t_sync)} in seconds per 10-s window
_REGIME_COEFFICIENTS = {
    Regime.CAPACITY_LIMITED: (
        0.12,   # T_comp: compute is not the bottleneck
        0.55,   # T_mem:  dominant — frequent eviction/reload
        0.18,   # T_swap: moderate
        0.08,   # T_sync: low (no complex coordination)
    ),
    Regime.COORDINATION_DOMINATED: (
        0.20,   # T_comp: balanced
        0.18,   # T_mem:  moderate (good residency)
        0.22,   # T_swap: moderate (overlap profitable)
        0.14,   # T_sync: significant (active coordination)
    ),
    Regime.IO_LIMITED: (
        0.10,   # T_comp: partially hidden
        0.12,   # T_mem:  low (but irrelevant — BW saturated)
        0.68,   # T_swap: dominant — PCIe saturated
        0.16,   # T_sync: amplified by DMA backpressure
    ),
}

# Baseline multiplier per orchestration method (relative to PyTorch default=1.0)
# Positive multiplier > 1 → higher latency (worse); < 1 → lower (better)
_BASELINE_MULTIPLIERS = {
    "orion":      {Regime.CAPACITY_LIMITED: 0.960, Regime.COORDINATION_DOMINATED: 0.795, Regime.IO_LIMITED: 0.895},
    "flexgen":    {Regime.CAPACITY_LIMITED: 0.985, Regime.COORDINATION_DOMINATED: 1.240, Regime.IO_LIMITED: 0.920},
    "deepspeed":  {Regime.CAPACITY_LIMITED: 0.980, Regime.COORDINATION_DOMINATED: 1.180, Regime.IO_LIMITED: 0.950},
    "swapadvisor":{Regime.CAPACITY_LIMITED: 0.995, Regime.COORDINATION_DOMINATED: 0.900, Regime.IO_LIMITED: 1.050},
    "vllm":       {Regime.CAPACITY_LIMITED: 1.010, Regime.COORDINATION_DOMINATED: 0.870, Regime.IO_LIMITED: 0.940},
    "pytorch":    {Regime.CAPACITY_LIMITED: 1.000, Regime.COORDINATION_DOMINATED: 1.000, Regime.IO_LIMITED: 1.000},
}

_CV = 0.04    # coefficient of variation for noise (≈ 4%)


class SimulatedBackend:
    """
    Simulated hardware backend for offline experiment reproduction.

    Args:
        hw:      HardwareProfile to simulate (default: A100_80GB).
        method:  Orchestration method name (used for multiplier lookup).
        seed:    RNG seed for reproducibility.
    """

    def __init__(
        self,
        hw: HardwareProfile = A100_80GB,
        method: str = "orion",
        seed: int = 42,
    ) -> None:
        self.hw     = hw
        self.method = method.lower()
        self._rng   = random.Random(seed)

    def warmup(self, warmup_sec: float = 60.0) -> None:
        """Simulate 60-s warmup (no-op in simulation)."""
        pass

    def measure(self, r_c: float, r_b: float) -> LatencyRecord:
        """Generate one synthetic 10-s LatencyRecord at (r_c, r_b)."""
        regime = classify_regime(r_c, r_b)
        coeffs = _REGIME_COEFFICIENTS[regime]
        mult   = _BASELINE_MULTIPLIERS.get(self.method, {}).get(regime, 1.0)

        def noisy(val: float) -> float:
            return max(0.0, val * mult * (1 + self._rng.gauss(0, _CV)))

        t_comp = noisy(coeffs[0])
        t_mem  = noisy(coeffs[1])
        t_swap = noisy(coeffs[2])
        t_sync = noisy(coeffs[3])
        t_wall = t_comp + t_mem + t_swap + t_sync

        # DMA utilisation: high in IO_LIMITED, moderate in coordination-dominated
        dma_util = {
            Regime.CAPACITY_LIMITED:       0.35,
            Regime.COORDINATION_DOMINATED: 0.52,
            Regime.IO_LIMITED:             0.91,
        }[regime]

        cache_hit = {
            Regime.CAPACITY_LIMITED:       0.55,
            Regime.COORDINATION_DOMINATED: 0.81,
            Regime.IO_LIMITED:             0.74,
        }[regime]

        return LatencyRecord(
            timestamp=time.time(),
            r_c=r_c, r_b=r_b,
            t_comp=t_comp, t_mem=t_mem, t_swap=t_swap, t_sync=t_sync,
            t_wall=t_wall,
            swap_to_comp_ratio=t_swap / t_comp if t_comp > 0 else 0,
            cache_hit_rate=cache_hit + self._rng.gauss(0, 0.02),
            dma_utilisation=dma_util + self._rng.gauss(0, 0.03),
        )
