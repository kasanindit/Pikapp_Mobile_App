import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import GeoPoint

# init firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

db = firestore.client()


# def migrate_coordinate_to_geopoint():
#     docs = db.collection("bsu").stream()

#     total = 0
#     updated = 0

#     for doc in docs:
#         total += 1
#         data = doc.to_dict()

#         coord = data.get("coordinate")

#         if isinstance(coord, GeoPoint):
#             lat = coord.latitude
#             lng = coord.longitude
#         elif isinstance(coord, list) and len(coord) == 2:
#             lat = coord[0]
#             lng = coord[1]
#         else:
#             print(f"Skip (invalid): {doc.id}")
#             continue

#         try:
#             # update ke GeoPoint
#             doc.reference.update({
#                 "location": GeoPoint(lat, lng)
#             })

#             print(f"Updated: {doc.id} → ({lat}, {lng})")
#             updated += 1

#         except Exception as e:
#             print(f"Error di {doc.id}: {e}")

#     print(f"\nTotal docs: {total}")
#     print(f"Berhasil update: {updated}")

def delete_old_coordinate():
    docs = db.collection("bsu").stream()

    for doc in docs:
        doc.reference.update({
            "coordinate": firestore.DELETE_FIELD
        })

    print("✅ Field coordinate berhasil dihapus")


if __name__ == "__main__":
    # migrate_coordinate_to_geopoint()
    delete_old_coordinate()