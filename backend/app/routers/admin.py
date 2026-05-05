from fastapi import APIRouter, Depends, HTTPException
from dependencies import verify_token
from database import db
from google.cloud.firestore import GeoPoint
from firebase_admin import firestore, auth
from datetime import date, datetime, timezone
import re
from pydantic import BaseModel
from services.ga_models import jalankan_ga, format_jadwal, BSU
import math

router = APIRouter(tags=["admin"])

@router.get("/verify-admin")
def admin_only(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]

    query = db.collection("users").where("uid", "==", uid).limit(1).stream()

    user = None
    for doc in query:
        user = doc.to_dict()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    return {"message": "Welcome Admin!"}

# Create New BSU Acc
class CreateUserRequest(BaseModel):
    bsu_name: str
    address: str | None = None
    kecamatan: str | None = None
    phone_num: str | None = None

class LocationModel(BaseModel):
    latitude: float
    longitude: float

def generate_bsu_email(name: str):
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = ".".join(name.split())
    return f"{name}@pikapp.id"

@router.post("/admin/create-bsu")
async def register_bsu(request: CreateUserRequest, decoded_token: dict = Depends(admin_only)):
    try:
        generated_email = generate_bsu_email(request.bsu_name)
        default_password = "user123"
        
        user_record = auth.create_user(
            email=generated_email,
            password=default_password,
            display_name=request.bsu_name
        )
        uid = user_record.uid
        
        # storing data to "user" collection
        user_data = {
            "uid": uid,
            "email": generated_email,
            "uname": generated_email.split("@")[0],
            "role": "user",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        db.collection("users").document(uid).set(user_data)


        # storing data to "bsu" collection
        bsu_data = {
            "uid": user_record.uid,
            "email": generated_email,
            "bsu_name": request.bsu_name,
            "address": request.address,
            "kecamatan": request.kecamatan,
            "phone_num": request.phone_num,
            "role": "user",
            "created_at": firestore.SERVER_TIMESTAMP
        }

        db.collection("bsu").document(uid).set(bsu_data)
        
        return {
            "status": "success",
            "message": f"BSU berhasil didaftarkan dengan email: {generated_email}",
            "data": {
                "email": generated_email,
                "password": default_password
            }
        }
        
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail=f"Email {generated_email} sudah terdaftar. Coba nama BSU lain atau tambahkan karakter lain untuk membedakan akun.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/bsu-list")
def get_all_bsu(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]

    # Verify if user is admin
    query = db.collection("users").where("uid", "==", uid).limit(1).stream()
    user = None
    for doc in query:
        user = doc.to_dict()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden - Admin only access")

    # Fetch all BSU documents
    bsu_docs = db.collection("bsu").stream()
    bsu_list = []
    
    for doc in bsu_docs:
        data = doc.to_dict()
        
        # Safely handle coordinate parsing with NaN/Inf protection
        coordinate = None
        raw_coord = data.get("coordinate")
        if raw_coord and isinstance(raw_coord, list) and len(raw_coord) >= 2:
            try:
                lat = float(raw_coord[0]) if raw_coord[0] is not None else 0.0
                lon = float(raw_coord[1]) if raw_coord[1] is not None else 0.0
                if math.isnan(lat) or math.isinf(lat): lat = 0.0
                if math.isnan(lon) or math.isinf(lon): lon = 0.0
                coordinate = {"lat": lat, "long": lon}
            except (ValueError, TypeError):
                coordinate = {"lat": 0.0, "long": 0.0}
            
        bsu_list.append({
            "uid": data.get("uid"),
            "email": data.get("email"),
            "bsu_name": data.get("bsu_name"),
            "bsu_id": data.get("bsu_id") or data.get("uid"),
            "address": data.get("address"),
            "kecamatan": data.get("kecamatan"),
            "phone_num": data.get("phone_num"),
            "is_priority": data.get("is_priority"),
            "coordinate": coordinate
        })

    return {
        "success": True,
        "message": "Successfully fetched all BSU",
        "data": bsu_list,
        "total_bsu": len(bsu_list)
    }

class PeriodeSettings(BaseModel):
    is_open: bool

@router.get("/admin/periode/{tahun}/{bulan}")
def get_periode_status(tahun: int, bulan: int, auth_status: dict = Depends(admin_only)):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("periode_pengajuan").document(doc_id).get()
    
    if doc.exists:
        return {"success": True, "data": doc.to_dict()}
    
    return {"success": True, "data": {"tahun": tahun, "bulan": bulan, "is_open": False}}

@router.put("/admin/periode/{tahun}/{bulan}")
def update_periode_status(tahun: int, bulan: int, request: PeriodeSettings, auth_status: dict = Depends(admin_only)):
    doc_id = f"{tahun}_{bulan}"
    db.collection("periode_pengajuan").document(doc_id).set({
        "tahun": tahun,
        "bulan": bulan,
        "is_open": request.is_open,
        "updated_at": firestore.SERVER_TIMESTAMP
    }, merge=True)
    
    return {"success": True, "message": f"Periode {tahun}-{bulan} is now {'open' if request.is_open else 'closed'}."}

@router.get("/admin/schedule-requests")
def get_schedule_requests(auth_status: dict = Depends(admin_only)):
    docs = db.collection("schedule_requests").stream()
    data = []
    for doc in docs:
        data.append(doc.to_dict())
    return {"success": True, "data": data}

@router.put("/admin/schedule-requests/{request_id}/approve")
def approve_request(request_id: str, auth_status: dict = Depends(admin_only)):
    doc_ref = db.collection("schedule_requests").document(request_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Request not found")
        
    req_data = doc.to_dict()
    jenis = req_data.get("jenis_pengajuan", "baru")
    tahun = req_data.get("tahun")
    bulan = req_data.get("bulan")
    bsu_id = req_data.get("bsu_id")
    
    if jenis in ["reschedule", "batal"]:
        # Update the final schedule document
        jadwal_doc_id = f"{tahun}_{bulan}"
        jadwal_ref = db.collection("jadwal").document(jadwal_doc_id)
        jadwal_doc = jadwal_ref.get()
        
        if jadwal_doc.exists:
            jadwal_data = jadwal_doc.to_dict()
            hari_list = jadwal_data.get("hari_list", [])
            
            # Find and remove from old date
            old_date = req_data.get("tanggal_lama")
            if old_date:
                for h in hari_list:
                    if h["tanggal"] == old_date:
                        h["slots"] = [s for s in h["slots"] if s.get("bsu_id") != bsu_id]
                        # Recalculate total_vol
                        h["total_vol"] = sum(s.get("vol_kg", 0.0) for s in h["slots"])
            
            # If reschedule, add to new date
            if jenis == "reschedule":
                new_date = req_data.get("tanggal_baru")
                if new_date:
                    # find the new date in hari_list or create it
                    target_h = next((h for h in hari_list if h["tanggal"] == new_date), None)
                    
                    # Fetch BSU detail to construct the slot
                    bsu_doc_ref = db.collection("bsu").document(bsu_id)
                    bsu_doc = bsu_doc_ref.get()
                    
                    if not bsu_doc.exists:
                        # try query by bsu_id field if doc ID (uid) didn't match
                        bsu_docs = db.collection("bsu").where("bsu_id", "==", bsu_id).limit(1).stream()
                        bsu_doc = next(bsu_docs, None)
                    
                    if bsu_doc:
                        bsu_data = bsu_doc.to_dict()
                        lat, lon = 0.0, 0.0
                        coord = bsu_data.get("coordinate")
                        if coord and isinstance(coord, list) and len(coord) >= 2:
                            lat = float(coord[0]) if coord[0] is not None else 0.0
                            lon = float(coord[1]) if coord[1] is not None else 0.0
                            
                        slot_data = {
                            "bsu_id": bsu_id,
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
                            # Sort by date
                            hari_list.sort(key=lambda x: x["tanggal"])
            
            jadwal_ref.update({
                "hari_list": hari_list,
                "updated_at": firestore.SERVER_TIMESTAMP
            })
            
    doc_ref.update({"status": "approved", "updated_at": firestore.SERVER_TIMESTAMP})
    return {"success": True, "message": "Request approved"}

@router.put("/admin/schedule-requests/{request_id}/reject")
def reject_request(request_id: str, auth_status: dict = Depends(admin_only)):
    doc_ref = db.collection("schedule_requests").document(request_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Request not found")
        
    doc_ref.update({"status": "rejected", "updated_at": firestore.SERVER_TIMESTAMP})
    return {"success": True, "message": "Request rejected"}

class GenerateScheduleRequest(BaseModel):
    tahun: int
    bulan: int

@router.post("/generate-schedule")
def generate_schedule(request: GenerateScheduleRequest, auth_status: dict = Depends(admin_only)):
    tahun = request.tahun
    bulan = request.bulan
    
    req_docs = db.collection("schedule_requests").where("tahun", "==", tahun).where("bulan", "==", bulan).stream()
    
    bsu_requests = {}
    requested_bsu_ids = set()
    estimasi_map = {}
    
    for doc in req_docs:
        data = doc.to_dict()
        
        # Filter status approved and jenis_pengajuan baru
        # For backward compatibility, if status or jenis_pengajuan doesn't exist, assume it's valid
        if data.get("status", "approved") != "approved":
            continue
        if data.get("jenis_pengajuan", "baru") != "baru":
            continue

        bsu_id = data.get("bsu_id")
        requested_bsu_ids.add(bsu_id)
        estimasi_map[bsu_id] = data.get("estimasi_vol_kg", 0.0)
        
        tgl_str = data.get("tanggal_request")
        if tgl_str:
            try:
                y, m, d = map(int, tgl_str.split('-'))
                bsu_requests[bsu_id] = date(y, m, d)
            except:
                pass
                
    if not requested_bsu_ids:
        raise HTTPException(status_code=400, detail="No schedule requests found for this period.")
        
    bsu_list = []
    seen_ids = set()
    bsu_docs = db.collection("bsu").stream()
    
    for doc in bsu_docs:
        data = doc.to_dict()
        bsu_id = data.get("bsu_id") or data.get("uid")
        
        if bsu_id in requested_bsu_ids and bsu_id not in seen_ids:
            seen_ids.add(bsu_id)
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
            
            vol = estimasi_map.get(bsu_id, 0.0)
            if math.isnan(vol) or math.isinf(vol): vol = 0.0
                
            bsu_list.append(BSU(
                bsu_id=bsu_id,
                nama=data.get("bsu_name", "Unknown"),
                kecamatan=data.get("kecamatan", "Unknown"),
                lat=lat,
                lon=lon,
                estimasi_vol_kg=float(vol)
            ))
            
    if not bsu_list:
        raise HTTPException(status_code=400, detail="BSU data not found for the requests.")
        
    try:
        jadwal_chromosome, history = jalankan_ga(tahun, bulan, bsu_list, bsu_requests)
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
        "success": True,
        "message": "Schedule generated successfully and saved as draft.",
        "data": {
            "tahun": tahun,
            "bulan": bulan,
            "status": "draft",
            "hari_list": formatted_jadwal
        }
    }

@router.get("/schedule/{tahun}/{bulan}")
def get_admin_schedule(tahun: int, bulan: int, auth_status: dict = Depends(admin_only)):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("jadwal").document(doc_id).get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found")
        
    return {
        "success": True,
        "data": doc.to_dict()
    }

class SchedulePublishRequest(BaseModel):
    hari_list: list[dict]

@router.put("/schedule/{tahun}/{bulan}/publish")
def publish_schedule(tahun: int, bulan: int, request: SchedulePublishRequest, auth_status: dict = Depends(admin_only)):
    doc_id = f"{tahun}_{bulan}"
    doc_ref = db.collection("jadwal").document(doc_id)
    
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Schedule draft not found")
        
    doc_ref.update({
        "status": "published",
        "hari_list": request.hari_list,
        "updated_at": firestore.SERVER_TIMESTAMP
    })
    
    return {
        "success": True,
        "message": "Schedule published successfully"
    }
