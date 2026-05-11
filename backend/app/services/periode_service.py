from google.cloud import firestore
from database import db

def fetch_periode_status(tahun: int, bulan: int):
    doc_id = f"{tahun}_{bulan}"
    doc = db.collection("periode_pengajuan").document(doc_id).get()
    
    if doc.exists:
        return doc.to_dict()
    
    return {"tahun": tahun, "bulan": bulan, "is_open": False}

def set_periode_status(tahun: int, bulan: int, is_open: bool):
    doc_id = f"{tahun}_{bulan}"
    db.collection("periode_pengajuan").document(doc_id).set({
        "tahun": tahun,
        "bulan": bulan,
        "is_open": is_open,
        "updated_at": firestore.SERVER_TIMESTAMP
    }, merge=True)
    
    return True
