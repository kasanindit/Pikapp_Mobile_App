from __future__ import annotations

import math
from datetime import date, timedelta
from typing import List, Optional

from models.ga_models_ver4 import BSU, DailySchedule, ScheduleConfig, SlotWarning

try:
    import holidays  # type: ignore[import]
except ImportError:
    holidays = None


def get_working_days(
    start_date: date,
    end_date: date,
    use_indonesian_holidays: bool = True,
    additional_holidays: Optional[List[date]] = None,
) -> List[date]:
    working_days: List[date] = []
    current_date = start_date
    additional_holidays_set = set(additional_holidays or [])
    indonesia_holidays = set()

    if use_indonesian_holidays:
        if holidays is None:
            raise ImportError(
                "Library 'holidays' belum terinstall. Install dengan: pip install holidays"
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


# def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
#     earth_radius_km = 6371.0
#     lat1_rad = math.radians(lat1)
#     lon1_rad = math.radians(lon1)
#     lat2_rad = math.radians(lat2)
#     lon2_rad = math.radians(lon2)

#     dlat = lat2_rad - lat1_rad
#     dlon = lon2_rad - lon1_rad

#     a = (
#         math.sin(dlat / 2) ** 2
#         + math.cos(lat1_rad)
#         * math.cos(lat2_rad)
#         * math.sin(dlon / 2) ** 2
#     )
#     a = max(0.0, min(1.0, a))
#     return 2 * earth_radius_km * math.asin(math.sqrt(a))


# def calculate_route_distance(items: List[BSU]) -> float:
#     if len(items) <= 1:
#         return 0.0

#     return sum(
#         haversine_distance(
#             items[index].latitude,
#             items[index].longitude,
#             items[index + 1].latitude,
#             items[index + 1].longitude,
#         )
#         for index in range(len(items) - 1)
#     )


def build_daily_schedule(tanggal: date, items: List[BSU]) -> DailySchedule:
    return DailySchedule(
        tanggal=tanggal,
        items=items,
        total_volume=sum(item.estimated_volume_kg for item in items),
        # total_distance=calculate_route_distance(items),
        kecamatan_list=sorted({item.kecamatan for item in items}),
    )


def build_preflight_warnings(
    active_bsu_count: int,
    working_day_count: int,
    config: ScheduleConfig,
) -> List[SlotWarning]:
    warnings: List[SlotWarning] = []
    total_slot = working_day_count * config.max_bsu_per_day

    if active_bsu_count > total_slot:
        warnings.append(
            SlotWarning(
                code="BSU_EXCEEDS_MONTHLY_SLOT",
                message=(
                    "Jumlah BSU aktif melebihi kapasitas kunjungan bulan ini. "
                    "Draft tetap dibuat, tetapi beberapa hari mungkin melewati batas kunjungan."
                ),
                details={
                    "active_bsu_count": active_bsu_count,
                    "working_day_count": working_day_count,
                    "max_bsu_per_day": config.max_bsu_per_day,
                    "total_slot": total_slot,
                    "excess_bsu_count": active_bsu_count - total_slot,
                },
            )
        )

    if active_bsu_count < working_day_count:
        warnings.append(
            SlotWarning(
                code="BSU_LESS_THAN_WORKING_DAYS",
                message=(
                    "Jumlah BSU aktif lebih sedikit dari jumlah hari kerja. "
                    "Beberapa hari kerja dapat kosong."
                ),
                details={
                    "active_bsu_count": active_bsu_count,
                    "working_day_count": working_day_count,
                },
            )
        )

    return warnings
