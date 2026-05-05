from firebase_admin import auth
from firebase_config import db
from datetime import datetime, timezone
import re

def generate_email_from_name(name: str):
    # lowercase
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # split & join biar gak ada dot dobel
    name = ".".join(name.split())
    return f"{name}@pikapp.id"

def generate_auth_for_bsu():
    collection_ref = db.collection("bsu")
    docs = collection_ref.stream()

    for index, doc in enumerate(docs):
        data = doc.to_dict()

        bsu_name = data["bsu_name"]

        # generate email baru
        new_email = generate_email_from_name(bsu_name)

        try:
            if "uid" in data:
                uid = data["uid"]

                try:
                    # update email di Firebase Auth
                    auth.update_user(
                        uid,
                        email=new_email
                    )
                    print(f"🔄 Auth updated: {new_email}")

                except Exception as e:
                    print(f"Auth update failed ({bsu_name}): {e}")

                #update firestore
                doc.reference.update({
                    "email": new_email,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })

                print(f"Firestore updated: {bsu_name}")

            else:
                bsu_id = f"BSU{str(index + 1).zfill(3)}"
                password = "user123"

                user_record = auth.create_user(
                    email=new_email,
                    password=password
                )

                uid = user_record.uid

                doc.reference.update({
                    "uid": uid,
                    "bsu_id": bsu_id,
                    "email": new_email,
                    "role": "user",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })

                print(f"Created {bsu_id}")

        except Exception as e:
            print(f"Error {bsu_name}: {e}")


if __name__ == "__main__":
    generate_auth_for_bsu()