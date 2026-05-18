from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

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

    # Hard constraint
    max_bsu_per_day: int = 3
    vehicle_capacity_kg: float = 1000.0

    # Bobot fitness
    weight_distance: float = 0.40
    weight_district: float = 0.30
    weight_unscheduled: float = 0.30

    # Kalender Indonesia
    use_indonesian_holidays: bool = True
    additional_holidays: Optional[List[date]] = None


@dataclass
class DailySchedule:
    tanggal: date
    items: List[BSU]
    total_volume: float
    total_distance: float
    kecamatan_list: List[str]


@dataclass
class FitnessDetail:
    distance_score: float
    district_penalty: float
    unscheduled_penalty: float
    fitness: float
    total_distance: float
    mixed_district_days: int
    used_days: int
    scheduled_bsu_count: int
    unscheduled_bsu_count: int


@dataclass
class GAResult:
    best_chromosome: List[BSU]
    best_schedule: List[DailySchedule]
    best_fitness: float
    fitness_detail: FitnessDetail
    generation_found: int
    fitness_history: List[float]
