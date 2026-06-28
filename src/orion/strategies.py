"""
Per-regime orchestration strategies (Discussion §Practical regime-aware inference).

Each strategy is triggered by the RegimeClassifier and adjusts:
  - tensor placement (HBM vs. host DRAM)
  - swap granularity
  - prefetch aggressiveness
  - synchronisation mode

Latency improvement ranges from Table 2 (regime_inversion):
  CAPACITY_LIMITED:      hardware only;  ≤ 5% gain from coordination
  COORDINATION_DOMINATED: 18–27% gain from full orchestration
  IO_LIMITED:            8–12% *degradation* from aggressive offloading;
                         correct intervention: reduce D, not add coordination
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from orion.config import Regime

logger = logging.getLogger(__name__)


class SwapGranularity(Enum):
    LAYER      = auto()   # offload / reload one transformer layer at a time
    BLOCK      = auto()   # sub-layer tensor block (coarser)
    TENSOR     = auto()   # individual tensor (finest; default)


@dataclass
class StrategyConfig:
    """Orchestration knobs for one regime."""
    regime: Regime
    # Tensor placement
    hbm_fraction: float               # fraction of W to keep in HBM [0, 1]
    swap_granularity: SwapGranularity
    # Prefetch
    prefetch_layers_ahead: int        # how many layers to prefetch during fwd pass
    overlap_compute_transfer: bool    # pipeline DMA with matmul kernels
    # Synchronisation
    sync_mode: str                    # "eager" | "lazy" | "barrier-free"
    # NUMA binding
    numa_bind: bool
    # Description for logging
    description: str = ""


# Reference strategy configurations
STRATEGY_CAPACITY_LIMITED = StrategyConfig(
    regime=Regime.CAPACITY_LIMITED,
    hbm_fraction=1.0,               # keep everything possible in HBM
    swap_granularity=SwapGranularity.LAYER,
    prefetch_layers_ahead=0,        # no prefetch; locality dominates
    overlap_compute_transfer=False,
    sync_mode="eager",
    numa_bind=True,
    description=(
        "Capacity-limited: maximise HBM residency. "
        "NUMA binding + process pinning provide ≤5% gain; "
        "coordination overhead has negligible return."
    ),
)

STRATEGY_COORDINATION_DOMINATED = StrategyConfig(
    regime=Regime.COORDINATION_DOMINATED,
    hbm_fraction=0.75,              # partial offload; overlap is profitable
    swap_granularity=SwapGranularity.TENSOR,
    prefetch_layers_ahead=2,        # 2-layer look-ahead for HBM prefetch
    overlap_compute_transfer=True,  # pipeline DMA with computation
    sync_mode="lazy",               # defer barriers to reduce sync stalls
    numa_bind=True,
    description=(
        "Coordination-dominated: full orchestration profitable. "
        "Pipelining + KV-cache management + overlap yield 18–27% latency reduction."
    ),
)

STRATEGY_IO_LIMITED = StrategyConfig(
    regime=Regime.IO_LIMITED,
    hbm_fraction=1.0,               # minimise D: keep as much as possible in HBM
    swap_granularity=SwapGranularity.LAYER,
    prefetch_layers_ahead=0,        # prefetch amplifies already-saturated PCIe
    overlap_compute_transfer=False, # overlap adds scheduling overhead when BW saturated
    sync_mode="barrier-free",
    numa_bind=True,
    description=(
        "I/O-limited: reduce transfer volume D, not scheduling complexity. "
        "Aggressive offloading (FlexGen, DeepSpeed) worsens latency by 8–12%."
    ),
)

_STRATEGY_MAP: dict[Regime, StrategyConfig] = {
    Regime.CAPACITY_LIMITED:       STRATEGY_CAPACITY_LIMITED,
    Regime.COORDINATION_DOMINATED: STRATEGY_COORDINATION_DOMINATED,
    Regime.IO_LIMITED:             STRATEGY_IO_LIMITED,
}


class StrategyController:
    """
    Applies and monitors regime-aware orchestration strategy.

    Called by the Orchestrator each time the RegimeClassifier outputs
    a (potentially new) regime label.
    """

    def __init__(self) -> None:
        self._current: Optional[StrategyConfig] = None
        self._switch_count: int = 0

    def update(self, regime: Regime) -> tuple[StrategyConfig, bool]:
        """
        Return the strategy for the given regime and whether it changed.

        Args:
            regime: Current regime from RegimeClassifier.

        Returns:
            (strategy_config, switched) where switched=True on regime change.
        """
        new_strategy = _STRATEGY_MAP[regime]
        switched = (self._current is None or
                    self._current.regime != new_strategy.regime)
        if switched:
            if self._current is not None:
                logger.info(
                    "Regime switch: %s → %s",
                    self._current.regime.name,
                    new_strategy.regime.name,
                )
            self._current = new_strategy
            self._switch_count += 1
        return new_strategy, switched

    @property
    def current_strategy(self) -> Optional[StrategyConfig]:
        return self._current

    @property
    def switch_count(self) -> int:
        return self._switch_count
