"""nitrogen/fixation.py — 질소고정 ODE (넷째날 순환 1-A)

설계 철학:
    "N₂ → 고정질소" 는 pioneer 생물이 만드는 첫 번째 출발점.
    산소가 낮을수록, 온도·수분이 적당할수록 질소고정 활발.

수식 (DAY4_DESIGN.md):
    N_fix(t) = K_fix × B_pioneer × f_O2_n × f_T × f_W

    f_O2_n = exp(-O2_frac / O2_HALF_N2FIXATION)
        → O₂ 높으면 혐기성 질소고정균 억제
        → O₂=0%: f_O2_n ≈ 1.0 (최대 고정)
        → O₂=21%: f_O2_n ≈ 0.07 (현재 지구 수준)

    f_T = exp(-((T_K - T_OPT_N2FIX)/(T_WIDTH_N2FIX))**2)
        → 최적 온도(25°C=298K) 가우시안 응답

    f_W = W_moisture / (W_moisture + W_HALF_N2FIX)
        → 수분 미카엘리스-멘텐 포화

    번개 고정:
    N_lightning = K_LIGHTNING × f_thunderstorm
        → 현재 지구: ~5 Tg N/yr 전지구

v1.0 (넷째날 순환 1-A):
    NitrogenFixation: 질소고정 속도 계산기
    LightningFixation: 번개 질소고정
    total_fixation(): 생물+번개 합산
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# ── 물리 상수 ─────────────────────────────────────────────────────────────────

# 질소고정 속도 상수
K_FIX_MAX = 0.005       # [g N m⁻² yr⁻¹] 최대 질소고정 속도 (pioneer 완전 피복 시)
                         # 현재 지구 전지구 생물고정 ~120 Tg N/yr → 단위면적 환산

# O₂ 억제 반감기 상수
O2_HALF_N2FIX = 0.05    # [mol/mol] f_O2_n = 0.5 되는 O₂ 분율
                         # O₂=5%에서 절반, O₂=21%에서 ~0.07

# 온도 최적값/폭 (질소고정균 Rhizobium, Azotobacter)
T_OPT_N2FIX = 303.0     # [K] 최적 온도 = 30°C
T_WIDTH_N2FIX = 15.0    # [K] 가우시안 폭 (±15K에서 1/e²로 감소)

# 수분 포화 상수
W_HALF_N2FIX = 0.3      # 수분 포화도 0.5 지점 (Michaelis-Menten)

# 번개 질소고정
K_LIGHTNING = 8e-5      # [g N m⁻² yr⁻¹] 전지구 번개 고정 (5 Tg N/yr ÷ 1.4e14 m²)
F_THUNDERSTORM_REF = 0.1  # 기준 뇌우 발생 빈도 [0~1]

EPS = 1e-30


# ── 스냅샷 ────────────────────────────────────────────────────────────────────

@dataclass
class FixationResult:
    """질소고정 결과 스냅샷.

    Attributes:
        N_fix_bio:    생물 질소고정 속도 [g N m⁻² yr⁻¹]
        N_fix_lightning: 번개 질소고정 속도 [g N m⁻² yr⁻¹]
        N_fix_total:  총 질소고정 속도 [g N m⁻² yr⁻¹]
        f_O2_n:       O₂ 억제 팩터 [0~1]
        f_T:          온도 팩터 [0~1]
        f_W:          수분 팩터 [0~1]
    """
    N_fix_bio: float
    N_fix_lightning: float
    N_fix_total: float
    f_O2_n: float
    f_T: float
    f_W: float

    def summary(self) -> str:
        return (
            f"N_fix={self.N_fix_total:.4f} g/m²/yr "
            f"(bio={self.N_fix_bio:.4f}, lightning={self.N_fix_lightning:.4f}) "
            f"f_O2={self.f_O2_n:.3f} f_T={self.f_T:.3f} f_W={self.f_W:.3f}"
        )


# ── NitrogenFixation ──────────────────────────────────────────────────────────

class NitrogenFixation:
    """생물+번개 질소고정 속도 계산기.

    사용법::

        fixer = NitrogenFixation()

        # 단일 시점 계산
        result = fixer.compute(
            B_pioneer=0.5,      # pioneer 식물 피복도 [0~1]
            O2_frac=0.21,       # 대기 O₂ 분율
            T_K=298.0,          # 지표 온도 [K]
            W_moisture=0.5,     # 토양 수분 포화도 [0~1]
            f_thunderstorm=0.1, # 뇌우 빈도 [0~1]
        )

        print(result.N_fix_total)  # [g N m⁻² yr⁻¹]

    항상성 의미:
        낮은 O₂ → f_O2_n↑ → N_fix↑ → N_soil↑ → GPP↑ → O₂↑ (양의 피드백)
        높은 O₂ → f_O2_n↓ → N_fix↓ → N_soil↓ → GPP↓ → O₂↓ (음의 피드백)
        → 산불 O₂ attractor와 상호작용하며 균형점 형성
    """

    def __init__(
        self,
        K_fix_max: float = K_FIX_MAX,
        O2_half: float = O2_HALF_N2FIX,
        T_opt: float = T_OPT_N2FIX,
        T_width: float = T_WIDTH_N2FIX,
        W_half: float = W_HALF_N2FIX,
        K_lightning: float = K_LIGHTNING,
    ):
        self.K_fix_max  = K_fix_max
        self.O2_half    = O2_half
        self.T_opt      = T_opt
        self.T_width    = T_width
        self.W_half     = W_half
        self.K_lightning = K_lightning

    # ── 환경 팩터 ─────────────────────────────────────────────────────────────

    def f_O2_nitrogen(self, O2_frac: float) -> float:
        """O₂ 억제 팩터.

        f_O2_n = exp(-O2_frac / O2_half)

        O₂ 높을수록 혐기성 질소고정균 활성 감소.
        """
        return math.exp(-max(0.0, O2_frac) / self.O2_half)

    def f_temperature(self, T_K: float) -> float:
        """온도 팩터 (가우시안).

        f_T = exp(-((T_K - T_opt) / T_width)²)
        """
        dT = (T_K - self.T_opt) / self.T_width
        return math.exp(-dT * dT)

    def f_moisture(self, W_moisture: float) -> float:
        """수분 팩터 (Michaelis-Menten).

        f_W = W / (W + W_half)
        """
        W = max(0.0, W_moisture)
        return W / (W + self.W_half + EPS)

    # ── 생물 질소고정 ─────────────────────────────────────────────────────────

    def bio_fixation_rate(
        self,
        B_pioneer: float,
        O2_frac: float,
        T_K: float,
        W_moisture: float,
    ) -> tuple[float, float, float, float]:
        """생물 질소고정 속도 계산.

        Returns:
            (N_fix_bio, f_O2_n, f_T, f_W)  [g N m⁻² yr⁻¹], [0~1] x3
        """
        f_o = self.f_O2_nitrogen(O2_frac)
        f_t = self.f_temperature(T_K)
        f_w = self.f_moisture(W_moisture)

        B = max(0.0, min(1.0, B_pioneer))
        N_fix = self.K_fix_max * B * f_o * f_t * f_w
        return N_fix, f_o, f_t, f_w

    # ── 번개 질소고정 ─────────────────────────────────────────────────────────

    def lightning_fixation_rate(self, f_thunderstorm: float = F_THUNDERSTORM_REF) -> float:
        """번개 질소고정 속도.

        N_lightning = K_lightning × f_thunderstorm / f_ref

        Args:
            f_thunderstorm: 뇌우 발생 빈도 [0~1], 기준=0.1

        Returns:
            N_lightning [g N m⁻² yr⁻¹]
        """
        f = max(0.0, f_thunderstorm)
        return self.K_lightning * f / (F_THUNDERSTORM_REF + EPS)

    # ── 통합 계산 ─────────────────────────────────────────────────────────────

    def compute(
        self,
        B_pioneer: float,
        O2_frac: float,
        T_K: float,
        W_moisture: float,
        f_thunderstorm: float = F_THUNDERSTORM_REF,
    ) -> FixationResult:
        """총 질소고정 결과 계산.

        Args:
            B_pioneer:     pioneer 식물 피복도 [0~1]
            O2_frac:       대기 O₂ 분율 [0~1]
            T_K:           지표 온도 [K]
            W_moisture:    토양 수분 포화도 [0~1]
            f_thunderstorm: 뇌우 빈도 [0~1]

        Returns:
            FixationResult
        """
        N_bio, f_o, f_t, f_w = self.bio_fixation_rate(B_pioneer, O2_frac, T_K, W_moisture)
        N_light = self.lightning_fixation_rate(f_thunderstorm)

        return FixationResult(
            N_fix_bio        = N_bio,
            N_fix_lightning  = N_light,
            N_fix_total      = N_bio + N_light,
            f_O2_n           = f_o,
            f_T              = f_t,
            f_W              = f_w,
        )


# ── 팩토리 ────────────────────────────────────────────────────────────────────

def make_fixation_engine(K_fix_max: float = K_FIX_MAX) -> NitrogenFixation:
    """기본 지구 파라미터 질소고정 엔진."""
    return NitrogenFixation(K_fix_max=K_fix_max)


__all__ = [
    "NitrogenFixation",
    "FixationResult",
    "make_fixation_engine",
    "K_FIX_MAX",
    "O2_HALF_N2FIX",
    "T_OPT_N2FIX",
]
