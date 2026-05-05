# import pandas as pd
import random
from datetime import datetime
from database import db
from google.cloud import firestore

def seed_data():
    tahun = 2025
    bulan = 8

    # Data Dummy BSU (Area Depok)
    dummy_bsu = [
        {"bsu_id": "BSU-01", "name": "BSU Beji Sejahtera", "kecamatan": "Beji", "lat": -6.3812, "lon": 106.8318, "vol": 920, "req_date": None},
        {"bsu_id": "BSU-02", "name": "BSU Beji Indah", "kecamatan": "Beji", "lat": -6.3790, "lon": 106.8295, "vol": 280, "req_date": "2025-08-15"},
        {"bsu_id": "BSU-03", "name": "BSU Kukusan Bersih", "kecamatan": "Beji", "lat": -6.3901, "lon": 106.8290, "vol": 350, "req_date": None},
        {"bsu_id": "BSU-04", "name": "BSU Pondok Cina Maju", "kecamatan": "Beji", "lat": -6.3850, "lon": 106.8340, "vol": 453, "req_date": "2025-08-04"},
        {"bsu_id": "BSU-05", "name": "BSU Depok Lama Hijau", "kecamatan": "Pancoran Mas", "lat": -6.4012, "lon": 106.8198, "vol": 410, "req_date": "2025-08-05"},
        {"bsu_id": "BSU-06", "name": "BSU Rangkapan Bersatu", "kecamatan": "Pancoran Mas", "lat": -6.4080, "lon": 106.8210, "vol": 380, "req_date": None},
        {"bsu_id": "BSU-07", "name": "BSU Mampang Asri", "kecamatan": "Pancoran Mas", "lat": -6.4050, "lon": 106.8175, "vol": 567, "req_date": "2025-08-11"},
        {"bsu_id": "BSU-08", "name": "BSU Sukmajaya Mandiri", "kecamatan": "Sukmajaya", "lat": -6.3700, "lon": 106.8450, "vol": 440, "req_date": None},
        {"bsu_id": "BSU-09", "name": "BSU Abadijaya Lestari", "kecamatan": "Sukmajaya", "lat": -6.3680, "lon": 106.8480, "vol": 310, "req_date": "2025-08-20"},
        {"bsu_id": "BSU-10", "name": "BSU Cilodong Bersih", "kecamatan": "Cilodong", "lat": -6.3500, "lon": 106.8550, "vol": 500, "req_date": None},
        {"bsu_id": "BSU-11", "name": "BSU Tapos Hijau", "kecamatan": "Tapos", "lat": -6.3400, "lon": 106.8700, "vol": 420, "req_date": "2025-08-28"},
        {"bsu_id": "BSU-12", "name": "BSU Cimanggis Berkah", "kecamatan": "Cimanggis", "lat": -6.3600, "lon": 106.8900, "vol": 290, "req_date": None},
    ]

    print("Menyimpan data BSU dan Schedule Requests ke Firestore...")
    
    batch = db.batch()
    
    for b in dummy_bsu:
        uid = f"dummy_uid_{b['bsu_id']}"
        
        # 1. Masukkan ke collection "bsu"
        bsu_ref = db.collection("bsu").document(uid)
        batch.set(bsu_ref, {
            "uid": uid,
            "bsu_id": b["bsu_id"],
            "bsu_name": b["name"],
            "kecamatan": b["kecamatan"],
            "coordinate": [b["lat"], b["lon"]],
            "role": "user",
            "email": f"{b['bsu_id'].lower()}@dummy.com",
            "created_at": firestore.SERVER_TIMESTAMP
        })
        
        # 2. Masukkan ke collection "schedule_requests"
        req_id = f"{tahun}_{bulan}_{b['bsu_id']}"
        req_ref = db.collection("schedule_requests").document(req_id)
        batch.set(req_ref, {
            "uid": uid,
            "bsu_id": b["bsu_id"],
            "tahun": tahun,
            "bulan": bulan,
            "tanggal_request": b["req_date"],
            "estimasi_vol_kg": b["vol"],
            "created_at": firestore.SERVER_TIMESTAMP
        })

    # Eksekusi semua perintah penyimpanan dalam satu waktu (batch)
    batch.commit()
    print(f"Berhasil menambahkan {len(dummy_bsu)} BSU dan Request Jadwal untuk Tahun {tahun} Bulan {bulan}!")
    print("Silakan coba panggil endpoint POST /admin/generate-schedule dengan JSON:")
    print(f'{{"tahun": {tahun}, "bulan": {bulan}}}')

if __name__ == "__main__":
    seed_data()

# def seed_data_from_excel(file_path):
#     # 1. Baca File Excel
#     try:
#         df = pd.read_excel(file_path)
#     except Exception as e:
#         print(f"Error membaca file: {e}")
#         return

#     tahun = 2025
#     bulan = 8
    
#     print(f"Memproses {len(df)} data dari Excel...")
#     batch = db.batch()

#     for index, row in df.iterrows():
#         # Menyesuaikan nama kolom Excel (silakan ubah sesuai nama kolom di filemu)
#         name = row['NAMA BANK SAMPAH']
#         alamat = row['Alamat']
#         kecamatan = row['KECAMATAN']
#         lat = row['Lat']
#         lon = row['Long']
        
#         # Generate ID unik berdasarkan index atau nama
#         bsu_id = f"BSU-{index+1:03}"
#         uid = f"user_{bsu_id.lower()}"

#         # Volume diacak antara 200kg - 900kg
#         vol = random.randint(200, 900)

#         # Random request hari (50% kemungkinan punya request)
#         req_date = None
#         if random.choice([True, False]):
#             random_day = random.randint(1, 28)
#             req_date = f"{tahun}-{bulan:02}-{random_day:02}"

#         # 1. Simpan ke koleksi "bsu" (Profil Nasabah)
#         bsu_ref = db.collection("bsu").document(uid)
#         batch.set(bsu_ref, {
#             "uid": uid,
#             "bsu_id": bsu_id,
#             "bsu_name": f"dummy_{name}",
#             "address": alamat,
#             "kecamatan": kecamatan,
#             "coordinate": [lat, lon],
#             "role": "user",
#             "email": f"{bsu_id.lower()}@pikapp.id",
#             "created_at": firestore.SERVER_TIMESTAMP
#         })

#         # 2. Simpan ke koleksi "schedule_requests" (Data Input GA)
#         # ID Dokumen: Tahun_Bulan_UID agar unik per periode
#         req_id = f"{tahun}_{bulan}_{uid}"
#         req_ref = db.collection("schedule_requests").document(req_id)
#         batch.set(req_ref, {
#             "uid": uid,
#             "bsu_id": bsu_id,
#             "bsu_name": f"dummy_{name}", # Redundansi untuk mempermudah pembacaan di admin
#             "tahun": tahun,
#             "bulan": bulan,
#             "tanggal_request": req_date,
#             "estimasi_vol_kg": vol,
#             "status": "pending",
#             "created_at": firestore.SERVER_TIMESTAMP
#         })

#     # Eksekusi batch
#     batch.commit()
#     print(f"✅ Berhasil mengimpor {len(df)} data ke Firestore!")
#     print(f"🚀 Sekarang jalankan endpoint generate untuk periode {bulan}-{tahun}")

# if __name__ == "__main__":
#     path_file = "dummy_bsu.xlsx" 
#     seed_data_from_excel(path_file)
