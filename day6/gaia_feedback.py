"""gaia_feedback — Day6 Genome ↔ Environment feedback (Gaia loop 닫힘)

핵심 개념:
    지금까지: environment → fitness (단방향)
    이제:     genome → environment modification (루프 닫힘)

수식:
    Δalbedo(band)  = Σ_s N_s * genome_s.albedo_trait * w_albedo
    ΔCO₂_flux      = Σ_s N_s * genome_s.co2_trait    * w_co2
    ΔN_deposition  = Σ_s N_s * genome_s.n_trait      * w_n

    env_new["albedo"]   += Δalbedo   (식물 진화 → 지표 반사율 변화)
    env_new["CO2_ppm"]  += ΔCO₂_flux (미생물 → CO₂ flux 변화)
    env_new["N_soil"]   += ΔN_deposition

이 모듈이 없으면 Day6 는 "생물 시뮬레이션"으로만 동작.
이 모듈이 있으면 Day6 는 "planet-scale optimization system" 으로 동작.
→ Gaia hypothesis 의 핵심: 생명이 환경을 조절하는 피드백 루프.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable


@dataclass
class GaiaFeedbackResult:
    """한 스텝 Genome→Env 피드백 결과."""
    env_delta: Dict[str, float]   # 환경 변화량 {key: Δvalue}
    env_new: Dict[str, Any]       # 갱신된 환경


class GaiaFeedbackEngine:
    """Genome 집단 → 환경 수정 피드백 엔진.

    genome_to_env_fn(genome, density) → Dict[str, float]
    각 종의 genome 과 밀도(N_s) 를 받아 환경 변화량을 반환하는 함수.
    기본 구현: GenomeState.traits 의 인덱스별 환경 키에 매핑.

    Parameters
    ----------
    trait_env_map : Dict[int, str]
        {trait_idx: env_key}. 예: {0: "albedo", 1: "CO2_ppm", 2: "N_soil"}
    trait_weights : Dict[int, float]
        {trait_idx: weight}. 단위 변환 계수.
    clamp : Dict[str, tuple]
        {env_key: (min, max)}. 환경 변수 물리 한계 클램핑.
    """

    _DEFAULT_CLAMP: Dict[str, tuple] = {
        "albedo":   (0.0,  1.0),
        "CO2_ppm":  (150.0, 5000.0),
        "N_soil":   (0.0,  1e6),
        "T_surface": (150.0, 400.0),
    }

    def __init__(
        self,
        trait_env_map: Optional[Dict[int, str]] = None,
        trait_weights: Optional[Dict[int, float]] = None,
        clamp: Optional[Dict[str, tuple]] = None,
        genome_to_env_fn: Optional[Callable] = None,
    ) -> None:
        # 기본 trait 매핑: trait[0]=albedo, trait[1]=CO2, trait[2]=N
        self.trait_env_map: Dict[int, str] = trait_env_map or {
            0: "albedo",
            1: "CO2_ppm",
            2: "N_soil",
        }
        self.trait_weights: Dict[int, float] = trait_weights or {
            0: 1e-4,   # albedo: 아주 작은 변화 (genome 1단위 → Δalbedo 0.0001)
            1: 0.01,   # CO2_ppm: genome 1단위 → ΔCO2 0.01 ppm
            2: 0.001,  # N_soil: genome 1단위 → ΔN 0.001 g/m²
        }
        self.clamp: Dict[str, tuple] = clamp or dict(self._DEFAULT_CLAMP)
        self.genome_to_env_fn = genome_to_env_fn  # None이면 trait 매핑 사용

    def _genome_contribution(
        self,
        genome_traits: List[float],
        density: float,
    ) -> Dict[str, float]:
        """단일 genome × density → 환경 기여량."""
        if self.genome_to_env_fn is not None:
            return self.genome_to_env_fn(genome_traits, density)

        delta: Dict[str, float] = {}
        for trait_idx, env_key in self.trait_env_map.items():
            if trait_idx < len(genome_traits):
                w = self.trait_weights.get(trait_idx, 1e-5)
                delta[env_key] = delta.get(env_key, 0.0) + genome_traits[trait_idx] * density * w
        return delta

    def step(
        self,
        env: Dict[str, Any],
        genomes: List[List[float]],   # 종별 대표 genome traits
        densities: List[float],        # 종별 밀도 N_s
        dt_yr: float = 1.0,
    ) -> GaiaFeedbackResult:
        """전 종 genome × 밀도 → 환경 수정.

        Δenv_key = Σ_s genome_s[trait] * N_s * weight * dt_yr

        반환된 env_new 를 다음 스텝의 fitness_pressure() 에 전달하면
        Genome→Env→Fitness→Selection→Genome 루프 완성.
        """
        n = min(len(genomes), len(densities))
        total_delta: Dict[str, float] = {}

        for s in range(n):
            contrib = self._genome_contribution(genomes[s], max(0.0, densities[s]))
            for key, val in contrib.items():
                total_delta[key] = total_delta.get(key, 0.0) + val * dt_yr

        # 환경 갱신 + 물리 한계 클램핑
        env_new = dict(env)
        for key, delta in total_delta.items():
            current = float(env_new.get(key, 0.0))
            updated = current + delta
            if key in self.clamp:
                lo, hi = self.clamp[key]
                updated = max(lo, min(hi, updated))
            env_new[key] = updated

        return GaiaFeedbackResult(env_delta=total_delta, env_new=env_new)


def make_gaia_feedback_engine(
    trait_env_map: Optional[Dict[int, str]] = None,
    trait_weights: Optional[Dict[int, float]] = None,
    clamp: Optional[Dict[str, tuple]] = None,
) -> GaiaFeedbackEngine:
    return GaiaFeedbackEngine(
        trait_env_map=trait_env_map,
        trait_weights=trait_weights,
        clamp=clamp,
    )


__all__ = ["GaiaFeedbackEngine", "GaiaFeedbackResult", "make_gaia_feedback_engine"]
