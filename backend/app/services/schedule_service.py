from fastapi import HTTPException
from google.cloud import firestore
from datetime import date
import math
from database import db
from models.request_models import GenerateScheduleRequest
from services.ga_models import jalankan_ga, format_jadwal, BSU
from utils.firestore_helper import get_bsu_by_uid

def create_generated_schedule(request: GenerateScheduleRequest):
    tahun = request.tahun
    bulan = request.bulan
    
    req_docs = db.collection("schedule_requests").where("tahun", "==", tahun).where("bulan", "==", bulan).stream()
    
    bsu_requests = {}
    requested_bsu_ids = set()
    estimasi_map = {}
    
    for doc in req_docs:
        data = doc.to_dict()
        
        if data.get("status", "approved") != "approved":
            continue
        if data.get("jenis_pengajuan", "baru") != "baru":
            continue

        # uid adalah kunci relasi utama (bsu_id hanya display)
        uid = data.get("uid")
        if not uid:
            continue
        requested_bsu_ids.add(uid)
        estimasi_map[uid] = data.get("estimasi_vol_kg", 0.0)
        
        tgl_str = data.get("tanggal_request")
        if tgl_str:
            try:
                y, m, d = map(int, tgl_str.split('-'))
                bsu_requests[uid] = date(y, m, d)
            except:
                pass
                
    if not requested_bsu_ids:
        raise HTTPException(status_code=400, detail="No schedule requests found for this period.")
        
    bsu_list = []
    seen_ids = set()
    bsu_docs = db.collection("bsu").stream()
    
    for doc in bsu_docs:
        data = doc.to_dict()
        # uid adalah primary identifier, bsu_id hanya untuk display
        uid = data.get("uid")
        if not uid:
            continue
        
        if uid in requested_bsu_ids and uid not in seen_ids:
            seen_ids.add(uid)
            lat, lon = 0.0, 0.0
            coord = data.get("coordinate")
            if coord and isinstance(coord, list) and len(coord) >= 2:
                try:
                    lat = float(coord[0]) if coord[0] is not None else 0.0
                    lon = float(coord[1]) if coord[1] is not None else 0.0
                    if math.isnan(lat) or math.isinf(lat): lat = 0.0
                    if math.isnan(lon) or math.isinf(lon): lon = 0.0
                except (ValueError, TypeError):
                    lat, lon = 0.0, 0.0
            
            vol = estimasi_map.get(uid, 0.0)
            if math.isnan(vol) or math.isinf(vol): vol = 0.0
                
            bsu_list.append(BSU(
                bsu_id=uid,   # BSU.bsu_id diisi uid agar GA menggunakan uid sebagai key internal
                nama=data.get("bsu_name", "Unknown"),
                kecamatan=data.get("kecamatan", "Unknown"),
                lat=lat,
                lon=lon,
                estimasi_vol_kg=float(vol)
            ))
            
    if not bsu_list:
        raise HTTPException(status_code=400, detail="BSU data not found for the requests.")
        
    try:
        kapasitas_harian = request.jumlah_kendaraan * request.kapasitas_kendaraan
        max_bsu_harian = request.jumlah_kendaraan * request.kuota_kunjungan
        jadwal_chromosome, history = jalankan_ga(
            tahun, bulan, bsu_list, bsu_requests,
            kapasitas=kapasitas_harian, max_bsu=max_bsu_harian
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate schedule: {str(e)}")
        
    formatted_jadwal = format_jadwal(jadwal_chromosome)
    
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
    # uid sudah tersedia dari token — tidak perlu lookup BSU hanya untuk dapat id
    doc_id = f"{tahun}_{bulan}"
    jadwal_doc = db.collection("jadwal").document(doc_id).get()

    if not jadwal_doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")

    jadwal_data = jadwal_doc.to_dict()
    if jadwal_data.get("status") != "published":
        raise HTTPException(status_code=404, detail="Schedule not published yet")

    hari_list = jadwal_data.get("hari_list", [])
    my_schedule = []

    for hari in hari_list:
        # Cari slot milik user ini — bandingkan dengan uid (relasi utama)
        user_slot = next(
            (slot for slot in hari.get("slots", []) if slot.get("uid") == uid),
            None
        )

        if user_slot:
            my_schedule.append({
                "tanggal": hari.get("tanggal"),
                "vol_kg": user_slot.get("vol_kg", 0.0),
                "req_terpenuhi": user_slot.get("req_terpenuhi", False)
            })

    return my_schedule


