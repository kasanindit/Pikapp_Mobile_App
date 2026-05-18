from fastapi import HTTPException
from firebase_admin import auth, firestore
from datetime import datetime, timezone
import re
import math
from database import db
from models.request_models import CreateUserRequest, ProfileUpdate
from utils.firestore_helper import get_bsu_by_uid

def generate_bsu_email(name: str):
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = ".".join(name.split())
    return f"{name}@pikapp.id"

def register_new_bsu(request: CreateUserRequest):
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
            "uid": uid,
            "bsu_id": uid,  # Eksplisit simpan bsu_id agar konsisten dengan seluruh codebase
            "email": generated_email,
            "bsu_name": request.bsu_name,
            "address": request.address,
            "kecamatan": request.kecamatan,
            "phone_num": request.phone_num,
            "is_active": True,
            "role": "user",
            "created_at": firestore.SERVER_TIMESTAMP
        }
        if request.coordinate:
            bsu_data["coordinate"] = [request.coordinate.lat, request.coordinate.long]

        db.collection("bsu").document(uid).set(bsu_data)
        
        return {
            "email": generated_email,
            "password": default_password
        }
        
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail=f"Email {generated_email} sudah terdaftar. Coba nama BSU lain atau tambahkan karakter lain untuk membedakan akun.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def fetch_all_bsu():
    bsu_docs = db.collection("bsu").stream()
    bsu_list = []
    
    for doc in bsu_docs:
        data = doc.to_dict()
        
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
            "is_active": data.get("is_active", True),
            "coordinate": coordinate
        })

    return bsu_list

def get_bsu_detail(uid: str):
    user_data = get_bsu_by_uid(uid)

    if not user_data:
        raise HTTPException(status_code=404, detail="User not found in Firestore")

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

def update_bsu_profile(uid: str, update_payload: dict):
    # Find the document ID first since old data might not use uid as document ID
    query = db.collection("bsu").where("uid", "==", uid).limit(1).stream()
    user_doc_id = None
    for doc in query:
        user_doc_id = doc.id
        
    if not user_doc_id:
        raise HTTPException(status_code=404, detail="User not found in Firestore")

    user_doc_ref = db.collection("bsu").document(user_doc_id)
    
    if "coordinate" in update_payload and update_payload["coordinate"]:
        coordinate = update_payload["coordinate"]
        if hasattr(coordinate, "dict"):
            coordinate = coordinate.dict()
        update_payload["coordinate"] = [coordinate["lat"], coordinate["long"]]
    elif "latitude" in update_payload and "longitude" in update_payload:
        update_payload["coordinate"] = [update_payload.pop("latitude"), update_payload.pop("longitude")]
    else:
        update_payload.pop("latitude", None)
        update_payload.pop("longitude", None)

    if update_payload:
        update_payload["updated_at"] = firestore.SERVER_TIMESTAMP
        user_doc_ref.update(update_payload)

    return user_doc_ref.get().to_dict()
