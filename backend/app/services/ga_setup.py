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

    schedule: List[DailySchedule] = []

    current_day_index = 0
    current_items: List[BSU] = []
    current_volume = 0.0

    for bsu in chromosome:
        if current_day_index >= len(working_days):
            break

        will_exceed_quota = len(current_items) >= config.max_bsu_per_day

        will_exceed_capacity = (
            current_volume + bsu.estimated_volume_kg
            > config.vehicle_capacity_kg
        )

        # Jika item saat ini sudah ada dan BSU baru menyebabkan constraint dilanggar,
        # maka jadwal hari ini disimpan, lalu lanjut ke hari berikutnya.
        if current_items and (will_exceed_quota or will_exceed_capacity):
            tanggal = working_days[current_day_index]
            total_distance = calculate_route_distance(current_items)
            kecamatan_list = sorted(list({item.kecamatan for item in current_items}))

            schedule.append(
                DailySchedule(
                    tanggal=tanggal,
                    items=current_items,
                    total_volume=current_volume,
                    total_distance=total_distance,
                    kecamatan_list=kecamatan_list,
                )
            )

            current_day_index += 1
            current_items = []
            current_volume = 0.0

        # jika hari masih tersedia, masukkan bsu
        if current_day_index < len(working_days):
            current_items.append(bsu)
            current_volume += bsu.estimated_volume_kg

    # simpan sisa item terakhir
    if current_items and current_day_index < len(working_days):
        tanggal = working_days[current_day_index]
        total_distance = calculate_route_distance(current_items)
        kecamatan_list = sorted(list({item.kecamatan for item in current_items}))

        schedule.append(
            DailySchedule(
                tanggal=tanggal,
                items=current_items,
                total_volume=current_volume,
                total_distance=total_distance,
                kecamatan_list=kecamatan_list,
            )
        )

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

        if total_distance > max_distance:
            max_distance = total_distance

    # Mencegah pembagian dengan nol
    if max_distance == 0:
        return 1.0

    return max_distance

# hitung fitness
def calculate_fitness_detail(
    chromosome: List[BSU],
    config: ScheduleConfig,
    max_distance: float,
    working_days: Optional[List[date]] = None
) -> FitnessDetail:

    # Rumus: 
    # Fitness = w_jarak × DistanceScore + w_kercamatan × DistrictPenalty + w_unschedule × UnscheduledPenalty

    schedule = decode_chromosome(chromosome, config, working_days)

    total_distance = sum(daily.total_distance for daily in schedule)

    # jarak -> semakin kecil jarak semakin kecil score
    distance_score = total_distance / max_distance
    distance_score = min(1.0, distance_score)

    # district penalty -> penalti satu hari lebih dari 1 kecamatan
    used_days = len(schedule)

    mixed_district_days = 0

    for daily in schedule:
        if len(daily.kecamatan_list) > 1:
            mixed_district_days += 1

    if used_days == 0:
        district_penalty = 1.0
    else:
        district_penalty = mixed_district_days / used_days

    # unscheduled bsu -> penalti BSU yang tidak masuk jadwal.
    scheduled_bsu_count = sum(len(daily.items) for daily in schedule)
    total_bsu_count = len(chromosome)
    unscheduled_bsu_count = total_bsu_count - scheduled_bsu_count

    if total_bsu_count == 0:
        unscheduled_penalty = 1.0
    else:
        unscheduled_penalty = unscheduled_bsu_count / total_bsu_count

    # final fitness
    fitness = (
        config.weight_distance * distance_score
        + config.weight_district * district_penalty
        + config.weight_unscheduled * unscheduled_penalty
    )

    return FitnessDetail(
        distance_score=distance_score,
        district_penalty=district_penalty,
        unscheduled_penalty=unscheduled_penalty,
        fitness=fitness,
        total_distance=total_distance,
        mixed_district_days=mixed_district_days,
        used_days=used_days,
        scheduled_bsu_count=scheduled_bsu_count,
        unscheduled_bsu_count=unscheduled_bsu_count,
    )


