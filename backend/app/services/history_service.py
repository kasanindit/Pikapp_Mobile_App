from datetime import datetime, timezone
from google.cloud import firestore
from database import db
from utils.firestore_helper import get_bsu_by_uid

FINAL_EVENT_STATUSES = {"completed", "canceled", "rescheduled", "failed"}

def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

def _as_iso(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value

def _month_matches(date_str: str | None, tahun: int | None, bulan: int | None) -> bool:
    tanggal = _parse_date(date_str)
    if tanggal is None:
        return False
    if tahun is not None and tanggal.year != tahun:
        return False
    if bulan is not None and tanggal.month != bulan:
        return False
    return True

def _history_doc_id(uid: str, tanggal: str, status: str, request_id: str | None = None) -> str:
    suffix = request_id or int(datetime.now(timezone.utc).timestamp())
    return f"{uid}_{tanggal}_{status}_{suffix}"

def _format_history_item(data: dict) -> dict:
    tanggal = data.get("tanggal")
    tanggal_date = _parse_date(tanggal)
    return {
        "history_id": data.get("history_id"),
        "uid": data.get("uid"),
        "bsu_id": data.get("bsu_id"),
        "bsu_name": data.get("bsu_name"),
        "kecamatan": data.get("kecamatan"),
        "tanggal": tanggal,
        "tanggal_baru": data.get("tanggal_baru"),
        "status": data.get("status"),
        "vol_kg": data.get("vol_kg", 0.0),
        "request_id": data.get("request_id"),
        "alasan": data.get("alasan"),
        "source": data.get("source"),
        "keterangan": data.get("keterangan"),
        "tahun": tanggal_date.year if tanggal_date else data.get("tahun"),
        "bulan": tanggal_date.month if tanggal_date else data.get("bulan"),
        "created_at": _as_iso(data.get("created_at")),
        "updated_at": _as_iso(data.get("updated_at")),
        "approved_at": _as_iso(data.get("approved_at")),
    }

def write_pickup_history(
    uid: str,
    tanggal: str,
    status: str,
    slot_data: dict | None = None,
    bsu_data: dict | None = None,
    tanggal_baru: str | None = None,
    request_id: str | None = None,
    alasan: str | None = None,
    source: str = "system",
):
    slot_data = slot_data or {}
    bsu_data = bsu_data or get_bsu_by_uid(uid) or {}
    tanggal_date = _parse_date(tanggal)
    history_id = _history_doc_id(uid, tanggal, status, request_id)

    payload = {
        "history_id": history_id,
        "uid": uid,
        "bsu_id": slot_data.get("bsu_id") or bsu_data.get("bsu_id") or uid,
        "bsu_name": slot_data.get("nama") or bsu_data.get("bsu_name", ""),
        "kecamatan": slot_data.get("kecamatan") or bsu_data.get("kecamatan", ""),
        "tanggal": tanggal,
        "tanggal_baru": tanggal_baru,
        "status": status,
        "vol_kg": float(slot_data.get("vol_kg", 0.0) or 0.0),
        "request_id": request_id,
        "alasan": alasan,
        "source": source,
        "tahun": tanggal_date.year if tanggal_date else None,
        "bulan": tanggal_date.month if tanggal_date else None,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    existing = db.collection("pickup_history").document(history_id).get()
    if not existing.exists:
        payload["created_at"] = firestore.SERVER_TIMESTAMP
    if source == "admin_request":
        payload["approved_at"] = firestore.SERVER_TIMESTAMP

    db.collection("pickup_history").document(history_id).set(payload, merge=True)
    return {**payload, "created_at": None, "updated_at": None, "approved_at": None}

def fetch_history(uid: str | None = None, tahun: int | None = None, bulan: int | None = None, status: str | None = None):
    today = datetime.now(timezone.utc).date()
    events = []

    event_docs = db.collection("pickup_history").stream()
    for doc in event_docs:
        data = doc.to_dict()
        if uid is not None and data.get("uid") != uid:
            continue
        if status is not None and data.get("status") != status:
            continue
        if (tahun is not None or bulan is not None) and not _month_matches(data.get("tanggal"), tahun, bulan):
            continue
        events.append(_format_history_item(data))

    override_keys = set()
    for item in events:
        if item.get("status") not in FINAL_EVENT_STATUSES:
            continue
        if item.get("uid"):
            override_keys.add((item.get("uid"), item.get("tanggal")))
        if item.get("bsu_id"):
            override_keys.add((item.get("bsu_id"), item.get("tanggal")))

    user_identifiers = None
    if uid is not None:
        bsu_data = get_bsu_by_uid(uid) or {}
        user_identifiers = {value for value in [uid, bsu_data.get("uid"), bsu_data.get("bsu_id")] if value}

    completed_items = []
    schedule_docs = db.collection("jadwal").stream()
    for doc in schedule_docs:
        schedule_data = doc.to_dict()
        if schedule_data.get("status") != "published":
            continue

        for hari in schedule_data.get("hari_list", []):
            tanggal = hari.get("tanggal")
            tanggal_date = _parse_date(tanggal)
            if tanggal_date is None or tanggal_date >= today:
                continue
            if (tahun is not None or bulan is not None) and not _month_matches(tanggal, tahun, bulan):
                continue

            for slot in hari.get("slots", []):
                slot_uid = slot.get("uid") or slot.get("bsu_id")
                if uid is not None and slot.get("uid") not in user_identifiers and slot.get("bsu_id") not in user_identifiers:
                    continue
                if status is not None and status != "completed":
                    continue
                if (slot_uid, tanggal) in override_keys or (slot.get("uid"), tanggal) in override_keys or (slot.get("bsu_id"), tanggal) in override_keys:
                    continue

                completed_items.append(_format_history_item({
                    "history_id": f"auto_{slot_uid}_{tanggal}",
                    "uid": slot_uid,
                    "bsu_id": slot.get("bsu_id") or slot_uid,
                    "bsu_name": slot.get("nama", ""),
                    "kecamatan": slot.get("kecamatan", ""),
                    "tanggal": tanggal,
                    "status": "completed",
                    "vol_kg": slot.get("vol_kg", 0.0),
                    "source": "auto_completed",
                    "keterangan": "Pengangkutan selesai",
                }))

    result = events + completed_items
    result.sort(key=lambda item: (item.get("tanggal") or "", item.get("created_at") or ""), reverse=True)
    return result

def fetch_user_history(uid: str):
    return fetch_history(uid=uid)

def fetch_admin_history(tahun: int | None = None, bulan: int | None = None, status: str | None = None, uid: str | None = None):
    return fetch_history(uid=uid, tahun=tahun, bulan=bulan, status=status)
