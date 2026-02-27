"""forget_engine.py — 인지적 망각 엔진 (GaiaFire 인지 브리지)

핵심 통찰:
  산불과 망각은 수학적으로 동일한 클래스의 시스템이다.
  둘 다 "음의 피드백 attractor" — 과잉 누적을 비선형으로 소거하여 항상성 복원.

동역학적 대응:

  행성 (GaiaFire)               인지 (ForgetEngine)
  ─────────────────────────────────────────────────────
  O₂ [mol/mol]              ↔  Memory_Load [synapses/neuron]
  O₂ 과잉 임계 (25%)         ↔  Load 과잉 임계 (L_th)
  fire_risk = f_O2×f_fuel×  ↔  forget_risk = f_load×f_debris×
              f_temp×f_dry              f_stress×f_fatigue
  fire_sink = K×max(0,O2-th)²↔  forget_sink = K×max(0,L-L_th)²
  biomass 소각                ↔  시냅스 가지치기 (synaptic pruning)
  CO₂ 방출 → 새 광합성 기회  ↔  기억 소거 → 새 학습 공간
  산불 hot spot (위도)        ↔  pruning hot spot (뇌 영역)
  전지구 GFI                  ↔  전뇌 인지 부하 지수 (CBI)

수식 동일성:

  산불:   fire_sink   ∝ max(0, O2   - O2_th  )²
  망각:   forget_sink ∝ max(0, Load - Load_th )²

  둘 다: ∂(d상태/dt)/∂상태 < 0  ← attractor 조건

스트레스와의 관계:
  스트레스 = 두 시스템에서 공통적으로 "임계 초과 상태"

  행성 스트레스:  고O₂ + 고온 + 건조   → 산불 발생
  뇌 스트레스:    고부하 + 코르티솔↑   → 시냅스 가소성 억제 + pruning↑
    코르티솔 ↑  ↔  W (수분) ↓  (건조 게이트 = 스트레스 게이트)
    Ca²⁺ ↑     ↔  T (온도) ↑  (열 게이트 = 흥분독성 게이트)
    열 충격     ↔  T > T_MAX  (f_temperature 감소 = 심각한 손상)

4가지 망각 게이트:

  f_load(L):     기억 부하 게이트 (= f_O2)
    L < L_min → 망각 없음 (안전 구간)
    L > L_high → 급격한 망각 (비선형)

  f_debris(D):   미처리 자극 누적 (= f_fuel)
    처리 안 된 감각 입력 + 반추 → 망각 연료

  f_stress(cortisol): 스트레스 호르몬 게이트 (= f_temperature)
    낮은 코르티솔 → 망각 없음
    최적 코르티솔 → 망각 최대 (역설적으로 적응적)
    극도 코르티솔 → 시스템 손상 (f_temp > T_MAX와 동일)

  f_fatigue(ATP): 주의력 자원 고갈 (= f_dryness)
    ATP 충분 → 기억 보호
    ATP 고갈 → 방어 메커니즘 무력화 → 망각↑

재생을 위한 파괴:
  산불: 오래된 biomass 제거 → 새 생장 공간
  망각: 오래된 기억 제거 → 새 학습 공간
  둘 다: 항상성 = "적절한 소거"가 있어야 유지됨

CookiieBrain 통합 방향:
  MetabolicFeedback:
    CO₂↑ → 손실 증가  ↔  debris↑ → forget_risk↑
    Heat↑ → 효율 감소  ↔  cortisol↑ → LTP 억제
    Ca_alert → recovery  ↔  Ca²⁺↑ → 흥분독성 → 강제 pruning

  뉴런-Gaia 브리지:
    fire_engine.global_fire_index()  → 전지구 O₂ attractor 압력
    forget_engine.global_cbi()       → 전뇌 인지 부하 압력
    두 값을 동시에 모니터링 → "행성-뇌 항상성 동기화 지표"
"""

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

EPS = 1e-30

# ── 물리 상수 (인지 스케일) ───────────────────────────────────────────────────

# 기억 부하 임계 (= O₂ 임계의 인지 대응)
LOAD_IGNITION_MIN  = 0.3   # [0~1] 이 이하는 pruning 없음
LOAD_IGNITION_NORM = 0.5   # [0~1] 정상 부하
LOAD_IGNITION_HIGH = 0.7   # [0~1] 이 이상 급격한 pruning

# 미처리 자극 누적 (연료) 임계
DEBRIS_HALF = 0.4          # Michaelis-Menten 반포화

# 스트레스(코르티솔) 조건 (= 온도 게이트의 인지 대응)
CORTISOL_MIN = 0.1         # [0~1] 이 이하 pruning 없음
CORTISOL_OPT = 0.5         # [0~1] 적응적 pruning 최대
CORTISOL_MAX = 0.9         # [0~1] 이 이상 손상 모드

# 주의력/ATP 자원 고갈 (= 건조 게이트의 인지 대응)
# f_fatigue(ATP) = max(0, 1 - ATP) → ATP=0이면 완전 무방비

# 망각 강도 계수
K_FORGET_INTENSITY = 1.0   # [synapses/neuron/s] 최대 pruning 속도


# ── 게이트 함수 ───────────────────────────────────────────────────────────────

def f_load(L: float) -> float:
    """기억 부하 → 망각 위험도 [0~1].  (= f_O2_fire의 인지 대응)

    L < 30%: pruning 없음 (안전)
    L > 70%: 급격한 비선형 pruning
    """
    excess_base = max(0.0, L - LOAD_IGNITION_MIN)
    excess_high = max(0.0, L - LOAD_IGNITION_HIGH)
    f = (excess_base ** 1.5 + 3.0 * excess_high ** 2) / (0.3 + EPS)
    return min(1.0, max(0.0, f))


def f_debris(D: float, noise: float = 0.0) -> float:
    """미처리 자극 누적 → 망각 연료 [0~1].  (= f_fuel의 인지 대응)

    D: 처리 안 된 감각 입력 + 반추 노이즈 축적량
    noise: 추가 배경 노이즈 (시냅스 잡음)
    """
    total = D + 0.5 * noise
    return total / (total + DEBRIS_HALF + EPS)


def f_stress(cortisol: float) -> float:
    """스트레스(코르티솔) → pruning 촉진도 [0~1].  (= f_temperature 인지 대응)

    삼각형 게이트:
      낮은 코르티솔 → 망각 없음 (각성 부족)
      중간 코르티솔 → 적응적 망각 최대 (역설: 스트레스가 정리를 도움)
      극도 코르티솔 → 시스템 손상 (흥분독성, 해마 위축)
    """
    rise = max(0.0, cortisol - CORTISOL_MIN) / (CORTISOL_OPT - CORTISOL_MIN + EPS)
    fall = max(0.0, CORTISOL_MAX - cortisol) / (CORTISOL_MAX - CORTISOL_OPT + EPS)
    return min(rise, fall, 1.0)


def f_fatigue(atp: float) -> float:
    """ATP(주의력) 고갈 → 방어 무력화 [0~1].  (= f_dryness 인지 대응)

    ATP=1.0 (충분) → 기억 보호 → fatigue=0
    ATP=0.0 (고갈) → 방어 붕괴 → fatigue=1
    """
    return max(0.0, 1.0 - atp)


def circadian_modifier(region_id: int, time_hr: float) -> float:
    """수면-각성 주기 수분 보정.  (= dry_season_modifier의 인지 대응)

    수면 중(22:00~06:00): pruning 최대 (뇌 청소 시간)
    각성 중: pruning 감소

    region_id: 0~11 (뇌 영역 인덱스 = 위도 밴드 인덱스)
    time_hr: 0~24 [hours]
    """
    # 수면 위상: time_hr=2 (새벽 2시) 최대
    # sin(2π(t/24 - 2/24)) → t=2일 때 최대
    phase_hr = 2.0
    amplitude = 0.7   # 수면 중 pruning 진폭 (건기와 동일 역할)
    sleep_factor = amplitude * math.sin(
        2.0 * math.pi * ((time_hr / 24.0) - phase_hr / 24.0)
    )
    # 수면(sleep_factor>0) → 연결성 낮음 → forget_risk↑
    # max(0.0, ...) → 수면 중에만 효과
    return max(0.0, min(1.0, 1.0 - max(0.0, sleep_factor)))


# ── ForgetRiskState ────────────────────────────────────────────────────────────

@dataclass
class ForgetRiskState:
    """단일 뇌 영역의 망각 위험도 상태.  (= FireRiskState의 인지 대응)

    GaiaFire ↔ ForgetEngine 단위 대응:
      fire_risk         ↔ forget_risk       [0~1]
      fire_intensity    ↔ forget_intensity  [synapses/neuron/s]
      fire_o2_sink_kgO2 ↔ atp_drain        [ATP/neuron/s]
      fire_co2_source   ↔ noise_release     (억압된 기억 → 의식에 노출)
    """
    region_id:          int
    time_hr:            float
    forget_risk:        float   # [0~1] 종합 망각 위험도
    f_load:             float   # 부하 기여
    f_debris:           float   # 잡음 기여
    f_stress:           float   # 스트레스 기여
    f_fatigue:          float   # 피로 기여
    forget_intensity:   float   # [synapses/neuron/s] pruning 속도
    atp_drain:          float   # [ATP/neuron/s] 에너지 소비
    noise_release:      float   # [0~1] 억압 기억 표면화 확률


# ── 핵심 함수 ─────────────────────────────────────────────────────────────────

def compute_forget_risk(
    load:      float,    # [0~1] 기억 부하 (= O₂)
    cortisol:  float,    # [0~1] 스트레스 호르몬 (= 온도)
    atp:       float,    # [0~1] 주의력/ATP (= 수분)
    debris:    float,    # [0~1] 미처리 자극 누적 (= B_wood)
    region_id: int,      # 뇌 영역 인덱스 0~11 (= 위도)
    time_hr:   float,    # [hr] 현재 시간 (수면주기 계산)
    noise:     float = 0.0,  # [0~1] 배경 노이즈 (= organic_litter)
) -> ForgetRiskState:
    """뇌 영역×수면주기×인지 상태 → 망각 위험도.

    forget_risk = f_load × f_debris × f_stress × f_fatigue_effective
    (= fire_risk = f_O2 × f_fuel × f_temp × f_dry와 동일 구조)
    """
    fl   = f_load(load)
    fd   = f_debris(debris, noise)
    fs   = f_stress(cortisol)

    # 수면 주기 수분 보정 (= dry_season_modifier)
    circ_mod = circadian_modifier(region_id, time_hr)
    atp_eff  = atp * circ_mod          # 수면 중 ATP 방어 약화
    ffat     = f_fatigue(atp_eff)

    forget_risk = fl * fd * fs * ffat

    # 로컬 플럭스 (= 로컬 탄소 플럭스)
    forget_intensity = K_FORGET_INTENSITY * forget_risk
    atp_drain        = forget_intensity * 2.0   # pruning은 에너지 비용 있음
    noise_release    = forget_intensity * 0.3   # 일부 억압 기억 표면화

    return ForgetRiskState(
        region_id        = region_id,
        time_hr          = time_hr,
        forget_risk      = forget_risk,
        f_load           = fl,
        f_debris         = fd,
        f_stress         = fs,
        f_fatigue        = ffat,
        forget_intensity = forget_intensity,
        atp_drain        = atp_drain,
        noise_release    = noise_release,
    )


# ── CognitiveBrainSnapshot ────────────────────────────────────────────────────

@dataclass
class CognitiveBrainSnapshot:
    """전뇌 인지 상태 스냅샷.  (= FireEnvSnapshot의 인지 대응)

    전역 변수:
      memory_load_global: 전체 기억 부하 [0~1]  (= O2_frac)
      cortisol_global:    스트레스 호르몬 [0~1]  (= 대기 CO₂ — 온실 효과)
      atp_global:         에너지 상태 [0~1]      (= 태양상수)
      time_hr:            현재 시각 [0~24]       (= 계절)
    """
    memory_load_global: float = 0.5
    cortisol_global:    float = 0.3
    atp_global:         float = 0.8
    time_hr:            float = 14.0  # 기본: 오후 2시 (각성 상태)
    region_debris:      Optional[List[float]] = None  # 영역별 잡음


# ── ForgetEngine ──────────────────────────────────────────────────────────────

class ForgetEngine:
    """전뇌 망각 발생 예측 엔진.  (= FireEngine의 인지 대응)

    인지 상태 → 뇌 영역별 망각 위험도 맵 → pruning hot spot 예측
    항상성과의 연결: forget_risk 분포 = 인지 부하 복원력 공간 분포

    GaiaFire 연결:
      fire_engine.global_fire_index() ↔ forget_engine.global_cbi()
      두 값의 상관관계 = 행성-뇌 항상성 동기화 지표

    사용:
        engine = ForgetEngine()
        brain = CognitiveBrainSnapshot(memory_load_global=0.8, time_hr=3.0)
        result = engine.predict(brain)
        engine.print_map(result)
    """

    HOTSPOT_THRESHOLD = 0.05   # forget_risk > 0.05 → pruning hot spot

    REGION_NAMES = [
        "소뇌/뇌간",  "시상하부",    "해마(뒤)",  "편도체",
        "해마(앞)",   "기저핵",      "전두엽(후)", "측두엽",
        "두정엽",     "전두엽(전)",  "전전두엽",  "디폴트모드",
    ]

    def predict(self, brain: CognitiveBrainSnapshot) -> List[ForgetRiskState]:
        """전뇌 망각 위험도 예측."""
        results = []
        for region_id in range(12):
            # 영역별 잡음 (= B_wood 프로파일)
            debris = (brain.region_debris[region_id]
                      if brain.region_debris else
                      0.5 * math.exp(-((region_id - 4) / 3.0) ** 2) + 0.1)

            rs = compute_forget_risk(
                load      = brain.memory_load_global,
                cortisol  = brain.cortisol_global,
                atp       = brain.atp_global,
                debris    = debris,
                region_id = region_id,
                time_hr   = brain.time_hr,
            )
            results.append(rs)
        return results

    def global_cbi(self, results: List[ForgetRiskState]) -> float:
        """전뇌 인지 부하 지수 (Cognitive Burden Index).
        (= FireEngine.global_fire_index()의 인지 대응)
        """
        return sum(r.forget_risk for r in results) / len(results)

    def homeostasis_pressure(self, results: List[ForgetRiskState]) -> Dict[str, Any]:
        """인지 항상성 복원 압력 분석."""
        dominant = max(results, key=lambda r: r.forget_risk)
        cbi = self.global_cbi(results)
        total_atp_drain = sum(r.atp_drain for r in results)
        return {
            "cognitive_burden_index": cbi,
            "dominant_region":   self.REGION_NAMES[dominant.region_id],
            "dominant_region_id": dominant.region_id,
            "total_atp_drain":   total_atp_drain,
            "homeostasis_pressure": min(1.0, cbi * 2.0),
        }

    def print_map(self, results: List[ForgetRiskState],
                  title: str = "전뇌 망각 위험도 MAP") -> None:
        print(f"\n  {title}")
        print(f"  {'영역':>12}  {'위험도':>7}  {'부하':>5}  {'잡음':>5}  "
              f"{'스트레스':>8}  {'피로':>5}  {'강도':>7}  시각화")
        print("  " + "-" * 85)
        for r, name in zip(results, self.REGION_NAMES):
            bar_len = int(r.forget_risk * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            spot = "🧹PRUNE" if r.forget_risk > self.HOTSPOT_THRESHOLD else "     "
            print(
                f"  {name:>12}"
                f"  {r.forget_risk:>7.3f}"
                f"  {r.f_load:>5.2f}"
                f"  {r.f_debris:>5.2f}"
                f"  {r.f_stress:>8.2f}"
                f"  {r.f_fatigue:>5.2f}"
                f"  {r.forget_intensity:>7.3f}"
                f"  |{bar}| {spot}"
            )


# ── GaiaForgetBridge — 행성-뇌 항상성 동기화 ──────────────────────────────────

class GaiaForgetBridge:
    """행성 산불 ↔ 인지 망각 항상성 동기화 분석기.

    두 시스템을 동시에 실행하여:
      1. 수식 동일성 검증
      2. 행성-뇌 동기화 지표 계산
      3. 확장: 뇌 상태 → 지구 환경 파라미터로 매핑 (역방향 탐색)
    """

    def compare(
        self,
        fire_gfi: float,    # FireEngine.global_fire_index()
        forget_cbi: float,  # ForgetEngine.global_cbi()
    ) -> Dict[str, Any]:
        """행성 GFI ↔ 뇌 CBI 비교 분석."""
        sync = 1.0 - abs(fire_gfi - forget_cbi)
        return {
            "fire_gfi":    fire_gfi,
            "forget_cbi":  forget_cbi,
            "sync_index":  sync,          # 1.0 = 완전 동기화
            "delta":       fire_gfi - forget_cbi,
            "interpretation": (
                "동기화 (행성-뇌 항상성 일치)" if sync > 0.8
                else "비동기 (두 시스템 부하 불균형)"
            ),
        }

    def planet_to_brain(self, O2_frac: float, CO2_ppm: float,
                        time_yr: float) -> CognitiveBrainSnapshot:
        """행성 환경 파라미터 → 뇌 상태로 매핑 (탐색적).

        O2_frac  → memory_load_global (높은 O₂ = 높은 인지 부하)
        CO2_ppm  → cortisol_global    (CO₂ 과잉 = 스트레스 반응)
        time_yr  → time_hr            (계절 → 일주기 매핑)
        """
        load     = min(1.0, max(0.0, (O2_frac - 0.15) / (0.35 - 0.15)))
        cortisol = min(1.0, max(0.0, (CO2_ppm - 280.0) / (800.0 - 280.0)))
        time_hr  = (time_yr % 1.0) * 24.0
        return CognitiveBrainSnapshot(
            memory_load_global = load,
            cortisol_global    = cortisol,
            atp_global         = 1.0 - cortisol * 0.5,
            time_hr            = time_hr,
        )
