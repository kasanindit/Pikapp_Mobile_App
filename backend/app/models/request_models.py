from __future__ import annotations

from pydantic import BaseModel

# ==========================================
# ADMIN REQUEST MODELS
# ==========================================

class CoordinateUpdate(BaseModel):
    lat: float
    long: float

class CreateUserRequest(BaseModel):
    bsu_name: str
    address: str | None = None
    kecamatan: str | None = None
    phone_num: str | None = None
    coordinate: CoordinateUpdate | None = None

class LocationModel(BaseModel):
    latitude: float
    longitude: float

class PeriodeSettings(BaseModel):
    is_open: bool

class GenerateScheduleRequest(BaseModel):
    tahun: int
    bulan: int
    jumlah_kendaraan: int = 1
    kapasitas_kendaraan: float = 1000.0
    kuota_kunjungan: int = 3

class SchedulePublishRequest(BaseModel):
    hari_list: list[dict]


# ==========================================
# USER REQUEST MODELS
# ==========================================

class ProfileUpdate(BaseModel):
    bsu_name: str | None = None
    address: str | None = None
    kecamatan: str | None = None
    phone_num: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate: CoordinateUpdate | None = None
    is_active: bool | None = None

class ScheduleRequestInput(BaseModel):
    tahun: int
    bulan: int
    tanggal_request: str | None = None
    # estimasi_vol_kg sebelumnya wajib untuk semua pengajuan.
    # Untuk reschedule dan batal, volume tidak digunakan.
    # estimasi_vol_kg: float
    estimasi_vol_kg: float = 0.0
    jenis_pengajuan: str = "baru" # "baru", "reschedule", "batal"
    tanggal_lama: str | None = None
    tanggal_baru: str | None = None
    alasan: str | None = None

class HistoryStatusUpdate(BaseModel):
    uid: str
    tanggal: str
    status: str
    vol_kg: float = 0.0
    tanggal_baru: str | None = None
    alasan: str | None = None
    request_id: str | None = None
