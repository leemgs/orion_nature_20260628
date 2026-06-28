# Orion — Source Code

Reference implementation for:

> **"Hierarchical memory orchestration in AI inference exhibits intrinsic regime-dependent limits"**  
> *Nature Computational Science* (under review)

This directory contains the Orion measurement framework and all scripts needed to reproduce the paper's results.

---

## Directory structure

```
src/
├── orion/                      # Core Orion framework
│   ├── config.py               #   Thresholds, hardware profiles, model specs
│   ├── ratios.py               #   R_C, R_B computation & regime classification
│   ├── classifier.py           #   Depth-3 CART regime classifier (<0.1 ms)
│   ├── strategies.py           #   Per-regime orchestration strategies
│   ├── lower_bound.py          #   Structural lower bound & sharpness coefficient S
│   ├── profiler.py             #   Latency decomposition & hardware profiling
│   └── orchestrator.py         #   Main control loop (Orion_HW / Orion_Full)
├── experiments/
│   ├── simulated_backend.py    #   CPU-only synthetic backend for offline reproduction
│   ├── run_regime_sweep.py     #   Full R_C / R_B probing sweep (→ JSONL logs)
│   ├── reproduce_table2.py     #   Table 2: regime-dependent strategy inversion
│   ├── reproduce_table3.py     #   Table 3: workload generality (BLIP2/RAG/YOLOv8)
│   ├── reproduce_figure2.py    #   Figure 2: regime map + latency decomposition
│   └── reproduce_classifier_ablation.py  # Table D.1: Orion_HW vs Orion_Full
├── utils/
│   ├── stats.py                #   Bootstrap CI, Wilcoxon test, SweepStats
│   └── logging.py              #   JSONL record writer/reader
├── requirements.txt
└── setup.py
```

---

## Installation

### Prerequisites

- Python ≥ 3.9
- For **simulated reproduction** (no GPU): no additional dependencies required
- For **live GPU experiments**: CUDA 12.x, PyTorch ≥ 2.4, NVML (pynvml ≥ 11.0)

### Install (simulated mode)

```bash
cd src/
pip install -e ".[plot]"
# or without pip install:
pip install numpy scipy matplotlib
```

### Install (live GPU mode)

```bash
pip install -e ".[gpu,plot]"
# Install inference backends (as needed):
pip install vllm>=0.5.3
pip install deepspeed>=0.14
# FlexGen: follow https://github.com/FMInference/FlexGen
```

---

## Quick start — verify installation

```python
import sys; sys.path.insert(0, 'src')
from orion import from_hardware_model, A100_80GB, LLAMA3_8B

# Reproduce paper worked example (Introduction):
# Llama-3 8B at batch=8 on 80 GB HBM server
op = from_hardware_model(A100_80GB, LLAMA3_8B, delta_t_s=0.120, d_bytes=1.2e9)
print(f"R_C = {op.r_c:.2f}   (paper: 1.91)")  # 1.92
print(f"R_B = {op.r_b:.2f}   (paper: 1.61)")  # 1.61
print(f"Regime: {op.regime.name}")              # COORDINATION_DOMINATED
```

---

## Reproducing paper results

All experiments can be reproduced **without GPU** using the simulated backend.  
For exact numerical match to paper figures, use the raw JSONL traces on [Zenodo](https://doi.org/10.5281/zenodo.XXXXXXX).

### Table 2 — Regime-dependent strategy inversion

```bash
cd src/
python experiments/reproduce_table2.py
```

Expected output: FlexGen shows −24% in coordination-dominated regime but +8–12% in I/O-limited.

### Table 3 — Workload generality (BLIP2 / RAG / YOLOv8)

```bash
python experiments/reproduce_table3.py
```

### Figure 2 — Regime map and latency decomposition

```bash
# Save as PDF (requires matplotlib):
python experiments/reproduce_figure2.py --save-pdf figure2_reproduced.pdf

# Save raw CSV data (no matplotlib required):
python experiments/reproduce_figure2.py --save-csv
# → results/figure2/fig2a_rc_sweep.csv
#   results/figure2/fig2b_decomposition.csv
#   results/figure2/fig2c_rb_sweep.csv
```

### Table D.1 — Classifier ablation (Orion_HW vs Orion_Full)

```bash
python experiments/reproduce_classifier_ablation.py
```

Expected: hardware-only gain −3.8 to −8.3%; classifier adds −1.1 to −18.8% (21–76% of total).

### Full regime probing sweep

```bash
# Simulated (CPU-only, ~2 min):
python experiments/run_regime_sweep.py --mode simulate

# Live A100 hardware:
python experiments/run_regime_sweep.py --mode live --platform A100-80GB
```

Output is written to `results/regime_sweep/`:
- `sweep_XX.jsonl` — raw 10-second window records (Zenodo archive format)
- `summary.json` — boundary estimates and sharpness coefficients

---

## Running on real hardware

### A100 80 GB (primary platform)

Software requirements: PyTorch 2.4, CUDA 12.2, vLLM 0.5.3, pynvml ≥ 11.0.

```bash
python experiments/run_regime_sweep.py \
    --mode live \
    --platform A100-80GB \
    --n-sweeps 5 \
    --n-windows 30 \
    --output-dir results/a100_sweep
```

The sweep varies R_C ∈ {0.10 … 2.00} and R_B ∈ {0.10 … 2.00} (14 grid points each).  
A 60-second warm-up period precedes each operating point.  
Total runtime: approximately 5–8 hours for the full grid.

### Other platforms

| Platform | Software stack | Notes |
|----------|---------------|-------|
| Google TPU v4 | JAX 0.4.26 | Regime boundaries consistent within ±0.05 |
| AWS Inferentia2 | NeuronSDK 2.18 | θ_B error ~12.4% (proprietary interconnect) |
| AMD MI250 | ROCm 6.0 | Verified via ROCm CUPTI equivalents |
| Intel Xeon + Optane-PMem | PyTorch 2.4 | DRAM as fast tier; no GPU HBM |

Platform-specific backend adapters are not included (hardware unavailable for open release). Implement `measure(r_c, r_b) → LatencyRecord` and register via `HardwareProfiler.register_backend()`.

---

## Programmatic API

### Compute R_C, R_B from hardware and model parameters

```python
from orion import compute_rc, compute_rb, classify_regime

r_c = compute_rc(c_fast_bytes=80e9, w_bytes=41.8e9)   # 1.91
r_b = compute_rb(b_slow_bps=16.1e9, delta_t_s=0.120, d_bytes=1.2e9)  # 1.61
regime = classify_regime(r_c, r_b)                    # COORDINATION_DOMINATED
```

### Structural lower bound

```python
from orion import compute_lower_bound, A100_80GB
from orion.ratios import OperatingPoint

op = OperatingPoint(r_c=1.91, r_b=1.61, w_gb=41.8, d_gb=1.2, b_slow_gbs=16.1)
lb = compute_lower_bound(op, rho=A100_80GB.rho, t_measured_s=0.93)
print(f"Achievability τ = {lb.achievability:.2f}")   # 0.86–0.92 range
print(f"Residual (T_sync) = {lb.residual_fraction:.1%}")
```

### Runtime regime classifier

```python
from orion import RegimeClassifier, RuntimeFeatures

clf = RegimeClassifier()
# Features collected from DMA logs + CUPTI counters:
features = RuntimeFeatures(
    swap_to_comp_ratio=0.08,
    cache_hit_rate=0.82,
    dma_utilisation=0.45,
    r_c=1.91, r_b=1.61,      # pass ratios directly for highest accuracy
)
regime = clf.classify(features)
print(f"Regime: {regime.name}")
print(f"Latency: {clf.mean_latency_ms:.3f} ms")    # < 0.1 ms
```

### Regime-aware orchestrator

```python
from orion import OrionOrchestrator, OrionMode

# Orion_Full: hardware + 100-ms classifier loop
orc = OrionOrchestrator(mode=OrionMode.FULL)
orc.start()

for request in workload:
    latency = orc.infer(request, r_c=current_r_c, r_b=current_r_b)

orc.stop()
print(f"Mean latency: {orc.metrics.mean_latency_ms:.1f} ms")
print(f"Regime switches: {orc.metrics.n_regime_switches}")
```

---

## Data availability

Raw measurement logs (JSONL format, one entry per 10-second window) for all reported experiments are archived on Zenodo:

**DOI: [10.5281/zenodo.XXXXXXX](https://doi.org/10.5281/zenodo.XXXXXXX)**  
*(DOI to be confirmed upon acceptance)*

Each JSONL entry contains: `timestamp`, `r_c`, `r_b`, `t_comp`, `t_mem`, `t_swap`, `t_sync`, `t_wall`, `platform`, `model`, `sweep_id`, `window_id`.

Load with the provided utility:

```python
from utils.logging import load_jsonl
records = list(load_jsonl("path/to/sweep_00.jsonl"))
```

---

## Reproducing sharpness coefficient S

```python
from orion.lower_bound import sharpness_coefficient

# T_total measurements across R_C grid near θ_C = 0.50
t_values = [0.95, 0.93, 0.92, 0.88, 0.72, 0.54, 0.52, 0.51]
r_values = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
S = sharpness_coefficient(t_values, r_values)
print(f"S = {S:.2f}   (paper: 4.12 at θ_C, S* = 2.0)")
```

---

## Statistical tests

```python
from utils.stats import bootstrap_ci, wilcoxon_one_sided, SweepStats

# Aggregate across 5 sweeps
stats = SweepStats(sweep_means=[0.93, 0.91, 0.94, 0.92, 0.93])
print(stats)
# SweepStats(mean=0.9260, 95% CI=[0.9100, 0.9400], n_eff≈150)

# Wilcoxon test: H0: S ≤ S* = 2.0
s_estimates = [4.05, 4.12, 3.98, 4.18, 4.09]
p = wilcoxon_one_sided(s_estimates, null_value=2.0)
print(f"p = {p:.4f}   (paper: p < 0.05 near boundaries)")
```

---

## Plotting (Figure 2)

```bash
# Interactive:
python experiments/reproduce_figure2.py

# PDF at 300 DPI:
python experiments/reproduce_figure2.py --save-pdf fig2.pdf
```

For custom plots, export CSV and use your preferred tool:

```bash
python experiments/reproduce_figure2.py --save-csv
# Files: results/figure2/fig2a_rc_sweep.csv
#        results/figure2/fig2b_decomposition.csv
#        results/figure2/fig2c_rb_sweep.csv
```

---

## Citation

```bibtex
@article{orion2026nature,
  title   = {Hierarchical memory orchestration in {AI} inference exhibits
             intrinsic regime-dependent limits},
  author  = {Lim, Geunsik and others},
  journal = {Nature Computational Science},
  year    = {2026},
  note    = {Under review},
}
```
