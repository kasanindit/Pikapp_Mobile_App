from fastapi import HTTPException
from google.cloud import firestore
from database import db

def get_user_by_uid(uid: str) -> dict | None:
    """Mengambil data user dari collection 'users' berdasarkan UID."""
    query = db.collection("users").where("uid", "==", uid).limit(1).stream()
    for doc in query:
        return doc.to_dict()
    return None

def get_bsu_by_uid(uid: str) -> dict | None:
    """Mengambil data BSU dari collection 'bsu' berdasarkan UID."""
    query = db.collection("bsu").where("uid", "==", uid).limit(1).stream()
    for doc in query:
        return doc.to_dict()
    return None

def verify_admin_role(uid: str) -> dict:
    """Memastikan user adalah admin. Mengembalikan dict user jika ya, raise exception jika tidak."""
    user = get_user_by_uid(uid)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden - Admin only access")
        
    return user
