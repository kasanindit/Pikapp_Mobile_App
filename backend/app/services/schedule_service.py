from fastapi import HTTPException
from google.cloud import firestore
from datetime import datetime, date
from calendar import monthrange
import math
import time
from database import db
from models.request_models import GenerateScheduleRequest
from models.ga_models_ver4 import BSU, ScheduleConfig
# from services.genetic_algorithm_ver4 import generate_schedule_with_ga_v4
from services.ga_scheduler_ver5 import generate_schedule_with_ga_v5
# from models.ga_models import BSU, ScheduleConfig
# from services.genetic_algorithm import generate_schedule_with_ga
from utils.firestore_helper import get_bsu_by_uid

FINAL_SKIP_STATUSES = {"canceled", "failed", "rescheduled"}
VISIBLE_SCHEDULE_STATUSES = {"published", "finalized"}

# Pengaturan sementara untuk mencoba backend/app/services/genetic_algorithm.py
# GA_POPULATION_SIZE = 150
# GA_GENERATIONS = 200
# GA_CROSSOVER_RATE = 0.8
# GA_MUTATION_RATE = 0.05
# GA_ELITISM_COUNT = 2
# GA_RANDOM_SEED = None

def _parse_iso_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

def _previous_month(tahun: int, bulan: int) -> tuple[int, int]:
    if bulan == 1:
        return tahun - 1, 12
    return tahun, bulan - 1

def _month_bounds(tahun: int, bulan: int) -> tuple[date, date]:
    last_day = monthrange(tahun, bulan)[1]
    return date(tahun, bulan, 1), date(tahun, bulan, last_day)

def _safe_float(value, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default

def _extract_coordinates(data: dict) -> tuple[float, float]:
    coord = data.get("coordinate")
    if coord and isinstance(coord, list) and len(coord) >= 2:
        return _safe_float(coord[0]), _safe_float(coord[1])
    return 0.0, 0.0

def _remember_latest_volume(
    candidates: dict[str, tuple[date, int, float]],
    uid: str | None,
    tanggal: date | None,
    volume: float,
    source_priority: int,
) -> None:
    if not uid or not tanggal:
        return

    current = candidates.get(uid)
    candidate = (tanggal, source_priority, volume)
    if current is None or (candidate[0], candidate[1]) > (current[0], current[1]):
        candidates[uid] = candidate

def _collect_latest_historical_volumes(
    tahun: int,
    bulan: int,
    excluded_history_sources: set[str] | None = None,
) -> dict[str, float]:
    start_date, _ = _month_bounds(tahun, bulan)
    candidates: dict[str, tuple[date, int, float]] = {}
    excluded_history_sources = excluded_history_sources or set()

    for schedule_doc in db.collection("jadwal").stream():
        schedule_data = schedule_doc.to_dict() or {}
        if schedule_data.get("status") not in VISIBLE_SCHEDULE_STATUSES:
            continue

        for hari in schedule_data.get("hari_list", []):
            tanggal = _parse_iso_date(hari.get("tanggal"))
            if not tanggal or tanggal >= start_date:
                continue

            for slot in hari.get("slots", []):
                _remember_latest_volume(
                    candidates=candidates,
                    uid=slot.get("uid") or slot.get("bsu_id"),
                    tanggal=tanggal,
                    volume=_safe_float(slot.get("vol_kg")),
                    source_priority=1,
                )

    # menimpa slot jadwal pada tanggal yang sama
    for doc in db.collection("pickup_history").stream():
        data = doc.to_dict() or {}
        if data.get("source") in excluded_history_sources:
            continue

        tanggal = _parse_iso_date(data.get("tanggal"))
        if not tanggal or tanggal >= start_date:
            continue

        uid = data.get("uid") or data.get("bsu_id")
        if not uid:
            continue

        status = data.get("status")
        if status == "completed":
            volume = _safe_float(data.get("vol_kg"))
        elif status in FINAL_SKIP_STATUSES:
            volume = 0.0
        else:
            continue

        _remember_latest_volume(
            candidates=candidates,
            uid=uid,
            tanggal=tanggal,
            volume=volume,
            source_priority=2,
        )

    return {
        uid: volume
        for uid, (_, _, volume) in candidates.items()
    }

def _build_active_bsu_input(tahun: int, bulan: int) -> list[BSU]:
    previous_volumes = _collect_latest_historical_volumes(tahun, bulan)
    bsu_list: list[BSU] = []
    seen_uids: set[str] = set()

    for doc in db.collection("bsu").stream():
        data = doc.to_dict()
        uid = data.get("uid")
        if not uid or uid in seen_uids:
            continue
        if data.get("is_active", True) is False:
            continue

        seen_uids.add(uid)
        lat, lon = _extract_coordinates(data)
        bsu_list.append(BSU(
            bsu_id=uid,
            nama_bsu=data.get("bsu_name", "Unknown"),
            kecamatan=data.get("kecamatan", "Unknown"),
            estimated_volume_kg=previous_volumes.get(uid, 0.0),
            latitude=lat,
            longitude=lon,
            is_active=True
        ))

    return bsu_list

def _format_ga_schedule(result) -> list[dict]:
    formatted = []
    for daily in result.best_schedule:
        day = {
            "tanggal": daily.tanggal.isoformat(),
            "total_vol": daily.total_volume,
            "slots": []
        }

        for item in daily.items:
            day["slots"].append({
                "uid": item.bsu_id,
                "bsu_id": item.bsu_id,
                "nama": item.nama_bsu,
                "kecamatan": item.kecamatan,
                "vol_kg": item.estimated_volume_kg,
                "lat": item.latitude,
                "lon": item.longitude,
                "req_terpenuhi": False
            })

        formatted.append(day)

    return formatted

def _format_ga_debug(
    result,
    bsu_list: list[BSU],
    config: ScheduleConfig | None = None,
    execution_time_seconds: float | None = None,
) -> dict:
    detail = result.fitness_detail
    fitness_history = getattr(result, "fitness_history", []) or []
    initial_fitness = fitness_history[0] if fitness_history else result.best_fitness
    final_fitness = result.best_fitness
    fitness_improvement = final_fitness - initial_fitness
    kecamatan_penalty = getattr(
        detail,
        "kecamatan_penalty",
        getattr(detail, "district_penalty", 0.0)
    )
    total_penalty = getattr(
        detail,
        "total_penalty",
        getattr(detail, "constraint_penalty", 0.0)
    )
    unscheduled_bsu_count = getattr(
        detail,
        "unscheduled_bsu_count",
        getattr(detail, "missing_bsu_count", 0)
    )
    unscheduled_penalty = getattr(
        detail,
        "unscheduled_penalty",
        getattr(detail, "constraint_penalty", 0.0)
    )
    fitness_history_sample = [
        {
            "generation": snapshot.generation,
            "best_fitness": snapshot.best_fitness,
            "total_penalty": snapshot.total_penalty,
            "capacity_penalty": snapshot.capacity_penalty,
            "kecamatan_penalty": snapshot.kecamatan_penalty,
            "max_bsu_penalty": snapshot.max_bsu_penalty,
            "empty_days_count": snapshot.empty_days_count,
            "overloaded_days_count": snapshot.overloaded_days_count,
            "over_quota_days_count": snapshot.over_quota_days_count,
            "mixed_district_days": snapshot.mixed_district_days,
        }
        for snapshot in getattr(result, "generation_snapshots", [])
    ]
    coverage_penalty = getattr(detail, "coverage_penalty", None)
    capacity_penalty = getattr(detail, "capacity_penalty", None)
    max_bsu_penalty = getattr(detail, "max_bsu_penalty", None)
    penalty_weights = {
        "coverage": getattr(config, "coverage_weight", 0.0) if config else 0.0,
        "capacity": getattr(config, "capacity_weight", 0.0) if config else 0.0,
        "max_bsu": getattr(config, "max_bsu_weight", 0.0) if config else 0.0,
        "kecamatan": getattr(config, "kecamatan_weight", 0.0) if config else 0.0,
    }
    constraint_penalties = [
        {
            "code": "coverage",
            "label": "Coverage hari kerja",
            "penalty": coverage_penalty,
            "weight": penalty_weights["coverage"],
            "weighted_penalty": (coverage_penalty or 0.0) * penalty_weights["coverage"],
            "affected_count": getattr(detail, "empty_days_count", None),
        },
        {
            "code": "capacity",
            "label": "Kapasitas kendaraan",
            "penalty": capacity_penalty,
            "weight": penalty_weights["capacity"],
            "weighted_penalty": (capacity_penalty or 0.0) * penalty_weights["capacity"],
            "affected_count": getattr(detail, "overloaded_days_count", None),
        },
        {
            "code": "max_bsu",
            "label": "Maksimal BSU per hari",
            "penalty": max_bsu_penalty,
            "weight": penalty_weights["max_bsu"],
            "weighted_penalty": (max_bsu_penalty or 0.0) * penalty_weights["max_bsu"],
            "affected_count": getattr(detail, "over_quota_days_count", None),
        },
        {
            "code": "kecamatan",
            "label": "Kesamaan kecamatan",
            "penalty": kecamatan_penalty,
            "weight": penalty_weights["kecamatan"],
            "weighted_penalty": (kecamatan_penalty or 0.0) * penalty_weights["kecamatan"],
            "affected_count": getattr(detail, "mixed_district_days", None),
        },
    ]

    return {
        "execution_time_seconds": execution_time_seconds,
        "execution_time_ms": round(execution_time_seconds * 1000, 2) if execution_time_seconds is not None else None,
        "active_bsu_count": len(bsu_list),
        "included_bsu": [
            {
                "uid": bsu.bsu_id,
                "nama": bsu.nama_bsu,
                "kecamatan": bsu.kecamatan,
                "vol_kg": bsu.estimated_volume_kg
            }
            for bsu in bsu_list
        ],
        "best_fitness": result.best_fitness,
        "generation_found": result.generation_found + 1,
        "generation_count": len(fitness_history),
        "initial_fitness": initial_fitness,
        "final_fitness": final_fitness,
        "fitness_improvement": fitness_improvement,
        "fitness_history_sample": fitness_history_sample,
        "constraint_penalties": constraint_penalties,
        "ga_summary": {
            "best_fitness": result.best_fitness,
            "generation_found": result.generation_found + 1,
            "generation_count": len(fitness_history),
            "scheduled_bsu_count": detail.scheduled_bsu_count,
            "unscheduled_bsu_count": unscheduled_bsu_count,
            "total_penalty": total_penalty,
            "capacity_penalty": capacity_penalty,
            "kecamatan_penalty": kecamatan_penalty,
            "max_bsu_penalty": max_bsu_penalty,
            "empty_days_count": getattr(detail, "empty_days_count", None),
            "overloaded_days_count": getattr(detail, "overloaded_days_count", None),
            "over_quota_days_count": getattr(detail, "over_quota_days_count", None),
            "mixed_district_days": detail.mixed_district_days,
        },
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "details": warning.details
            }
            for warning in getattr(result, "warnings", [])
        ],
        "working_day_count": getattr(result, "working_day_count", None),
        "total_slot": getattr(result, "total_slot", None),
        "max_bsu_per_day": getattr(result, "max_bsu_per_day", None),
        "vehicle_capacity_kg": getattr(result, "vehicle_capacity_kg", None),
        "mixed_district_days": detail.mixed_district_days,
        "used_days": detail.used_days,
        "scheduled_bsu_count": detail.scheduled_bsu_count,
        "unscheduled_bsu_count": unscheduled_bsu_count,
        "total_distance": getattr(detail, "total_distance", None),
        "district_penalty": kecamatan_penalty,
        "unscheduled_penalty": unscheduled_penalty,
        "volume_penalty": getattr(detail, "volume_penalty", None),
        "constraint_penalty": getattr(detail, "constraint_penalty", total_penalty),
        "coverage_penalty": coverage_penalty,
        "capacity_penalty": capacity_penalty,
        "max_bsu_penalty": max_bsu_penalty,
        "kecamatan_penalty": kecamatan_penalty,
        "total_penalty": total_penalty,
        "missing_bsu_count": getattr(detail, "missing_bsu_count", None),
        "duplicate_bsu_count": getattr(detail, "duplicate_bsu_count", None),
        "empty_days_count": getattr(detail, "empty_days_count", None),
        "overloaded_days_count": getattr(detail, "overloaded_days_count", None),
        "over_quota_days_count": getattr(detail, "over_quota_days_count", None),
    }

def create_generated_schedule(request: GenerateScheduleRequest):
    tahun = request.tahun
    bulan = request.bulan

    start_date, end_date = _month_bounds(tahun, bulan)
    bsu_list = _build_active_bsu_input(tahun, bulan)

    if not bsu_list:
        raise HTTPException(status_code=400, detail="No active BSU found for schedule generation.")

    try:
        kapasitas_harian = max(1.0, request.kapasitas_kendaraan)
        max_bsu_harian = max(1, request.kuota_kunjungan)
        config = ScheduleConfig(
            start_date=start_date,
            end_date=end_date,
            max_bsu_per_day=max_bsu_harian,
            vehicle_capacity_kg=kapasitas_harian,
            use_indonesian_holidays=True
        )
 
        ga_start_time = time.perf_counter()
        ga_result = generate_schedule_with_ga_v5(
            bsu_list=bsu_list,
            config=config
        )
        ga_execution_seconds = time.perf_counter() - ga_start_time
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate schedule: {str(e)}")

    formatted_jadwal = _format_ga_schedule(ga_result)
    ga_debug = _format_ga_debug(
        ga_result,
        bsu_list,
        config=config,
        execution_time_seconds=ga_execution_seconds,
    )
    
    doc_id = f"{tahun}_{bulan}"
    jadwal_data = {
        "tahun": tahun,
        "bulan": bulan,
        "status": "draft",
        "hari_list": formatted_jadwal,
        "ga_debug": ga_debug,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP
    }
    
    db.collection("jadwal").document(doc_id).set(jadwal_data)
    
    return {
        "tahun": tahun,
        "bulan": bulan,
        "status": "draft",
        "hari_list": formatted_jadwal,
        "ga_debug": ga_debug
    }

def fetch_admin_schedule(tahun: int, bulan: int):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("jadwal").document(doc_id).get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
    return doc.to_dict()

def modify_schedule_draft(tahun: int, bulan: int, hari_list: list):
    doc_id = f"{tahun}_{bulan}"
    doc_ref = db.collection("jadwal").document(doc_id)
    
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Schedule draft not found")
        
    doc_ref.update({
        "hari_list": hari_list,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def set_schedule_published(tahun: int, bulan: int, hari_list: list):
    doc_id = f"{tahun}_{bulan}"
    doc_ref = db.collection("jadwal").document(doc_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule draft not found")

    data = doc.to_dict()
    if data.get("status") == "finalized":
        raise HTTPException(status_code=400, detail="Finalized schedule cannot be reopened for user review")

    doc_ref.update({
        "status": "published",
        "hari_list": hari_list,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def set_schedule_finalized(tahun: int, bulan: int):
    doc_id = f"{tahun}_{bulan}"
    doc_ref = db.collection("jadwal").document(doc_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")

    data = doc.to_dict()
    if data.get("status") != "published":
        raise HTTPException(status_code=400, detail="Only a published schedule can be finalized")

    doc_ref.update({
        "status": "finalized",
        "updated_at": firestore.SERVER_TIMESTAMP
    })

    updated_doc = doc_ref.get()
    return updated_doc.to_dict()

def remove_schedule_slot(tahun: int, bulan: int, tanggal: str, uid: str):
    doc_id = f"{tahun}_{bulan}"
    doc_ref = db.collection("jadwal").document(doc_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
    jadwal_data = doc.to_dict()
    hari_list = jadwal_data.get("hari_list", [])
    
    found = False
    for h in hari_list:
        if h["tanggal"] == tanggal:
            original_len = len(h["slots"])
            # Hapus slot berdasarkan uid (relasi utama)
            h["slots"] = [s for s in h["slots"] if s.get("uid") != uid]
            
            if len(h["slots"]) < original_len:
                found = True
                h["total_vol"] = sum(s.get("vol_kg", 0.0) for s in h["slots"])
            break
            
    if not found:
        raise HTTPException(status_code=404, detail=f"Slot for uid {uid} on {tanggal} not found")
        
    doc_ref.update({
        "hari_list": hari_list,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

def remove_monthly_schedule(tahun: int, bulan: int):
    doc_id = f"{tahun}_{bulan}"
    doc_ref = db.collection("jadwal").document(doc_id)
    
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
    doc_ref.delete()

def fetch_published_schedule(tahun: int, bulan: int):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("jadwal").document(doc_id).get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found for this period")
        
    data = doc.to_dict()
    
    if data.get("status") not in VISIBLE_SCHEDULE_STATUSES:
        raise HTTPException(status_code=404, detail="Schedule is not published yet")
        
    return data.get("hari_list", [])

def fetch_my_schedule(uid: str, tahun: int, bulan: int):
    bsu_data = get_bsu_by_uid(uid) or {}
    user_identifiers = {
        value for value in [
            uid,
            bsu_data.get("uid"),
            bsu_data.get("bsu_id")
        ] if value
    }

    # Cocokkan jadwal baru (uid) dan jadwal lama (bsu_id/display id).
    doc_id = f"{tahun}_{bulan}"
    jadwal_doc = db.collection("jadwal").document(doc_id).get()

    if not jadwal_doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")

    jadwal_data = jadwal_doc.to_dict()
    schedule_status = jadwal_data.get("status")
    if schedule_status not in VISIBLE_SCHEDULE_STATUSES:
        raise HTTPException(status_code=404, detail="Schedule not published yet")

    hari_list = jadwal_data.get("hari_list", [])
    my_schedule = []

    request_status_by_old_date = {}
    request_docs = (
        db.collection("schedule_requests")
        .where("uid", "==", uid)
        .stream()
    )
    for request_doc in request_docs:
        request_data = request_doc.to_dict()
        request_type = request_data.get("jenis_pengajuan")
        if request_type not in {"reschedule", "batal"}:
            continue

        old_date = request_data.get("tanggal_lama")
        if not old_date:
            continue
        request_status_by_old_date[old_date] = {
            "request_id": request_data.get("request_id"),
            "status": request_data.get("status"),
            "jenis_pengajuan": request_type,
            "tanggal_baru": request_data.get("tanggal_baru"),
            "alasan": request_data.get("alasan"),
        }

    for hari in hari_list:
        # Cari slot milik user ini dari format jadwal lama maupun baru.
        user_slot = next(
            (
                slot for slot in hari.get("slots", [])
                if slot.get("uid") in user_identifiers
                or slot.get("bsu_id") in user_identifiers
            ),
            None
        )

        if user_slot:
            tanggal = hari.get("tanggal")
            change_request = request_status_by_old_date.get(tanggal)
            if not change_request and user_slot.get("rescheduled_from"):
                change_request = {
                    "request_id": user_slot.get("request_id"),
                    "status": "approved",
                    "jenis_pengajuan": "reschedule",
                    "tanggal_baru": tanggal,
                    "alasan": user_slot.get("reschedule_reason"),
                }

            my_schedule.append({
                "tanggal": tanggal,
                "vol_kg": user_slot.get("vol_kg", 0.0),
                "req_terpenuhi": user_slot.get("req_terpenuhi", False),
                "schedule_status": schedule_status,
                "can_request_change": schedule_status == "published",
                "change_request_status": change_request.get("status") if change_request else None,
                "change_request_id": change_request.get("request_id") if change_request else None,
                "change_request_type": change_request.get("jenis_pengajuan") if change_request else None,
                "tanggal_baru": change_request.get("tanggal_baru") if change_request else None,
                "alasan_reschedule": change_request.get("alasan") if change_request else None,
                "alasan_pengajuan": change_request.get("alasan") if change_request else None,
            })

    return my_schedule
