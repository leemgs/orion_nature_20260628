"""
Orion orchestrator: main control loop integrating classifier + strategy.

Orion_HW  = NUMA binding + process pinning + GPU-tailored swapping (hardware only)
Orion_Full = Orion_HW + 100-ms regime classifier loop + adaptive strategy switching

The classifier contributes 21–76% of total latency improvement over baseline
(Table D.1, Supplementary §D).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from orion.classifier import RegimeClassifier, RuntimeFeatures
from orion.config import Regime
from orion.strategies import StrategyController, StrategyConfig

logger = logging.getLogger(__name__)


class OrionMode(Enum):
    HW_ONLY  = auto()   # Orion_HW: NUMA + PCIe, fixed strategy
    FULL     = auto()   # Orion_Full: + classifier loop


@dataclass
class OrionMetrics:
    """Accumulated runtime metrics for one inference session."""
    n_requests: int = 0
    n_regime_switches: int = 0
    total_latency_s: float = 0.0
    total_energy_j: float = 0.0
    regime_counts: dict[str, int] = field(
        default_factory=lambda: {r.name: 0 for r in Regime}
    )
    classifier_latency_ms: list[float] = field(default_factory=list)

    @property
    def mean_latency_ms(self) -> float:
        if self.n_requests == 0:
            return 0.0
        return (self.total_latency_s / self.n_requests) * 1000

    @property
    def throughput_per_watt(self) -> float:
        if self.total_energy_j <= 0:
            return 0.0
        return self.n_requests / self.total_energy_j


class OrionOrchestrator:
    """
    Orion measurement and orchestration framework.

    The orchestrator wraps model inference with:
      1. Pre-inference: classify operating regime (Orion_Full only)
      2. Apply per-regime strategy (tensor placement, swap granularity, etc.)
      3. Execute inference (delegated to model backend)
      4. Post-inference: record latency decomposition

    Usage::

        orc = OrionOrchestrator(mode=OrionMode.FULL)
        orc.start()
        for request in workload:
            latency = orc.infer(request)
        orc.stop()
        print(orc.metrics)
    """

    CLASSIFIER_INTERVAL_S = 0.10   # 100 ms classifier loop

    def __init__(
        self,
        mode: OrionMode = OrionMode.FULL,
        profiler=None,
        model_backend=None,
    ) -> None:
        self.mode           = mode
        self.profiler       = profiler
        self.model_backend  = model_backend

        self._classifier    = RegimeClassifier()
        self._strategy_ctrl = StrategyController()
        self._metrics       = OrionMetrics()

        self._running       = False
        self._clf_thread: Optional[threading.Thread] = None
        self._current_regime: Regime = Regime.COORDINATION_DOMINATED
        self._current_strategy: Optional[StrategyConfig] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the orchestrator (and classifier loop for FULL mode)."""
        self._running = True
        if self.mode == OrionMode.FULL:
            self._clf_thread = threading.Thread(
                target=self._classifier_loop, daemon=True
            )
            self._clf_thread.start()
            logger.info("Orion_Full started (classifier interval=%s ms)",
                        self.CLASSIFIER_INTERVAL_S * 1000)
        else:
            logger.info("Orion_HW started (fixed strategy, no classifier loop)")

    def stop(self) -> None:
        """Gracefully stop the orchestrator."""
        self._running = False
        if self._clf_thread is not None:
            self._clf_thread.join(timeout=2.0)
        logger.info("Orion stopped. Metrics: %s", self._metrics)

    # ------------------------------------------------------------------ #
    # Inference entry point
    # ------------------------------------------------------------------ #

    def infer(self, request, r_c: float, r_b: float) -> float:
        """
        Run one inference request under regime-aware orchestration.

        Args:
            request: Model input (passed through to model_backend).
            r_c:     Current operating R_C (from memory tracker).
            r_b:     Current operating R_B (from DMA log).

        Returns:
            Wall-clock latency for this request [seconds].
        """
        # HW_ONLY: classify analytically once per request (no loop overhead)
        if self.mode == OrionMode.HW_ONLY:
            features = RuntimeFeatures(
                swap_to_comp_ratio=0.0,
                cache_hit_rate=0.0,
                dma_utilisation=0.0,
                r_c=r_c,
                r_b=r_b,
            )
            regime = self._classifier.classify(features)
            strategy, _ = self._strategy_ctrl.update(regime)
        else:
            # FULL: classifier loop updates _current_regime asynchronously
            strategy, _ = self._strategy_ctrl.update(self._current_regime)

        self._apply_strategy(strategy)

        t0 = time.perf_counter()
        if self.model_backend is not None:
            self.model_backend.run(request, strategy=strategy)
        t_wall = time.perf_counter() - t0

        self._record_request(t_wall, strategy.regime)
        return t_wall

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _classifier_loop(self) -> None:
        """Background thread: classify every 100 ms (Orion_Full mode)."""
        while self._running:
            loop_start = time.perf_counter()

            if self.profiler is not None:
                features = self._extract_features()
                regime = self._classifier.classify(features)
                self._current_regime = regime
                self._metrics.classifier_latency_ms.append(
                    self._classifier.mean_latency_ms
                )

            elapsed = time.perf_counter() - loop_start
            sleep = max(0.0, self.CLASSIFIER_INTERVAL_S - elapsed)
            time.sleep(sleep)

    def _extract_features(self) -> RuntimeFeatures:
        """Pull latest stats from profiler for classifier input."""
        records = self.profiler.records
        if not records:
            return RuntimeFeatures(
                swap_to_comp_ratio=0.0,
                cache_hit_rate=0.8,
                dma_utilisation=0.4,
            )
        last = records[-1]
        return RuntimeFeatures(
            swap_to_comp_ratio=last.swap_to_comp_ratio,
            cache_hit_rate=last.cache_hit_rate,
            dma_utilisation=last.dma_utilisation,
            r_c=last.r_c,
            r_b=last.r_b,
        )

    def _apply_strategy(self, strategy: StrategyConfig) -> None:
        """Apply strategy knobs to the underlying memory manager."""
        # In a real deployment: adjust NUMA bindings, DMA prefetch depth,
        # sync mode, swap granularity via CUDA/ROCm APIs.
        if self._current_strategy != strategy:
            logger.debug("Strategy applied: %s", strategy.description)
            self._current_strategy = strategy

    def _record_request(self, t_wall: float, regime: Regime) -> None:
        self._metrics.n_requests += 1
        self._metrics.total_latency_s += t_wall
        self._metrics.regime_counts[regime.name] += 1
        self._metrics.n_regime_switches = self._strategy_ctrl.switch_count

    @property
    def metrics(self) -> OrionMetrics:
        return self._metrics

    @property
    def current_regime(self) -> Regime:
        return self._current_regime
