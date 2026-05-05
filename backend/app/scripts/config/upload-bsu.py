import json
from firebase_config import db
from datetime import datetime, timezone


# load JSON
with open("bsu-collection.json", "r", encoding="utf-8") as file:
    bsu_data = json.load(file)

def upload_bsu():
    collection_ref = db.collection("bsu")

    for bsu in bsu_data:
        doc_ref = collection_ref.document()

        doc_ref.set({
            "bsu_name": bsu["NAMA BANK SAMPAH"],
            "kecamatan": bsu["KECAMATAN"],
            "address": "",
            "phone_num": "",
            "is_priority": False,
            "coordinate": [0, 0],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "update_at": datetime.now(timezone.utc).isoformat()
        })

        print(f"Uploaded: {bsu['NAMA BANK SAMPAH']}")

    print("✅ Semua data berhasil diupload!")

if __name__ == "__main__":
    upload_bsu()