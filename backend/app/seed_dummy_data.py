import pandas as pd
import random
from datetime import datetime
from database import db
from google.cloud import firestore

def clear_old_data():
    print("--- Memulai Pembersihan Data Dummy ---")
    
    # 1. Hapus BSU yang diawali 'dummy_uid_'
    bsu_docs = db.collection("bsu").where("uid", ">=", "dummy_uid_").where("uid", "<=", "dummy_uid_" + "\uf8ff").stream()
    count_bsu = 0
    for doc in bsu_docs:
        doc.reference.delete()
        count_bsu += 1
    
    # 2. Hapus semua schedule requests untuk membersihkan antrean
    req_docs = db.collection("schedule_requests").stream()
    count_req = 0
    for doc in req_docs:
        doc.reference.delete()
        count_req += 1
            
    # 3. Hapus Jadwal periode Agustus 2025
    db.collection("jadwal").document("2025_8").delete()
    print(f"Pembersihan Selesai: {count_bsu} BSU dan {count_req} Request dihapus.\n")

def seed_from_excel(file_path):
    # Bersihkan dulu data lama
    clear_old_data()
    
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error membaca file {file_path}: {e}")
        return

    tahun = 2026
    bulan = 6
    
    print(f"--- Mengimpor {len(df)} Data dari Excel ({tahun}-{bulan}) ---")
    
    # Buka periode agar valid
    db.collection("periode_pengajuan").document(f"{tahun}_{bulan}").set({
        "tahun": tahun, "bulan": bulan, "is_open": True, "updated_at": firestore.SERVER_TIMESTAMP
    })

    batch = db.batch()
    
    for index, row in df.iterrows():
        # Ambil data dari kolom Excel
        name = row.get('NAMA BANK SAMPAH', f"BSU {index+1}")
        kecamatan = row.get('KECAMATAN', 'Unknown')
        lat = row.get('Lat', 0.0)
        lon = row.get('Long', 0.0)
        
        bsu_id = f"BSU-{index+1:03}"
        uid = f"dummy_uid_{bsu_id}"
        
        # 1. Simpan Profil BSU
        bsu_ref = db.collection("bsu").document(uid)
        batch.set(bsu_ref, {
            "uid": uid,
            "bsu_id": bsu_id,
            "bsu_name": name,
            "kecamatan": kecamatan,
            "coordinate": [float(lat), float(lon)],
            "role": "user",
            "email": f"{bsu_id.lower()}@dummy.com",
            "created_at": firestore.SERVER_TIMESTAMP
        })
        
        # 2. Simpan Request (Langsung Set APPROVED agar bisa di-generate)
        req_id = f"req_{bsu_id}_{tahun}_{bulan}"
        req_ref = db.collection("schedule_requests").document(req_id)
        
        # Tambahkan tanggal_request acak untuk testing soft constraint GA (50% probabilitas)
        tgl_req = None
        if random.choice([True, False]):
            random_day = random.randint(1, 28)
            tgl_req = f"{tahun}-{bulan:02}-{random_day:02}"
            
        vol = random.randint(50, 900)
        batch.set(req_ref, {
            "request_id": req_id,
            "uid": uid,
            "bsu_id": bsu_id,
            "tahun": tahun,
            "bulan": bulan,
            "tanggal_request": tgl_req,
            "estimasi_vol_kg": float(vol),
            "jenis_pengajuan": "baru",
            "status": "approved", # Langsung approved untuk testing GA
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP
        })

    batch.commit()
    print(f"--- Selesai: {len(df)} BSU dan Request telah diimpor ---")
    print(f"Sekarang jalankan POST /generate-schedule untuk periode {tahun}-{bulan}")

if __name__ == "__main__":
    excel_file = "dummy_bsu.xlsx"
    seed_from_excel(excel_file)
