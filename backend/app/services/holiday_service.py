from calendar import monthrange
from datetime import date

import holidays


def fetch_indonesia_holidays(tahun: int, bulan: int):
    id_holidays = holidays.country_holidays("ID", years=[tahun])
    _, last_day = monthrange(tahun, bulan)

    result = []
    for day in range(1, last_day + 1):
        current_date = date(tahun, bulan, day)
        if current_date in id_holidays:
            result.append({
                "tanggal": current_date.isoformat(),
                "nama": id_holidays.get(current_date),
            })

    return result


def is_indonesia_holiday(schedule_date: date) -> tuple[bool, str | None]:
    id_holidays = holidays.country_holidays("ID", years=[schedule_date.year])
    if schedule_date in id_holidays:
        return True, id_holidays.get(schedule_date)

    return False, None