"""solar/day6 — Evolutionary Interaction · Reproductive OS Layer (여섯째날)

Day6 = 이동으로 연결된 biosphere 위에서
       경쟁·공생·포식·돌연변이 → 종 다양성·선택 압력
       + 이중 유전자 재조합(재생산 프로토콜) 안정화

레이어 포지션:
    Day5: transport (행성 네트워크)
    Day6: competition + mutation + recombination (진화 혼란 → 재생산 OS → 질서)

핵심 방정식:
    dN_s/dt = r·N_s·gpp
              − Σ_j C[s][j]·N_s·N_j          (경쟁, 행렬)
              − Σ_pred A[pred][s]·N_pred·N_s  (포식 손실)
              + η·Σ_prey A[s][prey]·N_s·N_prey (포식 이득)
    Genome_child = recombine(Genome_A, Genome_B) + mutation
    μ_eff = base_rate × P_contact(ρ) × fitness_pressure(T, CO₂)
"""

__version__ = "0.1.0"

from .species_engine import SpeciesEngine, SpeciesState, make_species_engine
from .mutation_engine import MutationEngine, MutationEvent, make_mutation_engine
from .contact_engine import ContactEngine, ContactResult, make_contact_engine
from .genome_state import GenomeState, recombine, mutate
from .reproduction_engine import ReproductionEngine, ReproductionResult, make_reproduction_engine
from .selection_engine import SelectionEngine, SelectionResult, make_selection_engine
from .interaction_graph import InteractionGraph, make_interaction_graph
from .niche_model import NicheModel, NicheState, make_niche_model
from .day5_coupling import Day5Coupler, CouplingResult, make_day5_coupler
from .gaia_feedback import GaiaFeedbackEngine, GaiaFeedbackResult, make_gaia_feedback_engine

__all__ = [
    "SpeciesEngine",
    "SpeciesState",
    "make_species_engine",
    "MutationEngine",
    "MutationEvent",
    "make_mutation_engine",
    "ContactEngine",
    "ContactResult",
    "make_contact_engine",
    "GenomeState",
    "recombine",
    "mutate",
    "ReproductionEngine",
    "ReproductionResult",
    "make_reproduction_engine",
    "SelectionEngine",
    "SelectionResult",
    "make_selection_engine",
    "InteractionGraph",
    "make_interaction_graph",
    "NicheModel",
    "NicheState",
    "make_niche_model",
    # (A) Day5→Day6 coupling
    "Day5Coupler",
    "CouplingResult",
    "make_day5_coupler",
    # (B) Gaia feedback loop
    "GaiaFeedbackEngine",
    "GaiaFeedbackResult",
    "make_gaia_feedback_engine",
]
