"""
Statistical utilities (Methods §Measurement protocol).

  bootstrap_ci:       95% confidence interval via bootstrap resampling
                      (1,000 replicates, window-within-sweep sampling)
  wilcoxon_one_sided: H0: S ≤ S* = 2.0 (one-sided signed-rank test)
  SweepStats:         aggregate sweep-level estimates across 5 sweeps
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable, Sequence


def bootstrap_ci(
    data: Sequence[float],
    statistic: Callable[[list[float]], float] = statistics.mean,
    n_replicates: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Bootstrap confidence interval.

    Args:
        data:         Sample of scalar measurements.
        statistic:    Function to estimate (default: mean).
        n_replicates: Number of bootstrap draws.
        confidence:   Coverage probability (default 0.95 → 95% CI).
        seed:         RNG seed for reproducibility.

    Returns:
        (point_estimate, lower_bound, upper_bound)
    """
    rng = random.Random(seed)
    n = len(data)
    if n == 0:
        raise ValueError("data must be non-empty.")

    point = statistic(list(data))
    replicates = []
    for _ in range(n_replicates):
        resample = [rng.choice(data) for _ in range(n)]
        replicates.append(statistic(resample))

    replicates.sort()
    alpha = 1.0 - confidence
    lo = replicates[int(alpha / 2 * n_replicates)]
    hi = replicates[int((1 - alpha / 2) * n_replicates)]
    return point, lo, hi


def wilcoxon_one_sided(
    s_values: Sequence[float],
    null_value: float = 2.0,
) -> float:
    """
    One-sided Wilcoxon signed-rank test.
    H0: median(S) ≤ null_value
    H1: median(S) > null_value  (right-tailed)

    Used to confirm S > S* = 2.0 near regime boundaries (Methods §).
    Returns approximate p-value via normal approximation (valid for n ≥ 5).

    Near-boundary regime conditions in the paper yield p < 0.05;
    interior conditions yield p > 0.40.
    """
    differences = [s - null_value for s in s_values]
    nonzero = [(abs(d), math.copysign(1, d)) for d in differences if d != 0]
    n = len(nonzero)
    if n == 0:
        return 0.5

    sorted_by_rank = sorted(nonzero, key=lambda x: x[0])
    w_plus = sum(
        (i + 1) for i, (_, sign) in enumerate(sorted_by_rank) if sign > 0
    )

    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if sigma == 0:
        return 0.5

    z = (w_plus - mu) / sigma
    # Normal CDF for right tail: P(Z > z) ≈ 1 - Φ(z)
    p = 0.5 * math.erfc(z / math.sqrt(2))
    return p


@dataclass
class SweepStats:
    """
    Aggregate statistics across n_sweeps = 5 independent probing sweeps.

    Each sweep contributes one mean latency estimate.
    The grand estimate and 95% CI are computed over the sweep-level means
    (bootstrap, 1,000 replicates).
    """
    sweep_means: list[float]

    @property
    def grand_mean(self) -> float:
        return statistics.mean(self.sweep_means)

    @property
    def std(self) -> float:
        return statistics.stdev(self.sweep_means) if len(self.sweep_means) > 1 else 0.0

    @property
    def ci95(self) -> tuple[float, float]:
        _, lo, hi = bootstrap_ci(self.sweep_means)
        return lo, hi

    @property
    def n_eff(self) -> int:
        """Effective sample size ≈ 150 per condition (5 sweeps × 30 windows)."""
        return len(self.sweep_means) * 30

    def __repr__(self) -> str:
        lo, hi = self.ci95
        return (f"SweepStats(mean={self.grand_mean:.4f}, "
                f"95% CI=[{lo:.4f}, {hi:.4f}], "
                f"n_eff≈{self.n_eff})")
