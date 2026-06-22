from fastapi import HTTPException
from google.cloud import firestore
from datetime import datetime, timezone
from database import db
from models.request_models import ScheduleRequestInput
from utils.firestore_helper import get_bsu_by_uid
from services.history_service import write_pickup_history

ALLOWED_REQUEST_TYPES = {"baru", "reschedule", "batal"}

def _parse_schedule_date(value: str | None, field_name: str):
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date format for {field_name}. Use YYYY-MM-DD")

def _schedule_doc_id(schedule_date):
    return f"{schedule_date.year}_{schedule_date.month}"

def _slot_belongs_to_user(slot: dict, uid: str, bsu_display_id: str | None = None) -> bool:
    identifiers = {value for value in [uid, bsu_display_id] if value}
    return slot.get("uid") in identifiers or slot.get("bsu_id") in identifiers

# def _validate_period_is_open(tahun: int, bulan: int):
#     periode_doc = db.collection("periode_pengajuan").document(f"{tahun}_{bulan}").get()
#     if not periode_doc.exists or not periode_doc.to_dict().get("is_open", False):
#         raise HTTPException(status_code=403, detail="Periode pengajuan untuk bulan dan tahun ini sedang ditutup")

def _validate_change_request(uid: str, bsu_display_id: str, request: ScheduleRequestInput):
    old_date = _parse_schedule_date(request.tanggal_lama, "tanggal_lama")
    today_date = datetime.now(timezone.utc).date()

    if (old_date - today_date).days < 2:
        raise HTTPException(status_code=403, detail="Perubahan jadwal tidak bisa dilakukan karena sudah H-2 pengangkutan")

    pending_requests = (
        db.collection("schedule_requests")
        .where("uid", "==", uid)
        .stream()
    )
    for request_doc in pending_requests:
        request_data = request_doc.to_dict()
        if (
            request_data.get("status") == "pending"
            and request_data.get("jenis_pengajuan") in {"reschedule", "batal"}
            and request_data.get("tanggal_lama") == request.tanggal_lama
        ):
            raise HTTPException(status_code=400, detail="Masih ada pengajuan perubahan jadwal yang menunggu persetujuan admin")

    old_doc = db.collection("jadwal").document(_schedule_doc_id(old_date)).get()
    if not old_doc.exists:
        raise HTTPException(status_code=404, detail="Jadwal lama tidak ditemukan")

    old_data = old_doc.to_dict()
    if old_data.get("status") == "finalized":
        raise HTTPException(status_code=403, detail="Jadwal sudah final dan tidak bisa diajukan perubahan")

    if old_data.get("status") != "published":
        raise HTTPException(status_code=403, detail="Jadwal lama belum dipublikasikan")

    old_day = next((h for h in old_data.get("hari_list", []) if h.get("tanggal") == request.tanggal_lama), None)
    if not old_day or not any(_slot_belongs_to_user(slot, uid, bsu_display_id) for slot in old_day.get("slots", [])):
        raise HTTPException(status_code=403, detail="Anda tidak memiliki jadwal pada tanggal tersebut")

    if request.jenis_pengajuan == "reschedule":
        new_date = _parse_schedule_date(request.tanggal_baru, "tanggal_baru")
        target_doc = db.collection("jadwal").document(_schedule_doc_id(new_date)).get()
        if not target_doc.exists:
            raise HTTPException(status_code=403, detail="Jadwal tujuan belum dipublikasikan")

        target_status = target_doc.to_dict().get("status")
        if target_status == "finalized":
            raise HTTPException(status_code=403, detail="Jadwal tujuan sudah final")
        if target_status != "published":
            raise HTTPException(status_code=403, detail="Jadwal tujuan belum dipublikasikan")

def fetch_all_schedule_requests():
    bsu_docs = db.collection("bsu").stream()
    bsu_map = {}
    for b_doc in bsu_docs:
        b_data = b_doc.to_dict()
        
        b_uid = b_data.get("uid")
        if b_uid:
            bsu_map[b_uid] = {
                "bsu_name": b_data.get("bsu_name", ""),
                "kecamatan": b_data.get("kecamatan", ""),
                "address": b_data.get("address", ""),
                "phone_num": b_data.get("phone_num", "")
            }

    docs = db.collection("schedule_requests").stream()
    data = []
    for doc in docs:
        req_data = doc.to_dict()
        uid_req = req_data.get("uid")
        req_data["bsu_detail"] = bsu_map.get(uid_req, {})
        data.append(req_data)
        
    return data

def process_approve_request(request_id: str):
    doc_ref = db.collection("schedule_requests").document(request_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Request not found")
        
    req_data = doc.to_dict()
    jenis = req_data.get("jenis_pengajuan", "baru")
    tahun = req_data.get("tahun")
    bulan = req_data.get("bulan")

    uid = req_data.get("uid")
    
    if jenis in ["reschedule", "batal"]:
        bsu_data = get_bsu_by_uid(uid) or {}
        bsu_display_id = bsu_data.get("bsu_id", uid)
        old_date = _parse_schedule_date(req_data.get("tanggal_lama"), "tanggal_lama")
        old_doc_id = _schedule_doc_id(old_date)
        old_ref = db.collection("jadwal").document(old_doc_id)
        old_doc = old_ref.get()

        if not old_doc.exists:
            raise HTTPException(status_code=404, detail="Jadwal lama tidak ditemukan")

        old_data = old_doc.to_dict()
        if old_data.get("status") == "finalized":
            raise HTTPException(status_code=403, detail="Jadwal sudah final dan tidak bisa diproses sebagai pengajuan perubahan")

        if old_data.get("status") != "published":
            raise HTTPException(status_code=403, detail="Jadwal lama belum dipublikasikan")

        old_hari_list = old_data.get("hari_list", [])
        removed_slot = None
        found = False

        for h in old_hari_list:
            if h.get("tanggal") == req_data.get("tanggal_lama"):
                original_slots = h.get("slots", [])
                kept_slots = []
                for slot in original_slots:
                    if _slot_belongs_to_user(slot, uid, bsu_display_id):
                        removed_slot = slot
                        found = True
                    else:
                        kept_slots.append(slot)

                h["slots"] = kept_slots
                h["total_vol"] = sum(s.get("vol_kg", 0.0) for s in kept_slots)
                break

        if not found:
            raise HTTPException(status_code=404, detail="Slot jadwal lama tidak ditemukan")

        if jenis == "reschedule":
            new_date = _parse_schedule_date(req_data.get("tanggal_baru"), "tanggal_baru")
            new_doc_id = _schedule_doc_id(new_date)
            target_ref = old_ref if new_doc_id == old_doc_id else db.collection("jadwal").document(new_doc_id)
            target_doc = old_doc if new_doc_id == old_doc_id else target_ref.get()

            if not target_doc.exists:
                raise HTTPException(status_code=404, detail="Jadwal tujuan tidak ditemukan")

            target_data = old_data if new_doc_id == old_doc_id else target_doc.to_dict()
            if target_data.get("status") == "finalized":
                raise HTTPException(status_code=403, detail="Jadwal tujuan sudah final")

            if target_data.get("status") != "published":
                raise HTTPException(status_code=403, detail="Jadwal tujuan belum dipublikasikan")

            target_hari_list = old_hari_list if new_doc_id == old_doc_id else target_data.get("hari_list", [])
            slot_data = {
                **(removed_slot or {}),
                "uid": uid,
                "bsu_id": bsu_display_id,
                "vol_kg": float(req_data.get("estimasi_vol_kg", 0.0)),
                # "vol_kg": float((removed_slot or {}).get("vol_kg", 0.0) or 0.0),
                "req_terpenuhi": True,
                "rescheduled_from": req_data.get("tanggal_lama"),
                "request_id": request_id,
                "reschedule_reason": req_data.get("alasan"),
            }

            target_h = next((h for h in target_hari_list if h.get("tanggal") == req_data.get("tanggal_baru")), None)
            if target_h:
                target_h.setdefault("slots", []).append(slot_data)
                target_h["total_vol"] = sum(s.get("vol_kg", 0.0) for s in target_h.get("slots", []))
            else:
                target_hari_list.append({
                    "tanggal": req_data.get("tanggal_baru"),
                    "total_vol": slot_data.get("vol_kg", 0.0),
                    "slots": [slot_data]
                })
                target_hari_list.sort(key=lambda x: x.get("tanggal", ""))

            if new_doc_id != old_doc_id:
                target_ref.update({
                    "hari_list": target_hari_list,
                    "updated_at": firestore.SERVER_TIMESTAMP
                })

            write_pickup_history(
                uid=uid,
                tanggal=req_data.get("tanggal_lama"),
                status="rescheduled",
                slot_data=removed_slot,
                bsu_data=bsu_data,
                tanggal_baru=req_data.get("tanggal_baru"),
                request_id=request_id,
                alasan=req_data.get("alasan"),
                source="admin_request",
            )

        if jenis == "batal":
            write_pickup_history(
                uid=uid,
                tanggal=req_data.get("tanggal_lama"),
                status="canceled",
                slot_data=removed_slot,
                bsu_data=bsu_data,
                request_id=request_id,
                alasan=req_data.get("alasan"),
                source="admin_request",
            )

        old_ref.update({
            "hari_list": old_hari_list,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
            
    doc_ref.update({"status": "approved", "updated_at": firestore.SERVER_TIMESTAMP})

def process_reject_request(request_id: str):
    doc_ref = db.collection("schedule_requests").document(request_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Request not found")
        
    doc_ref.update({"status": "rejected", "updated_at": firestore.SERVER_TIMESTAMP})

def submit_schedule_request(uid: str, request: ScheduleRequestInput):
    bsu_data = get_bsu_by_uid(uid)
    
    if not bsu_data:
        raise HTTPException(status_code=404, detail="BSU not found")

    if request.jenis_pengajuan not in ALLOWED_REQUEST_TYPES:
        raise HTTPException(status_code=400, detail="jenis_pengajuan tidak valid")
    
    bsu_display_id = bsu_data.get("bsu_id", uid)
    
    _validate_change_request(uid, bsu_display_id, request)    

    doc_id = f"{request.tahun}_{request.bulan}_{uid}_{int(datetime.now().timestamp())}"
    
    now = datetime.now(timezone.utc)
    
    request_data = {
        "request_id": doc_id,
        "uid": uid,                         
        "bsu_id": bsu_display_id,
        "tahun": request.tahun,
        "bulan": request.bulan,
        "estimasi_vol_kg": request.estimasi_vol_kg,
        "jenis_pengajuan": request.jenis_pengajuan,
        "tanggal_lama": request.tanggal_lama,
        "tanggal_baru": request.tanggal_baru,
        "alasan": request.alasan,
        "status": "pending",
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP
    }
    
    db.collection("schedule_requests").document(doc_id).set(request_data)
    
    return {
        **request_data,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }

def remove_schedule_request(uid: str, request_id: str):
    doc_ref = db.collection("schedule_requests").document(request_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Request not found")
        
    data = doc.to_dict()
    
    if data.get("uid") != uid:
        raise HTTPException(status_code=403, detail="Forbidden - You can only delete your own requests")
        
    if data.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Cannot delete request that is already processed (approved/rejected)")
        
    doc_ref.delete()
