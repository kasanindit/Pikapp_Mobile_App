# from firebase_admin import auth
from firebase_config import db
from datetime import datetime, timezone


# backup.py
docs = db.collection("bsu").stream()

backup = []

for doc in docs:
    backup.append(doc.to_dict())

import json

def custom_serializer(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')

with open("backup_bsu.json", "w") as f:
    json.dump(backup, f, default=custom_serializer, indent=4)

print("✅ Backup selesai")


