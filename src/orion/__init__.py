"""
Orion: Hierarchical Memory Orchestration for AI Inference.

Implements the regime-based framework from:
  "Hierarchical memory orchestration in AI inference exhibits
   intrinsic regime-dependent limits"
  Nature Computational Science (under review)

Key components:
  - ratios.py     : R_C, R_B computation and regime classification
  - classifier.py : depth-3 CART regime classifier (93.4% accuracy)
  - strategies.py : per-regime orchestration strategy selection
  - lower_bound.py: structural lower bound and sharpness coefficient
  - profiler.py   : latency decomposition and hardware profiling
  - orchestrator.py: main control loop (Orion_HW and Orion_Full)
  - config.py     : thresholds, hardware profiles, model specs
"""

from orion.config import (
    Regime,
    THETA_C,
    THETA_B,
    S_STAR,
    HardwareProfile,
    ModelSpec,
    A100_80GB,
    LLAMA3_8B,
)
from orion.ratios import (
    compute_rc,
    compute_rb,
    classify_regime,
    from_hardware_model,
    OperatingPoint,
)
from orion.classifier import RegimeClassifier, RuntimeFeatures
from orion.strategies import StrategyController
from orion.lower_bound import (
    compute_lower_bound,
    sharpness_coefficient,
    LowerBoundResult,
)
from orion.orchestrator import OrionOrchestrator, OrionMode

__all__ = [
    "Regime", "THETA_C", "THETA_B", "S_STAR",
    "HardwareProfile", "ModelSpec", "A100_80GB", "LLAMA3_8B",
    "compute_rc", "compute_rb", "classify_regime",
    "from_hardware_model", "OperatingPoint",
    "RegimeClassifier", "RuntimeFeatures",
    "StrategyController",
    "compute_lower_bound", "sharpness_coefficient", "LowerBoundResult",
    "OrionOrchestrator", "OrionMode",
]
