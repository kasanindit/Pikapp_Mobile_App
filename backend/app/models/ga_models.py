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
    max_bsu_per_day: int = 3 #jadiin dinamis sesuai dari android
    vehicle_capacity_kg: float = 1000.0

    # Bobot fitness
    weight_distance: float = 0.35
    weight_district: float = 0.40
    weight_volume: float = 0.25

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
    volume_penalty: float
    constraint_penalty: float
    fitness: float

    total_distance: float
    mixed_district_days: int
    used_days: int

    scheduled_bsu_count: int
    missing_bsu_count: int
    duplicate_bsu_count: int
    empty_days_count: int


@dataclass
class GAResult:
    best_chromosome: List[BSU]
    # Hasil decode dari best_chromosome
    best_schedule: List[DailySchedule]

    best_fitness: float
    fitness_detail: FitnessDetail
    generation_found: int
    fitness_history: List[float]
