from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Optional


@dataclass
class BSU:
    bsu_id: str
    nama_bsu: str
    kecamatan: str
    estimated_volume_kg: float
    latitude: float
    longitude: float
    is_active: bool = True


@dataclass
class ScheduleConfig:
    start_date: date
    end_date: date

    max_bsu_per_day: int = 3
    vehicle_capacity_kg: float = 1000.0

    # parameter GA
    population_size: int = 80
    generations: int = 200
    crossover_rate: float = 0.80
    mutation_rate: float = 0.15
    elitism_count: int = 2
    tournament_size: int = 4
    
    # bobot constraint
    coverage_weight: float = 35.0
    kecamatan_weight: float = 25.0
    max_bsu_weight: float = 30.0
    capacity_weight: float = 5.0
    volume_balance_weight: float = 5.0

    random_seed: Optional[int] = None
    use_indonesian_holidays: bool = True
    additional_holidays: Optional[List[date]] = None
    
@dataclass
class DailySchedule:
    tanggal: date
    items: List[BSU] = field(default_factory=list)
    total_volume: float = 0.0
    total_distance: float = 0.0
    kecamatan_list: List[str] = field(default_factory=list)

    @property
    def kecamatan_set(self) -> set[str]:
        return {bsu.kecamatan for bsu in self.items}


@dataclass
class SlotWarning:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationSnapshot:
    generation: int
    best_fitness: float
    total_penalty: float
    capacity_penalty: float
    kecamatan_penalty: float
    max_bsu_penalty: float
    empty_days_count: int
    overloaded_days_count: int
    over_quota_days_count: int
    mixed_district_days: int


@dataclass
class FitnessDetail:
    coverage_penalty: float
    capacity_penalty: float
    max_bsu_penalty: float
    kecamatan_penalty: float
    total_penalty: float
    fitness: float

    total_distance: float
    mixed_district_days: int
    used_days: int
    scheduled_bsu_count: int
    missing_bsu_count: int
    duplicate_bsu_count: int
    empty_days_count: int
    overloaded_days_count: int
    over_quota_days_count: int


@dataclass
class GAResult:
    best_chromosome: List[BSU]
    best_schedule: List[DailySchedule]
    best_fitness: float
    fitness_detail: FitnessDetail
    generation_found: int
    fitness_history: List[float]
    generation_snapshots: List[GenerationSnapshot] = field(default_factory=list)
    warnings: List[SlotWarning] = field(default_factory=list)
    working_day_count: int = 0
    total_slot: int = 0
    max_bsu_per_day: int = 0
    vehicle_capacity_kg: float = 0.0
