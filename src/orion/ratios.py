"""
Dimensionless control ratios R_C and R_B (Eq. 2 in paper).

R_C = C_fast / W
    Measures how much of the active working set fits in fast memory.
    R_C ≥ 1 → fully resident; R_C < θ_C → capacity-limited regime.

R_B = B_slow * Δt / D
    Measures the fraction of sustained transfer demand that available
    bandwidth can serve over one inference step.
    R_B < θ_B → I/O-limited regime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from orion.config import (
    THETA_C, THETA_B, Regime, HardwareProfile, ModelSpec,
)


@dataclass
class OperatingPoint:
    """A fully characterised (R_C, R_B) operating point."""
    r_c: float            # fast-memory residency ratio
    r_b: float            # transfer-pressure ratio
    # Raw quantities (optional, for book-keeping)
    c_fast_gb: float = 0.0
    w_gb: float      = 0.0
    b_slow_gbs: float = 0.0
    delta_t_s: float  = 0.0
    d_gb: float       = 0.0

    @property
    def regime(self) -> Regime:
        return classify_regime(self.r_c, self.r_b)

    def __repr__(self) -> str:
        return (f"OperatingPoint(R_C={self.r_c:.3f}, R_B={self.r_b:.3f}, "
                f"regime={self.regime.name})")


def compute_rc(c_fast_bytes: float, w_bytes: float) -> float:
    """
    R_C = C_fast / W

    Args:
        c_fast_bytes: Fast-memory (HBM) capacity in bytes actually available
                      to the model (after OS/framework overhead).
        w_bytes:      Active working-set size W = W_param + W_act + W_kv.

    Returns:
        Dimensionless residency ratio.  > 1 means fully resident.
    """
    if w_bytes <= 0:
        raise ValueError("Working-set size W must be positive.")
    return c_fast_bytes / w_bytes


def compute_rb(b_slow_bps: float, delta_t_s: float, d_bytes: float) -> float:
    """
    R_B = B_slow * Δt / D

    Args:
        b_slow_bps:  Sustained host-to-device bandwidth [bytes/s], measured
                     via NVML nvmlDeviceGetPcieThroughput over a 10-s window.
        delta_t_s:   Mean inference-step wall-clock duration [seconds].
        d_bytes:     Compulsory data volume transferred per step [bytes],
                     derived from DMA transfer logs.

    Returns:
        Dimensionless transfer-pressure ratio.  > 1 means bandwidth surplus.
    """
    if d_bytes <= 0:
        raise ValueError("Transfer volume D must be positive.")
    return (b_slow_bps * delta_t_s) / d_bytes


def classify_regime(r_c: float, r_b: float,
                    theta_c: float = THETA_C,
                    theta_b: float = THETA_B) -> Regime:
    """
    Depth-3 regime decision tree (Figure in Supplementary, §A classifier).

    Decision logic (mirrors the trained CART tree, 93.4% accuracy):
        if R_C < θ_C  →  CAPACITY_LIMITED
        elif R_B < θ_B →  IO_LIMITED
        else           →  COORDINATION_DOMINATED
    """
    if r_c < theta_c:
        return Regime.CAPACITY_LIMITED
    if r_b < theta_b:
        return Regime.IO_LIMITED
    return Regime.COORDINATION_DOMINATED


def from_hardware_model(
    hw: HardwareProfile,
    model: ModelSpec,
    delta_t_s: float,
    d_bytes: Optional[float] = None,
    c_fast_fraction: float = 1.0,
) -> OperatingPoint:
    """
    Construct an OperatingPoint from hardware + model descriptors.

    Args:
        hw:               HardwareProfile for the target platform.
        model:            ModelSpec for the deployed model.
        delta_t_s:        Measured mean step duration [s].
        d_bytes:          Compulsory DMA transfer volume per step [bytes].
                          If None, estimated as max(0, W - C_fast).
        c_fast_fraction:  Fraction of hw.c_fast_bytes made available
                          (default 1.0; reduce to simulate HBM constraints).
    """
    c_fast = hw.c_fast_bytes * c_fast_fraction
    w = model.w_total_bytes

    if d_bytes is None:
        # Conservative lower estimate: eviction volume when W > C_fast
        d_bytes = max(0.0, w - c_fast)
        if d_bytes == 0:
            d_bytes = 0.01 * w   # compulsory minimum even when fully resident

    r_c = compute_rc(c_fast, w)
    r_b = compute_rb(hw.b_slow_bps, delta_t_s, d_bytes)

    return OperatingPoint(
        r_c=r_c, r_b=r_b,
        c_fast_gb=c_fast / 1e9,
        w_gb=w / 1e9,
        b_slow_gbs=hw.b_slow_gbs,
        delta_t_s=delta_t_s,
        d_gb=d_bytes / 1e9,
    )


def predict_theta_b(hw: HardwareProfile,
                    r_b_sat: Optional[float] = None) -> float:
    """
    Closed-form θ_B prediction (Supplementary §A.7, Eq. thetaB_pred).

        θ_B = R_B_sat × (1 + α_wb + α_q)

    R_B_sat is the empirically measured R_B at which PCIe link reaches
    sustained saturation (~0.33 for A100 PCIe Gen4; estimated as
    0.33 if not provided).

    Mean prediction error: ≤ 4.7% on PCIe-based platforms;
    larger for proprietary interconnects (e.g., Inferentia2: ~12.4%).
    """
    if r_b_sat is None:
        # Default calibrated from A100 PCIe Gen4
        r_b_sat = 0.33
    return r_b_sat * (1.0 + hw.alpha_wb + hw.alpha_q)
