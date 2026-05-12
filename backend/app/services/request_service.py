from fastapi import HTTPException
from google.cloud import firestore
from datetime import datetime, timezone
from database import db
from models.request_models import ScheduleRequestInput
from utils.firestore_helper import get_bsu_by_uid

def fetch_all_schedule_requests():
    bsu_docs = db.collection("bsu").stream()
    bsu_map = {}
    for b_doc in bsu_docs:
        b_data = b_doc.to_dict()
        # uid adalah kunci relasi utama
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
        # uid adalah kunci relasi — bsu_id hanya untuk display
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
    # uid adalah kunci relasi untuk mencari slot di jadwal
    uid = req_data.get("uid")
    
    if jenis in ["reschedule", "batal"]:
        jadwal_doc_id = f"{tahun}_{bulan}"
        jadwal_ref = db.collection("jadwal").document(jadwal_doc_id)
        jadwal_doc = jadwal_ref.get()
        
        if jadwal_doc.exists:
            jadwal_data = jadwal_doc.to_dict()
            hari_list = jadwal_data.get("hari_list", [])
            
            old_date = req_data.get("tanggal_lama")
            if old_date:
                for h in hari_list:
                    if h["tanggal"] == old_date:
                        # Hapus slot milik user ini menggunakan uid
                        h["slots"] = [s for s in h["slots"] if s.get("uid") != uid]
                        h["total_vol"] = sum(s.get("vol_kg", 0.0) for s in h["slots"])
            
            if jenis == "reschedule":
                new_date = req_data.get("tanggal_baru")
                if new_date:
                    target_h = next((h for h in hari_list if h["tanggal"] == new_date), None)
                    
                    # Ambil data BSU via uid (direct document get)
                    bsu_data = get_bsu_by_uid(uid)
                    
                    if bsu_data:
                        lat, lon = 0.0, 0.0
                        coord = bsu_data.get("coordinate")
                        if coord and isinstance(coord, list) and len(coord) >= 2:
                            lat = float(coord[0]) if coord[0] is not None else 0.0
                            lon = float(coord[1]) if coord[1] is not None else 0.0
                            
                        slot_data = {
                            "uid": uid,           # relasi utama
                            "bsu_id": bsu_data.get("bsu_id", uid),  # display only
                            "nama": bsu_data.get("bsu_name", ""),
                            "kecamatan": bsu_data.get("kecamatan", ""),
                            "vol_kg": float(req_data.get("estimasi_vol_kg", 0.0)),
                            "lat": lat,
                            "lon": lon,
                            "req_terpenuhi": True
                        }
                        
                        if target_h:
                            target_h["slots"].append(slot_data)
                            target_h["total_vol"] += slot_data["vol_kg"]
                        else:
                            hari_list.append({
                                "tanggal": new_date,
                                "total_vol": slot_data["vol_kg"],
                                "slots": [slot_data]
                            })
                            hari_list.sort(key=lambda x: x["tanggal"])
            
            jadwal_ref.update({
                "hari_list": hari_list,
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
    
    # uid adalah kunci relasi utama; bsu_id hanya untuk display
    bsu_display_id = bsu_data.get("bsu_id", uid)
    
    # Validate period
    periode_doc = db.collection("periode_pengajuan").document(f"{request.tahun}_{request.bulan}").get()
    if not periode_doc.exists or not periode_doc.to_dict().get("is_open", False):
        raise HTTPException(status_code=403, detail="Periode pengajuan untuk bulan dan tahun ini sedang ditutup")

    # Validate H-5 for reschedule/batal
    if request.jenis_pengajuan in ["reschedule", "batal"]:
        if not request.tanggal_lama:
            raise HTTPException(status_code=400, detail="tanggal_lama is required for reschedule or batal")
        
        try:
            jadwal_date = datetime.strptime(request.tanggal_lama, "%Y-%m-%d").date()
            today_date = datetime.now(timezone.utc).date()
            
            diff = (jadwal_date - today_date).days
            if diff < 5:
                raise HTTPException(status_code=403, detail="Perubahan jadwal tidak bisa dilakukan karena sudah H-5 pengangkutan")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format for tanggal_lama. Use YYYY-MM-DD")

    doc_id = f"{request.tahun}_{request.bulan}_{uid}_{int(datetime.now().timestamp())}"
    
    request_data = {
        "request_id": doc_id,
        "uid": uid,                          # relasi utama
        "bsu_id": bsu_display_id,            # display only
        "tahun": request.tahun,
        "bulan": request.bulan,
        "tanggal_request": request.tanggal_request,
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
    
    return {**request_data, "created_at": None, "updated_at": None}

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
