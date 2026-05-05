import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

# init
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()

def migrate_bsu_to_users():
    docs = db.collection("bsu").stream()

    for doc in docs:
        data = doc.to_dict()

        uid = data.get("uid")
        email = data.get("email", "")
        username = data.get("bsu_name", "") 
        role = data.get("role", "bsu")

        if not uid:
            print("UID kosong, skip")
            continue

        user_ref = db.collection("users").document(uid)

        # skip kalau sudah ada
        if user_ref.get().exists:
            print(f"{email} already exists")
            continue

        user_data = {
            "uid": uid,
            "email": email,
            "uname": username,
            "role": role,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "update_at": datetime.now(timezone.utc).isoformat()
        }

        user_ref.set(user_data)
        print(f"{email} migrated")

if __name__ == "__main__":
    migrate_bsu_to_users()