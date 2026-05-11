import os
from database import db
from datetime import date
from services.ga_models import jalankan_ga, BSU, format_jadwal
import math

def test_ga():
    tahun = 2026
    bulan = 6
    jumlah_kendaraan = 1
    kapasitas_kendaraan = 1000.0
    kuota_kunjungan = 3

    print(f"--- Memulai Test GA untuk Periode {tahun}-{bulan} ---")
    print(f"Kendaraan: {jumlah_kendaraan}, Kapasitas/Truk: {kapasitas_kendaraan}kg, Kuota/Truk: {kuota_kunjungan}")
    
    kapasitas_harian = jumlah_kendaraan * kapasitas_kendaraan
    max_bsu_harian = jumlah_kendaraan * kuota_kunjungan

    # 1. Ambil data requests
    req_docs = db.collection("schedule_requests").where("tahun", "==", tahun).where("bulan", "==", bulan).stream()
    
    bsu_requests = {}
    requested_bsu_ids = set()
    estimasi_map = {}
    
    for doc in req_docs:
        data = doc.to_dict()
        if data.get("status", "approved") != "approved": continue
        if data.get("jenis_pengajuan", "baru") != "baru": continue

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

    print(f"Ditemukan {len(requested_bsu_ids)} request valid.")

    # 2. Ambil data BSU
    bsu_list = []
    seen_ids = set()
    bsu_docs = db.collection("bsu").stream()
    
    for doc in bsu_docs:
        data = doc.to_dict()
        bsu_id = data.get("bsu_id") or data.get("uid")
        
        if bsu_id in requested_bsu_ids and bsu_id not in seen_ids:
            seen_ids.add(bsu_id)
            coord = data.get("coordinate", [0.0, 0.0])
            vol = estimasi_map.get(bsu_id, 0.0)
            
            bsu_list.append(BSU(
                bsu_id=bsu_id,
                nama=data.get("bsu_name", "Unknown"),
                kecamatan=data.get("kecamatan", "Unknown"),
                lat=float(coord[0]) if coord else 0.0,
                lon=float(coord[1]) if len(coord)>1 else 0.0,
                estimasi_vol_kg=float(vol)
            ))

    print(f"Ditemukan {len(bsu_list)} data profil BSU yang cocok.")

    if not bsu_list:
        print("Tidak ada BSU untuk dijadwalkan.")
        return

    # 3. Jalankan GA
    print("Menjalankan Algoritma Genetika...")
    jadwal_chromosome, history = jalankan_ga(
        tahun, bulan, bsu_list, bsu_requests,
        kapasitas=kapasitas_harian, max_bsu=max_bsu_harian
    )

    # 4. Format & Print Hasil
    formatted = format_jadwal(jadwal_chromosome)
    print("\n--- HASIL JADWAL ---")
    terpenuhi_count = 0
    total_slots = 0
    
    for h in formatted:
        print(f"\n[Tanggal] {h['tanggal']} (Total Vol: {h['total_vol']} kg) - {len(h['slots'])} BSU")
        for s in h['slots']:
            total_slots += 1
            if s['req_terpenuhi']: terpenuhi_count += 1
            status_req = "[TEPAT]" if s['req_terpenuhi'] else "[-]"
            print(f"  - {s['nama']} ({s['vol_kg']}kg) [{s['kecamatan']}] {status_req}")

    print(f"\n📊 Statistik:")
    print(f"Total BSU dijadwalkan: {total_slots} / {len(bsu_list)}")
    print(f"Request terpenuhi: {terpenuhi_count}")

if __name__ == "__main__":
    test_ga()
