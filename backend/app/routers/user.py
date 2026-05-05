from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from dependencies import verify_token
from database import db
from datetime import datetime, timezone, timedelta
from google.cloud import firestore

router = APIRouter(tags=["user"])

@router.get("/bsu-detail")
def get_current_bsu(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]

    docs = db.collection("bsu").where("uid", "==", uid).limit(1).stream()

    user_doc = next(docs, None)

    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found in Firestore")

    user_data = user_doc.to_dict()

    return {
        "uid": uid,
        "email": user_data.get("email"),
        "bsu_name": user_data.get("bsu_name"),
        "bsu_id": user_data.get("bsu_id"),
        "role": user_data.get("role"),
        "address": user_data.get("address"),
        "kecamatan": user_data.get("kecamatan"),
        "phone_num": user_data.get("phone_num"),
        "is_priority": user_data.get("is_priority"),
        "coordinate": {
            "lat": user_data.get("coordinate")[0],
            "long": user_data.get("coordinate")[1]
        } if user_data.get("coordinate") else None
    }

class CoordinateUpdate(BaseModel):
    lat: float
    long: float

class ProfileUpdate(BaseModel):
    bsu_name: str | None = None
    address: str | None = None
    kecamatan: str | None = None
    phone_num: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate: CoordinateUpdate | None = None

@router.put("/bsu/update")
def UpdateProfile(request: ProfileUpdate, decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]

    docs = db.collection("bsu").where("uid", "==", uid).limit(1).stream()
    user_doc = next(docs, None)

    if not user_doc:
        raise HTTPException(status_code=404, detail="User not found in Firestore")

    user_data = db.collection("bsu").document(user_doc.id)

    update_payload = request.dict(exclude_unset=True)
    
    if "coordinate" in update_payload and update_payload["coordinate"]:
        update_payload["coordinate"] = [update_payload["coordinate"]["lat"], update_payload["coordinate"]["long"]]
    elif "latitude" in update_payload and "longitude" in update_payload:
        update_payload["coordinate"] = [update_payload.pop("latitude"), update_payload.pop("longitude")]
    else:
        update_payload.pop("latitude", None)
        update_payload.pop("longitude", None)

    if update_payload:
        user_data.update(update_payload)

    return {
        "message": "Profile updated successfully",
        "user_data": user_data.get().to_dict()
    }

class ScheduleRequestInput(BaseModel):
    tahun: int
    bulan: int
    tanggal_request: str | None = None
    estimasi_vol_kg: float
    jenis_pengajuan: str = "baru" # "baru", "reschedule", "batal"
    tanggal_lama: str | None = None
    tanggal_baru: str | None = None
    alasan: str | None = None

@router.get("/periode/{tahun}/{bulan}/active")
def get_periode_active(tahun: int, bulan: int, decoded_token: dict = Depends(verify_token)):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("periode_pengajuan").document(doc_id).get()
    
    is_open = False
    if doc.exists:
        is_open = doc.to_dict().get("is_open", False)
        
    return {
        "success": True,
        "data": {
            "tahun": tahun,
            "bulan": bulan,
            "is_open": is_open
        }
    }

@router.post("/schedule-request")
def create_schedule_request(request: ScheduleRequestInput, decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    
    # get bsu_id from bsu collection
    bsu_docs = db.collection("bsu").where("uid", "==", uid).limit(1).stream()
    bsu_doc = next(bsu_docs, None)
    
    if not bsu_doc:
        raise HTTPException(status_code=404, detail="BSU not found")
        
    bsu_data = bsu_doc.to_dict()
    bsu_id = bsu_data.get("bsu_id")
    if not bsu_id:
        bsu_id = uid  # ambil uid if bsu_id gada
    
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

    doc_id = f"{request.tahun}_{request.bulan}_{bsu_id}_{int(datetime.now().timestamp())}"
    
    request_data = {
        "request_id": doc_id,
        "uid": uid,
        "bsu_id": bsu_id,
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
    
    return {
        "success": True,
        "message": "Schedule request submitted successfully",
        "data": {**request_data, "created_at": None, "updated_at": None} # None so it's JSON serializable in response
    }

@router.get("/schedule")
def get_published_schedule(tahun: int, bulan: int, decoded_token: dict = Depends(verify_token)):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("jadwal").document(doc_id).get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Schedule not found for this period")
        
    data = doc.to_dict()
    
    if data.get("status") != "published":
        raise HTTPException(status_code=404, detail="Schedule is not published yet")
        
    return {
        "success": True,
        "message": "Successfully fetched published schedule",
        "data": data.get("hari_list", [])
    }

@router.get("/my-schedule")
def get_my_schedule(tahun: int, bulan: int, decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    
    # get bsu_id from bsu collection
    bsu_docs = db.collection("bsu").where("uid", "==", uid).limit(1).stream()
    bsu_doc = next(bsu_docs, None)
    if not bsu_doc:
        raise HTTPException(status_code=404, detail="BSU not found")
        
    bsu_id = bsu_doc.to_dict().get("bsu_id", uid)
    
    # query schedule for this month
    doc_id = f"{tahun}_{bulan}"
    jadwal_doc = db.collection("jadwal").document(doc_id).get()
    
    my_dates = []
    
    if jadwal_doc.exists:
        jadwal_data = jadwal_doc.to_dict()
        if jadwal_data.get("status") == "published":
            hari_list = jadwal_data.get("hari_list", [])
            for h in hari_list:
                # check if bsu_id is in slots
                if any(s.get("bsu_id") == bsu_id for s in h.get("slots", [])):
                    my_dates.append(h.get("tanggal"))
                    
    return {
        "success": True,
        "message": "Successfully fetched personal schedule dates",
        "data": my_dates
    }
