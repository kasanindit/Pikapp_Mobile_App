from fastapi import HTTPException
from google.cloud import firestore
from datetime import datetime, date
from calendar import monthrange
import math
from database import db
from models.request_models import GenerateScheduleRequest
from models.ga_models import BSU, ScheduleConfig
from services.genetic_algorithm import generate_schedule_with_ga
from utils.firestore_helper import get_bsu_by_uid

FINAL_SKIP_STATUSES = {"canceled", "failed", "rescheduled"}

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

def _collect_previous_month_volumes(tahun: int, bulan: int) -> dict[str, float]:
    prev_tahun, prev_bulan = _previous_month(tahun, bulan)
    volumes: dict[str, float] = {}
    explicit_history_uids: set[str] = set()

    for doc in db.collection("pickup_history").stream():
        data = doc.to_dict()
        tanggal = _parse_iso_date(data.get("tanggal"))
        if not tanggal or tanggal.year != prev_tahun or tanggal.month != prev_bulan:
            continue

        uid = data.get("uid") or data.get("bsu_id")
        if not uid:
            continue

        explicit_history_uids.add(uid)
        status = data.get("status")
        if status == "completed":
            volumes[uid] = volumes.get(uid, 0.0) + _safe_float(data.get("vol_kg"))
        elif status in FINAL_SKIP_STATUSES:
            volumes[uid] = 0.0

    previous_schedule = db.collection("jadwal").document(f"{prev_tahun}_{prev_bulan}").get()
    if previous_schedule.exists:
        schedule_data = previous_schedule.to_dict()
        if schedule_data.get("status") == "published":
            for hari in schedule_data.get("hari_list", []):
                for slot in hari.get("slots", []):
                    uid = slot.get("uid") or slot.get("bsu_id")
                    if not uid or uid in explicit_history_uids:
                        continue
                    volumes[uid] = volumes.get(uid, 0.0) + _safe_float(slot.get("vol_kg"))

    return volumes

def _build_active_bsu_input(tahun: int, bulan: int) -> list[BSU]:
    previous_volumes = _collect_previous_month_volumes(tahun, bulan)
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

def create_generated_schedule(request: GenerateScheduleRequest):
    tahun = request.tahun
    bulan = request.bulan

    start_date, end_date = _month_bounds(tahun, bulan)
    bsu_list = _build_active_bsu_input(tahun, bulan)

    if not bsu_list:
        raise HTTPException(status_code=400, detail="No active BSU found for schedule generation.")

    try:
        kapasitas_harian = request.jumlah_kendaraan * request.kapasitas_kendaraan
        max_bsu_harian = request.jumlah_kendaraan * request.kuota_kunjungan
        config = ScheduleConfig(
            start_date=start_date,
            end_date=end_date,
            max_bsu_per_day=max_bsu_harian,
            vehicle_capacity_kg=kapasitas_harian,
            use_indonesian_holidays=False
        )
        ga_result = generate_schedule_with_ga(
            bsu_list=bsu_list,
            config=config,
            population_size=80,
            generations=250
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate schedule: {str(e)}")

    formatted_jadwal = _format_ga_schedule(ga_result)
    
    doc_id = f"{tahun}_{bulan}"
    jadwal_data = {
        "tahun": tahun,
        "bulan": bulan,
        "status": "draft",
        "hari_list": formatted_jadwal,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP
    }
    
    db.collection("jadwal").document(doc_id).set(jadwal_data)
    
    return {
        "tahun": tahun,
        "bulan": bulan,
        "status": "draft",
        "hari_list": formatted_jadwal
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
    
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Schedule draft not found")
        
    doc_ref.update({
        "status": "published",
        "hari_list": hari_list,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

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
    
    if data.get("status") != "published":
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
    if jadwal_data.get("status") != "published":
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
                "change_request_status": change_request.get("status") if change_request else None,
                "change_request_id": change_request.get("request_id") if change_request else None,
                "change_request_type": change_request.get("jenis_pengajuan") if change_request else None,
                "tanggal_baru": change_request.get("tanggal_baru") if change_request else None,
                "alasan_reschedule": change_request.get("alasan") if change_request else None,
                "alasan_pengajuan": change_request.get("alasan") if change_request else None,
            })

    return my_schedule
