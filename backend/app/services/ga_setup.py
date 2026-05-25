from __future__ import annotations

import math
from datetime import date, timedelta
from typing import List, Optional

from models.ga_models import BSU, DailySchedule, FitnessDetail, ScheduleConfig

try:
    import holidays  # type: ignore[import]
except ImportError:
    holidays = None

# haversine formula
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_km * c

# calendar hari kerja indonesia
def get_working_days(
    start_date: date,
    end_date: date,
    use_indonesian_holidays: bool = True,
    additional_holidays: Optional[List[date]] = None
) -> List[date]:
    working_days: List[date] = []
    current_date = start_date

    additional_holidays_set = set(additional_holidays or [])

    indonesia_holidays = set()

    if use_indonesian_holidays:
        if holidays is None:
            raise ImportError(
                "Library 'holidays' belum terinstall. "
                "Install dengan: pip install holidays"
            )

        years = list(range(start_date.year, end_date.year + 1))
        indonesia_holidays = set(holidays.country_holidays("ID", years=years).keys())

    while current_date <= end_date:
        is_weekend = current_date.weekday() >= 5
        is_national_holiday = current_date in indonesia_holidays
        is_additional_holiday = current_date in additional_holidays_set

        if not is_weekend and not is_national_holiday and not is_additional_holiday:
            working_days.append(current_date)

        current_date += timedelta(days=1)

    return working_days

# hitung jarak antar bsu berdasarkan jadwal harian
def calculate_route_distance(items: List[BSU]) -> float:
    if len(items) <= 1:
        return 0.0

    total_distance = 0.0

    for i in range(len(items) - 1):
        current_bsu = items[i]
        next_bsu = items[i + 1]

        total_distance += haversine_distance(
            current_bsu.latitude,
            current_bsu.longitude,
            next_bsu.latitude,
            next_bsu.longitude,
        )

    return total_distance

def build_daily_schedule(tanggal: date, items: List[BSU]) -> DailySchedule:
    total_volume = sum(item.estimated_volume_kg for item in items)
    total_distance = calculate_route_distance(items)
    kecamatan_list = sorted(list({item.kecamatan for item in items}))

    return DailySchedule(
        tanggal=tanggal,
        items=items,
        total_volume=total_volume,
        total_distance=total_distance,
        kecamatan_list=kecamatan_list,
    )
    
# =========================
# SKOR PENEMPATAN BSU KE HARI
# =========================
def calculate_insertion_score(
    bsu: BSU,
    items: List[BSU],
    target_average_volume: float
) -> float:
    # Kalau hari masih kosong, jadikan prioritas
    if not items:
        return 0.0

    # Skor kecamatan
    kecamatan_set = {item.kecamatan for item in items}

    if bsu.kecamatan in kecamatan_set:
        district_score = 0.0
    else:
        district_score = 1.0

    # Skor volume
    current_volume = sum(item.estimated_volume_kg for item in items)
    new_volume = current_volume + bsu.estimated_volume_kg

    if target_average_volume <= 0:
        volume_score = 0.0
    else:
        volume_score = abs(new_volume - target_average_volume) / target_average_volume
        volume_score = min(1.0, volume_score)

    # Semakin kecil semakin baik
    return 0.6 * district_score + 0.4 * volume_score

# decoder -> ubah kromosom menjadi urutan jadwal harian
def decode_chromosome(
    chromosome: List[BSU],
    config: ScheduleConfig,
    working_days: Optional[List[date]] = None
) -> List[DailySchedule]:

    if working_days is None:
        working_days = get_working_days(
            config.start_date,
            config.end_date,
            use_indonesian_holidays=config.use_indonesian_holidays,
            additional_holidays=config.additional_holidays
        )

    if not working_days:
        return []

    assignment = {
        day: []
        for day in working_days
    }

    if not chromosome:
        return [
            build_daily_schedule(day, assignment[day])
            for day in working_days
        ]

    total_volume = sum(bsu.estimated_volume_kg for bsu in chromosome)
    target_average_volume = total_volume / len(working_days)

    index = 0

    # 1. Isi hari kerja satu per satu selama BSU masih ada
    for day in working_days:
        if index >= len(chromosome):
            break

        assignment[day].append(chromosome[index])
        index += 1

    # 2. Sisa BSU dimasukkan ke hari terbaik tanpa validasi ketat
    remaining_bsu = chromosome[index:]

    for bsu in remaining_bsu:
        best_day = min(
            working_days,
            key=lambda day: calculate_insertion_score(
                bsu=bsu,
                items=assignment[day],
                target_average_volume=target_average_volume
            )
        )

        assignment[best_day].append(bsu)

    schedule = [
        build_daily_schedule(day, assignment[day])
        for day in working_days
    ]

    return schedule

# normalisasi jarak
def estimate_max_distance(
    population: List[List[BSU]],
    config: ScheduleConfig,
    working_days: Optional[List[date]] = None
) -> float:
    max_distance = 0.0

    for chromosome in population:
        schedule = decode_chromosome(chromosome, config, working_days)
        total_distance = sum(daily.total_distance for daily in schedule)

        max_distance = max(max_distance, total_distance)

    return max_distance if max_distance > 0 else 1.0

# hitung fitness
def calculate_fitness_detail(
    chromosome: List[BSU],
    config: ScheduleConfig,
    max_distance: float,
    working_days: Optional[List[date]] = None
) -> FitnessDetail:

    schedule = decode_chromosome(
        chromosome=chromosome,
        config=config,
        working_days=working_days
    )

   # distance: total jarak harian
    total_distance = sum(daily.total_distance for daily in schedule)

    if max_distance <= 0:
        max_distance = 1.0

    distance_score = min(1.0, total_distance / max_distance)

    # fitness untuk pengelompokkan kecamatan
    mixed_district_days = 0
    district_penalty_total = 0.0

    for daily in schedule:
        if not daily.items:
            district_penalty_total += 1.0
            continue

        kecamatans = [item.kecamatan for item in daily.items]

        if len(set(kecamatans)) > 1:
            mixed_district_days += 1

        dominant_count = max(
            kecamatans.count(kecamatan)
            for kecamatan in set(kecamatans)
        )

        daily_penalty = 1.0 - (dominant_count / len(kecamatans))
        district_penalty_total += daily_penalty

    district_penalty = district_penalty_total / len(schedule) if schedule else 1.0

    # fitness pemerataan volume harian
    daily_volumes = [
        daily.total_volume
        for daily in schedule
    ]

    if not daily_volumes:
        volume_penalty = 1.0
    else:
        mean_volume = sum(daily_volumes) / len(daily_volumes)

        if mean_volume <= 0:
            volume_penalty = 1.0
        else:
            variance = sum(
                (volume - mean_volume) ** 2
                for volume in daily_volumes
            ) / len(daily_volumes)

            std_dev = math.sqrt(variance)
            volume_penalty = min(1.0, std_dev / mean_volume)

    # constraint penalty: penalti jika ada hari yang kosong, BSU yang tidak terjadwalkan, atau duplikasi BSU
    scheduled_ids: List[str] = []
    constraint_penalty = 0.0
    empty_days_count = 0

    for daily in schedule:
        if len(daily.items) == 0:
            empty_days_count += 1
            constraint_penalty += 5.0

        if len(daily.items) > config.max_bsu_per_day:
            constraint_penalty += (
                len(daily.items) - config.max_bsu_per_day
            ) * 5.0

        if daily.total_volume > config.vehicle_capacity_kg:
            overload_ratio = (
                daily.total_volume - config.vehicle_capacity_kg
            ) / config.vehicle_capacity_kg

            constraint_penalty += overload_ratio * 5.0

        for item in daily.items:
            scheduled_ids.append(item.bsu_id)

    scheduled_set = set(scheduled_ids)
    chromosome_set = {bsu.bsu_id for bsu in chromosome}

    missing_bsu_count = len(chromosome_set - scheduled_set)
    duplicate_bsu_count = len(scheduled_ids) - len(scheduled_set)

    if missing_bsu_count > 0:
        constraint_penalty += missing_bsu_count * 10.0

    if duplicate_bsu_count > 0:
        constraint_penalty += duplicate_bsu_count * 10.0

    # fitness total
    fitness = (
        config.weight_distance * distance_score
        + config.weight_district * district_penalty
        + config.weight_volume * volume_penalty
        + constraint_penalty
    )

    return FitnessDetail(
        distance_score=distance_score,
        district_penalty=district_penalty,
        volume_penalty=volume_penalty,
        constraint_penalty=constraint_penalty,
        fitness=fitness,
        total_distance=total_distance,
        mixed_district_days=mixed_district_days,
        used_days=len(schedule),
        scheduled_bsu_count=len(scheduled_set),
        missing_bsu_count=missing_bsu_count,
        duplicate_bsu_count=duplicate_bsu_count,
        empty_days_count=empty_days_count,
    )