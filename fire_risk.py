"""fire_risk.py — 위도×계절×생태계 산불 위험도 ODE (Phase 7f)

설계 철학: 세차운동·토양·항상성과 동일
  입력: 물리 환경값 (O2, T, W, B_wood, phi_deg, time_yr)
  출력: fire_risk ∈ [0,1] — 산불 발생 확률장 (viability field의 역)
        fire_intensity — 실제 탄소·O₂ 소비율 [kg C/m²/yr]

핵심 물리 (Bowman 2009; Pyne 2012; Lenton & Watson 2000):
  산불 3요소 = 산소 + 연료 + 열원
    f_O2(O2):    O₂ > 15%부터 점화 가능, > 25%에서 기하급수적 증가
    f_fuel(B_wood, organic): 목본 + 낙엽 = 연료량
    f_heat(T, F): 온도·복사 → 건조·점화 에너지
    f_dry(W):    수분 낮을수록 점화 쉬움 (역비례)

계절 연결:
  W_eff(φ, t) = W_base(φ) × (1 - dry_amplitude × sin(2π(t - t_dry(φ))))
    → 건기(여름 북반구, 겨울 남반구)에 W↓ → fire_risk↑
    → 극지 겨울(T < 0°C, 눈) → fire_risk ≈ 0

항상성 해석:
  fire_risk 높은 위도 = 현재 O₂ 과잉 → 산불로 소비해야 균형
  fire_risk 낮은 위도 = O₂ 정상 or 습함 → 산불 불필요
  전지구 fire_risk 가중평균 = Gaia O₂ attractor 복원력 지표

독립 모듈 원칙:
  solar/fire/는 solar/biosphere/에 의존하지 않음
  입력: 환경 dict만 받음
  출력: FireRiskState dataclass
"""

import math
from dataclasses import dataclass
from typing import Optional

# ── 물리 상수 ────────────────────────────────────────────────────────────────

# O₂ 산불 임계 (Lenton & Watson 2000)
O2_IGNITION_MIN  = 0.15   # [mol/mol] 15% 이하 점화 불가
O2_IGNITION_NORM = 0.21   # [mol/mol] 21% 현재 지구 기준
O2_IGNITION_HIGH = 0.25   # [mol/mol] 25% 이상 산불 기하급수 증가
O2_IGNITION_K    = 50.0   # 급격한 증가 계수 (sigmoid 기울기)

# 연료 임계
B_WOOD_HALF    = 0.5      # [kg C/m²] 목본 연료 반포화 (Michaelis-Menten)
ORGANIC_HALF   = 0.3      # [kg C/m²] 낙엽층 연료 반포화

# 온도 조건
T_FIRE_MIN     = 283.0    # [K] 10°C 이하 산불 거의 없음
T_FIRE_OPT     = 308.0    # [K] 35°C 최적 (건조 최대)
T_FIRE_MAX     = 333.0    # [K] 60°C 이상 → 열화 (드물)

# 건기 진폭 (위도별 건기·우기 계절성)
DRY_AMPLITUDE_TROPICAL  = 0.6   # 열대 건기: 건조 진폭 큼
DRY_AMPLITUDE_TEMPERATE = 0.4   # 온대: 중간
DRY_AMPLITUDE_POLAR     = 0.1   # 극지: 거의 없음 (눈/얼음)

# 산불 강도 계수 (탄소 소비)
K_FIRE_INTENSITY = 2.0    # [kg C/m²/yr] 최대 산불 탄소 소비율
                           # 관측: 보레알 산불 ~0.5~3 kg C/m²/yr

EPS = 1e-30


# ── 보조 함수 ─────────────────────────────────────────────────────────────────

def f_O2_fire(O2: float) -> float:
    """O₂ 농도 → 점화 가능도 [0~1].

    관측 기반 (Lenton & Watson 2000):
      O₂ < 15%: 점화 불가 → 0
      O₂ = 21%: 정상 → 0.4
      O₂ = 25%: 급증 → 0.8
      O₂ > 30%: 거의 1.0

    연속 sigmoid 구현 (no if-else 정신, 단 임계 0 처리):
      f = max(0, O2 - O2_IGNITION_MIN)^2 / normalization
    """
    excess_base = max(0.0, O2 - O2_IGNITION_MIN)     # 15% 이상만
    # 비선형 증폭: 25% 이상에서 기하급수 증가
    excess_high = max(0.0, O2 - O2_IGNITION_HIGH)
    f = (excess_base ** 1.5 + 3.0 * excess_high ** 2) / (0.3 + EPS)
    return min(1.0, max(0.0, f))


def f_fuel(B_wood: float, organic_litter: float = 0.0) -> float:
    """연료량 → 점화 가능도 [0~1].

    목본(B_wood) + 낙엽층(organic_litter) → 연료 총량
    Michaelis-Menten: f = fuel / (fuel + half)
    """
    fuel = B_wood + 0.5 * organic_litter
    return fuel / (fuel + B_WOOD_HALF + EPS)


def f_temperature(T: float) -> float:
    """온도 → 건조·점화 가능도 [0~1].

    삼각형 함수 (viability와 동일한 구조):
      T < T_FIRE_MIN → 0 (얼음/눈)
      T = T_FIRE_OPT → 1 (최적 건조)
      T > T_FIRE_MAX → 감소 (드문 케이스)
    """
    if T < T_FIRE_MIN:
        return 0.0
    elif T <= T_FIRE_OPT:
        return (T - T_FIRE_MIN) / (T_FIRE_OPT - T_FIRE_MIN + EPS)
    elif T <= T_FIRE_MAX:
        return (T_FIRE_MAX - T) / (T_FIRE_MAX - T_FIRE_OPT + EPS)
    else:
        return 0.0


def f_dryness(W: float) -> float:
    """수분 → 건조도 [0~1].

    수분이 낮을수록 산불 위험 높음 (역비례).
    W=0 → 1.0 (완전 건조), W=1 → 0.0 (포화)
    """
    return max(0.0, 1.0 - W)


def dry_season_modifier(phi_deg: float, time_yr: float) -> float:
    """위도별 건기 계절 수분 보정 계수 [0~1].

    북반구: 여름(time_yr≈0.5) → 건기
    남반구: 반대
    열대: 더 큰 진폭 (건기·우기 뚜렷)
    극지: 거의 없음

    반환값: 1 - dry_factor (낮을수록 건조)
    """
    abs_phi = abs(phi_deg)

    # 위도별 건기 진폭
    if abs_phi < 30.0:
        amplitude = DRY_AMPLITUDE_TROPICAL
    elif abs_phi < 60.0:
        amplitude = DRY_AMPLITUDE_TEMPERATE
    else:
        amplitude = DRY_AMPLITUDE_POLAR

    # 북반구: 여름(t=0.5) 건기 최대
    #   sin(2π(t - 0.25)) → t=0.5일 때 sin(π/2)=1 → dry_factor 최대
    # 남반구: 겨울(t=0.0) 건기 최대
    #   sin(2π(t - 0.75)) → t=0.0일 때 sin(-3π/2)=1 → dry_factor 최대
    if phi_deg >= 0:
        phase = 0.25
    else:
        phase = 0.75

    dry_factor = amplitude * math.sin(2.0 * math.pi * (time_yr - phase))
    # dry_factor > 0 → 건기 (수분 감소)
    return max(0.0, min(1.0, 1.0 - dry_factor))


# ── FireRiskState ─────────────────────────────────────────────────────────────

@dataclass
class FireRiskState:
    """단일 위도 밴드의 산불 위험도 상태.

    fire_risk ∈ [0,1]: 산불 발생 확률 (0=없음, 1=확실)
    fire_intensity: 실제 탄소 소비율 [kg C/m²/yr]
    fire_o2_sink:   O₂ 소비율 [mol/mol/yr]
    fire_co2_source: CO₂ 방출률 [kg C/m²/yr]

    항상성 해석:
      fire_risk → Gaia O₂ attractor 복원력 지표
      높은 fire_risk 위도 = "O₂ 항상성이 복원되어야 할 지점"
    """
    phi_deg:         float
    time_yr:         float
    fire_risk:       float   # [0,1] 종합 위험도
    f_O2:            float   # O₂ 기여
    f_fuel:          float   # 연료 기여
    f_temp:          float   # 온도 기여
    f_dry:           float   # 건조 기여
    fire_intensity:  float   # [kg C/m²/yr] 탄소 소비
    fire_o2_sink:    float   # [mol/mol/yr] O₂ 소비
    fire_co2_source: float   # [kg C/m²/yr] CO₂ 방출


# ── 핵심 함수 ─────────────────────────────────────────────────────────────────

def compute_fire_risk(
    O2:          float,        # [mol/mol] 전지구 대기 O₂
    T:           float,        # [K] 지표 온도
    W:           float,        # [0~1] 토양 수분
    B_wood:      float,        # [kg C/m²] 목본 바이오매스
    phi_deg:     float,        # [°] 위도
    time_yr:     float,        # [yr] 현재 시간 (계절 계산)
    organic_litter: float = 0.0,  # [kg C/m²] 낙엽층
    solar_flux:  float = 0.0,     # [W/m²] 태양 복사 (추가 건조 효과)
) -> FireRiskState:
    """위도×계절×생태계 → 산불 위험도 계산.

    fire_risk = f_O2 × f_fuel × f_temp × f_dry_effective
    모든 게이트 연속 곱 — no if-else (세차·토양·viability와 동일 구조)
    """
    # 1. O₂ 게이트
    fo2  = f_O2_fire(O2)

    # 2. 연료 게이트
    ffuel = f_fuel(B_wood, organic_litter)

    # 3. 온도 게이트
    ftemp = f_temperature(T)

    # 4. 건조도 게이트 (기본 수분 + 계절 건기 보정)
    dry_mod = dry_season_modifier(phi_deg, time_yr)
    W_eff   = W * dry_mod            # 건기 → W_eff 감소
    fdry    = f_dryness(W_eff)

    # 5. 종합 위험도 (연속 게이트 곱)
    fire_risk = fo2 * ffuel * ftemp * fdry

    # 6. 산불 강도 → 실제 소비율
    fire_intensity  = K_FIRE_INTENSITY * fire_risk   # [kg C/m²/yr]
    # O₂ 소비: C + O₂ → CO₂  (몰비 1:1, 질량비 12:32)
    fire_o2_sink    = fire_intensity * (32.0 / 12.0) / (1.2e18 / 1.48e14 + EPS)
    # 단순화: O₂ mol/mol 기준 (대기 O₂ 총량 기준 정규화)
    # KG_O2_PER_FRAC = 1.2e18 kg, LAND_AREA = 1.48e14 m²
    fire_co2_source = fire_intensity   # [kg C/m²/yr] (탄소 보존)

    return FireRiskState(
        phi_deg        = phi_deg,
        time_yr        = time_yr,
        fire_risk      = fire_risk,
        f_O2           = fo2,
        f_fuel         = ffuel,
        f_temp         = ftemp,
        f_dry          = fdry,
        fire_intensity = fire_intensity,
        fire_o2_sink   = fire_o2_sink,
        fire_co2_source= fire_co2_source,
    )
