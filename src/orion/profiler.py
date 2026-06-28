"""
Hardware profiling and latency decomposition (Methods §Measurement protocol).

Provides:
  - LatencyRecord: one 10-s measurement window (T_comp, T_mem, T_swap, T_sync)
  - HardwareProfiler: collects records from CUDA/NVML/CUPTI sources
  - BandwidthThrottle: software token-bucket rate-limiter for R_B sweeps
  - validate_completeness: checks |T_wall - Σ T_i| ≤ 3%

In production, T_comp is isolated via asynchronous CUDA events;
T_mem derives from CUPTI HBM counters; T_swap from DMA transfer logs;
T_sync from cudaStreamSynchronize / ncclAllReduce wrappers.

This module provides the data-structure layer and a simulation-mode
fallback for environments without CUDA/CUPTI (e.g., CPU-only CI).
"""

from __future__ import annotations

import json
import math
import time
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Iterator

from orion.config import (
    COMPLETENESS_TOL, WINDOW_SEC, WARMUP_SEC, N_WINDOWS, N_SWEEPS,
)


@dataclass
class LatencyRecord:
    """
    One 10-s measurement window at a fixed (R_C, R_B) operating point.
    All times in seconds.
    """
    timestamp:   float    # wall-clock epoch when window started
    r_c:         float    # operating R_C for this window
    r_b:         float    # operating R_B for this window
    t_comp:      float    # accelerator computation time [s]
    t_mem:       float    # locality-driven memory-access cost [s]
    t_swap:      float    # cross-tier DMA transfer time [s]
    t_sync:      float    # synchronisation / coordination overhead [s]
    t_wall:      float    # wall-clock total latency [s]
    # Derived
    swap_to_comp_ratio: float = 0.0
    cache_hit_rate:     float = 0.0
    dma_utilisation:    float = 0.0
    # Metadata
    platform: str = ""
    model:    str = ""
    sweep_id: int = 0
    window_id: int = 0

    def __post_init__(self) -> None:
        if self.t_comp > 0:
            self.swap_to_comp_ratio = self.t_swap / self.t_comp

    @property
    def t_total(self) -> float:
        return self.t_comp + self.t_mem + self.t_swap + self.t_sync

    @property
    def completeness_error(self) -> float:
        """Fractional deviation: |T_wall - Σ T_i| / T_wall."""
        if self.t_wall <= 0:
            return 0.0
        return abs(self.t_wall - self.t_total) / self.t_wall

    def is_valid(self) -> bool:
        return self.completeness_error <= COMPLETENESS_TOL

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self))


def validate_completeness(records: list[LatencyRecord],
                           tol: float = COMPLETENESS_TOL) -> tuple[bool, float]:
    """
    Check that |T_wall - Σ T_i| / T_wall ≤ tol for all records.

    Returns:
        (all_valid, mean_error_fraction)
    """
    errors = [r.completeness_error for r in records]
    mean_err = sum(errors) / len(errors) if errors else 0.0
    return all(e <= tol for e in errors), mean_err


class BandwidthThrottle:
    """
    Software token-bucket rate-limiter for PCIe bandwidth control (Methods §).

    Each cuMemcpyHtoDAsync call acquires tokens proportional to the transfer
    size.  The bucket refills at `target_bps` bytes per second.
    A counting semaphore caps outstanding transfer bytes per `window_ms`.

    In simulation mode (no CUDA), only the accounting logic is active.
    """

    def __init__(self, target_bps: float, window_ms: float = 10.0) -> None:
        if target_bps <= 0:
            raise ValueError("target_bps must be positive.")
        self.target_bps = target_bps
        self.window_ms  = window_ms
        self._bucket_cap = target_bps * (window_ms / 1000.0)
        self._tokens     = self._bucket_cap
        self._lock       = threading.Lock()
        self._last_refill = time.perf_counter()

    def acquire(self, n_bytes: int) -> None:
        """Block until n_bytes tokens are available (throttles transfer rate)."""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= n_bytes:
                    self._tokens -= n_bytes
                    return
            time.sleep(self.window_ms / 1000.0 / 10)

    def _refill(self) -> None:
        now = time.perf_counter()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._bucket_cap,
            self._tokens + self.target_bps * elapsed,
        )
        self._last_refill = now


class HardwareProfiler:
    """
    Collects LatencyRecords over a regime probing sweep.

    In a real deployment:
      - T_comp: CUDA events around matmul kernel batch
      - T_mem:  CUPTI nvmlDeviceGetPcieThroughput + L2-miss volume
      - T_swap: DMA transfer log timestamps
      - T_sync: cudaStreamSynchronize / ncclAllReduce wrappers

    This class provides the interface; backends are injected via
    `register_backend()`.  A SimulatedBackend is provided for
    offline / CPU-only reproduction.
    """

    def __init__(
        self,
        platform: str = "simulated",
        output_dir: Optional[Path] = None,
    ) -> None:
        self.platform = platform
        self.output_dir = output_dir
        self._backend = None
        self._records: list[LatencyRecord] = []

    def register_backend(self, backend) -> None:
        """Inject a measurement backend (CUDA, ROCm, TPU, or Simulated)."""
        self._backend = backend

    def collect_window(
        self,
        r_c: float,
        r_b: float,
        model: str = "",
        sweep_id: int = 0,
        window_id: int = 0,
    ) -> LatencyRecord:
        """Collect one 10-s measurement window at the given operating point."""
        if self._backend is None:
            raise RuntimeError(
                "No measurement backend registered. "
                "Call register_backend(SimulatedBackend(...)) for offline use."
            )
        record = self._backend.measure(r_c, r_b)
        record.platform = self.platform
        record.model    = model
        record.sweep_id = sweep_id
        record.window_id = window_id
        self._records.append(record)

        if self.output_dir is not None:
            log_path = self.output_dir / f"sweep_{sweep_id:02d}.jsonl"
            with open(log_path, "a") as f:
                f.write(record.to_jsonl() + "\n")

        return record

    def run_sweep(
        self,
        r_c: float,
        r_b: float,
        model: str = "",
        sweep_id: int = 0,
        n_windows: int = N_WINDOWS,
        warmup_sec: float = WARMUP_SEC,
    ) -> list[LatencyRecord]:
        """
        Run one full probing sweep: warmup → n_windows measurement windows.
        """
        if warmup_sec > 0 and self._backend is not None:
            self._backend.warmup(warmup_sec)

        sweep_records = []
        for w in range(n_windows):
            rec = self.collect_window(r_c, r_b, model=model,
                                      sweep_id=sweep_id, window_id=w)
            sweep_records.append(rec)
        return sweep_records

    @property
    def records(self) -> list[LatencyRecord]:
        return list(self._records)

    def save_jsonl(self, path: Path) -> None:
        """Dump all collected records to a JSONL file (Zenodo archive format)."""
        with open(path, "w") as f:
            for rec in self._records:
                f.write(rec.to_jsonl() + "\n")
