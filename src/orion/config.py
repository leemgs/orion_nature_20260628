"""
Orion configuration constants.

Regime thresholds and physical constants derived from the paper:
  θ_C = 0.50  (majority-eviction threshold, hardware-independent)
  θ_B = 0.40  (I/O saturation threshold, PCIe-calibrated)
  S*  = 2.0   (sharpness criterion for abrupt transition)
"""

from dataclasses import dataclass, field
from enum import Enum, auto


class Regime(Enum):
    CAPACITY_LIMITED     = auto()   # R_C < θ_C
    COORDINATION_DOMINATED = auto() # R_C ≥ θ_C and R_B ≥ θ_B
    IO_LIMITED           = auto()   # R_B < θ_B


THETA_C: float = 0.50   # fast-memory residency threshold
THETA_B: float = 0.40   # transfer-pressure threshold
S_STAR:  float = 2.0    # sharpness criterion (|d ln T / d ln R|)

# Measurement protocol constants (Methods §)
N_SWEEPS       = 5      # independent probing sweeps per condition
N_WINDOWS      = 30     # measurement windows per sweep (each 10 s)
WINDOW_SEC     = 10.0   # seconds per measurement window
WARMUP_SEC     = 60.0   # warm-up period discarded before each sweep
BOOTSTRAP_REPS = 1000   # bootstrap replicates for 95% CI

# Bandwidth throttle: token-bucket window
RATE_LIMIT_WINDOW_MS = 10  # ms

# Clock deviation gate (NVML): discard window if GPU clock deviates > 5%
CLOCK_DEVIATION_GATE = 0.05

# Measurement completeness target: |T_wall - Σ T_i| ≤ 3%
COMPLETENESS_TOL = 0.03


@dataclass
class HardwareProfile:
    """Per-platform hardware constants for Orion."""
    name: str
    c_fast_gb: float          # fast-memory capacity (GB), e.g. HBM
    b_slow_gbs: float         # sustained PCIe host-to-device bandwidth (GB/s)
    rho: float                # HBM miss-penalty per byte (s/byte)
    # Optional amplification factors for θ_B prediction
    alpha_wb: float = 0.10    # write-back amplification
    alpha_q: float  = 0.05    # quantisation-overhead amplification

    @property
    def c_fast_bytes(self) -> float:
        return self.c_fast_gb * 1e9

    @property
    def b_slow_bps(self) -> float:
        return self.b_slow_gbs * 1e9


# Reference hardware profiles (Table in Supplementary)
A100_80GB = HardwareProfile(
    name="A100-80GB",
    c_fast_gb=80.0,
    b_slow_gbs=16.1,   # PCIe Gen4 x16
    rho=2.5e-11,        # ~25 ps/byte HBM miss penalty
    alpha_wb=0.11,
    alpha_q=0.04,
)

TPU_V4 = HardwareProfile(
    name="TPU-v4",
    c_fast_gb=32.0,
    b_slow_gbs=19.2,
    rho=2.0e-11,
    alpha_wb=0.09,
    alpha_q=0.05,
)

INFERENTIA2 = HardwareProfile(
    name="Inferentia2",
    c_fast_gb=32.0,
    b_slow_gbs=12.0,   # proprietary Neuron-to-host link
    rho=3.1e-11,
    alpha_wb=0.14,
    alpha_q=0.06,
)

MI250 = HardwareProfile(
    name="MI250",
    c_fast_gb=128.0,
    b_slow_gbs=15.0,
    rho=2.3e-11,
    alpha_wb=0.10,
    alpha_q=0.04,
)

OPTANE_PMEM = HardwareProfile(
    name="Xeon-OptanePMem",
    c_fast_gb=0.0,      # no dedicated GPU HBM; uses DRAM as fast tier
    b_slow_gbs=6.4,     # Optane PMem read bandwidth
    rho=5.0e-11,
    alpha_wb=0.18,
    alpha_q=0.07,
)

ALL_PLATFORMS = [A100_80GB, TPU_V4, INFERENTIA2, MI250, OPTANE_PMEM]


@dataclass
class ModelSpec:
    """Working-set size decomposition for a model (Eq. in Methods)."""
    name: str
    w_param_gb: float       # parameter footprint (fp16)
    # Activation peak: B * L_layers * 4 * d_model * s_dtype (bytes)
    batch: int
    seq_len: int
    n_layers: int
    d_model: int
    dtype_bytes: int = 2    # fp16
    # KV cache: 2 * B * L * H * d_h * seq * dtype
    n_heads: int = 0
    d_head: int  = 0

    @property
    def w_act_gb(self) -> float:
        # W_act = B * ℓ * L * 4 * d_model * s_dtype  (Methods §Working-set size)
        return (self.batch * self.seq_len * self.n_layers * 4
                * self.d_model * self.dtype_bytes) / 1e9

    @property
    def w_kv_gb(self) -> float:
        if self.n_heads == 0:
            return 0.0
        return (2 * self.batch * self.n_layers * self.n_heads * self.d_head
                * self.seq_len * self.dtype_bytes) / 1e9

    @property
    def w_total_gb(self) -> float:
        return self.w_param_gb + self.w_act_gb + self.w_kv_gb

    @property
    def w_total_bytes(self) -> float:
        return self.w_total_gb * 1e9


# Reference model specs (Supplementary Table W_models)
LLAMA3_8B = ModelSpec(
    name="Llama-3-8B",
    w_param_gb=16.0,     # BF16
    batch=8, seq_len=2048, n_layers=32, d_model=4096, n_heads=32, d_head=128,
)

GPTJ_6B = ModelSpec(
    name="GPT-J-6B",
    w_param_gb=12.0,
    batch=8, seq_len=2048, n_layers=28, d_model=4096, n_heads=16, d_head=256,
)

LLAMA4_17B = ModelSpec(
    name="Llama-4-17B",
    w_param_gb=34.0,
    batch=8, seq_len=2048, n_layers=48, d_model=5120, n_heads=40, d_head=128,
)

MIXTRAL_8x7B = ModelSpec(
    name="Mixtral-8x7B",
    w_param_gb=87.0,
    batch=8, seq_len=2048, n_layers=32, d_model=4096, n_heads=32, d_head=128,
)

VIT_H14 = ModelSpec(
    name="ViT-H/14",
    w_param_gb=1.2,      # vision encoder only
    batch=32, seq_len=256, n_layers=32, d_model=1280, n_heads=16, d_head=80,
)

ALL_MODELS = [LLAMA3_8B, GPTJ_6B, LLAMA4_17B, MIXTRAL_8x7B, VIT_H14]
