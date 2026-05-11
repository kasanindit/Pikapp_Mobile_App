from database import db
from google.cloud import firestore

def clear_all_dummy():
    print("--- Memulai Pembersihan Total Data Dummy ---")
    
    # 1. Hapus Koleksi schedule_requests
    print("Menghapus semua data di 'schedule_requests'...")
    req_docs = db.collection("schedule_requests").stream()
    count_req = 0
    for doc in req_docs:
        doc.reference.delete()
        count_req += 1
    print(f"Selesai: {count_req} request dihapus.")

    # 2. Hapus Koleksi jadwal
    print("Menghapus semua data di 'jadwal'...")
    jadwal_docs = db.collection("jadwal").stream()
    count_jadwal = 0
    for doc in jadwal_docs:
        doc.reference.delete()
        count_jadwal += 1
    print(f"Selesai: {count_jadwal} jadwal dihapus.")

    # 3. Hapus BSU Dummy (dummy_uid_*)
    print("Menghapus BSU dummy (uid: dummy_uid_*)...")
    bsu_docs = db.collection("bsu").where("uid", ">=", "dummy_uid_").where("uid", "<=", "dummy_uid_" + "\uf8ff").stream()
    count_bsu = 0
    for doc in bsu_docs:
        doc.reference.delete()
        count_bsu += 1
    print(f"Selesai: {count_bsu} BSU dummy dihapus.")

    # 4. Hapus User Dummy di koleksi 'users' jika ada
    print("Menghapus User dummy (uid: dummy_uid_*)...")
    user_docs = db.collection("users").where("uid", ">=", "dummy_uid_").where("uid", "<=", "dummy_uid_" + "\uf8ff").stream()
    count_users = 0
    for doc in user_docs:
        doc.reference.delete()
        count_users += 1
    print(f"Selesai: {count_users} User dummy dihapus.")

    # 5. Reset Periode Pengajuan (Optional, tutup semua)
    print("Mereset status periode_pengajuan...")
    periode_docs = db.collection("periode_pengajuan").stream()
    for doc in periode_docs:
        doc.reference.update({"is_open": False})
    print("Semua periode pengajuan sekarang ditutup (is_open: False).")

    print("\n--- Pembersihan Selesai! Firestore siap digunakan untuk testing fresh ---")

if __name__ == "__main__":
    clear_all_dummy()
