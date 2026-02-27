"""solar/day5 — 생물 이동 / 정보 네트워크 레이어 (다섯째날)

Day5 = 움직이는 생물 + 씨드 분산 + 먹이사슬 (Loop F/G/H)

천지창조 다섯째 날의 핵심:
    새·물고기 등 하늘·바다에서 자유롭게 이동하는 대형 생명체.
    이들의 움직임이 전 지구적 물질·정보 네트워킹의 시작점이 된다.

Creation Layer 포지션:
    Day1  : SolarLuminosity (빛 에너지)
    Day2  : AtmosphereColumn (대기·온도·물)
    Day3  : BiosphereColumn / FireEngine (식생·산불)
    Day4  : NitrogenCycle / MilankovitchCycle (진화·주기)
    Day5  : BirdAgent / FishAgent / SeedTransport / FoodWeb  ← 현재 레이어
             "독립 기어 원칙" 유지 — Day3 내부 수정 없이 외부 transport 가산

핵심 방정식 (위도 밴드 transport):
    dB[i]/dt = f_local(B[i]) + Σ_j K[j→i]*B[j] - Σ_j K[i→j]*B[i]

    f_local  = Day3 BiosphereColumn (로컬 독립 ODE)
    K[j→i]  = 위도 밴드 j → i transport 커널 [1/yr]

도메인 분리:
    BirdAgent  → land_fraction_by_band 적용: 육상 밴드에서만 활동
    FishAgent  → (1 - land_fraction) 적용: 해양 밴드에서만 활동

대형 생명체 스케일링:
    biomass_by_band 파라미터로 개체수/바이오매스에 비례하는 플럭스 계산

장거리 이동 (전 지구적 네트워킹):
    long_range_max_jump=2 → ±2 밴드 동시 연결, 극지→적도 도달 시간 단축

Loop 연결:
    Loop F: BirdAgent 씨드 분산 → pioneer B[i] 증가   (육상, 장거리 가능)
    Loop G: BirdAgent 구아노    → nitrogen.N_soil[i]   (육상, [g N/m²/yr])
    Loop H: FishAgent 포식      → phyto 감소 → CO₂ 증가 (해양)

모듈:
    _constants.py       — 공유 상수 단일 소스 (단위 명시)
    mobility_engine.py  — BirdAgent / FishAgent + long_range_neighbors
    seed_transport.py   — 보존형 transport 커널 (총합 보존 수학적 보장)
    food_web.py         — 트로픽 ODE (phyto / herbivore / carnivore, 사망률 포함)
    day5_demo.py        — V1~V13 ALL PASS 검증
"""

__version__ = "1.1.0"
# v1.0.0: 초기 구현 (Loop F/G/H, 극지 topology, carnivore 사망률)
# v1.1.0: 완성도 향상 — herbivore 사망률, guano 단위, 장거리 이동,
#         도메인 분리(Bird 육상/Fish 해양), biomass 스케일링, V1~V13 ALL PASS

from ._constants import (
    R_SEED_DISPERSAL,
    R_GUANO_N,
    R_PREDATION,
    R_RESP_CO2,
    ALPHA_CO2_ABS,
    DEFAULT_GROWTH_PHYTO,
    DEFAULT_GRAZING_RATE,
    DEFAULT_PREDATION,
    DEFAULT_RESP_FRAC,
    M_CARNIVORE,
    M_HERBIVORE,
)
from .mobility_engine import (
    BirdAgent,
    FishAgent,
    make_bird_agent,
    make_fish_agent,
    long_range_neighbors,
)
from .seed_transport import (
    SeedTransport,
    TransportKernel,
    make_transport,
)
from .food_web import (
    FoodWeb,
    TrophicState,
    make_food_web,
)

__all__ = [
    # constants
    "R_SEED_DISPERSAL",
    "R_GUANO_N",
    "R_PREDATION",
    "R_RESP_CO2",
    "ALPHA_CO2_ABS",
    "DEFAULT_GROWTH_PHYTO",
    "DEFAULT_GRAZING_RATE",
    "DEFAULT_PREDATION",
    "DEFAULT_RESP_FRAC",
    "M_CARNIVORE",
    "M_HERBIVORE",
    # mobility
    "BirdAgent",
    "FishAgent",
    "make_bird_agent",
    "make_fish_agent",
    "long_range_neighbors",
    # transport
    "SeedTransport",
    "TransportKernel",
    "make_transport",
    # food web
    "FoodWeb",
    "TrophicState",
    "make_food_web",
]
