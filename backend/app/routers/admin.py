from fastapi import APIRouter, Depends, HTTPException
from dependencies import verify_token
from models.request_models import (
    CreateUserRequest, PeriodeSettings, 
    GenerateScheduleRequest, SchedulePublishRequest, HistoryStatusUpdate
)
from utils.firestore_helper import verify_admin_role
from utils.response import success_response

# Import Services
from services.bsu_service import register_new_bsu, fetch_all_bsu
from services.periode_service import fetch_periode_status, set_periode_status
from services.request_service import (
    fetch_all_schedule_requests, process_approve_request, process_reject_request
)
from services.history_service import fetch_admin_history, write_pickup_history
from services.schedule_service import (
    create_generated_schedule, fetch_admin_schedule, modify_schedule_draft,
    set_schedule_published, set_schedule_finalized, remove_schedule_slot, remove_monthly_schedule
)

router = APIRouter(tags=["admin"])

# Default dependency for admin routes
def admin_only(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    return verify_admin_role(uid)

@router.get("/verify-admin")
def check_admin(admin_user: dict = Depends(admin_only)):
    return {"message": "Welcome Admin!"}

@router.post("/admin/create-bsu")
def register_bsu(request: CreateUserRequest, admin_user: dict = Depends(admin_only)):
    result = register_new_bsu(request)
    return success_response(
        data=result, 
        message=f"BSU berhasil didaftarkan dengan email: {result['email']}"
    )

@router.get("/bsu-list")
def get_all_bsu(admin_user: dict = Depends(admin_only)):
    bsu_list = fetch_all_bsu()
    return success_response(
        data=bsu_list, 
        message="Successfully fetched all BSU"
    )

@router.get("/periode/{tahun}/{bulan}")
def get_periode_status(tahun: int, bulan: int, auth_status: dict = Depends(verify_token)):
    # Note: Ini bisa diakses user juga (sesuai kode asli yang tidak pakai admin_only)
    data = fetch_periode_status(tahun, bulan)
    return success_response(data=data)

@router.put("/admin/periode/{tahun}/{bulan}")
def update_periode_status(tahun: int, bulan: int, request: PeriodeSettings, admin_user: dict = Depends(admin_only)):
    set_periode_status(tahun, bulan, request.is_open)
    return success_response(
        message=f"Periode {tahun}-{bulan} is now {'open' if request.is_open else 'closed'}."
    )

@router.get("/admin/schedule-requests")
def get_schedule_requests(admin_user: dict = Depends(admin_only)):
    data = fetch_all_schedule_requests()
    return success_response(data=data)

@router.get("/admin/history")
def get_admin_history(
    tahun: int | None = None,
    bulan: int | None = None,
    status: str | None = None,
    uid: str | None = None,
    admin_user: dict = Depends(admin_only)
):
    data = fetch_admin_history(tahun=tahun, bulan=bulan, status=status, uid=uid)
    return success_response(data=data, message="Successfully fetched operational history")

@router.put("/admin/history/status")
def update_history_status(request: HistoryStatusUpdate, admin_user: dict = Depends(admin_only)):
    if request.status not in {"completed", "canceled", "rescheduled", "failed"}:
        raise HTTPException(status_code=400, detail="Invalid history status")

    data = write_pickup_history(
        uid=request.uid,
        tanggal=request.tanggal,
        status=request.status,
        slot_data={"vol_kg": request.vol_kg},
        tanggal_baru=request.tanggal_baru,
        request_id=request.request_id,
        alasan=request.alasan,
        source="admin_override",
    )
    return success_response(data=data, message="History status updated")

@router.put("/admin/schedule-requests/{request_id}/approve")
def approve_request(request_id: str, admin_user: dict = Depends(admin_only)):
    process_approve_request(request_id)
    return success_response(message="Request approved")

@router.put("/admin/schedule-requests/{request_id}/reject")
def reject_request(request_id: str, admin_user: dict = Depends(admin_only)):
    process_reject_request(request_id)
    return success_response(message="Request rejected")

@router.post("/generate-schedule")
def generate_schedule(request: GenerateScheduleRequest, admin_user: dict = Depends(admin_only)):
    data = create_generated_schedule(request)
    return success_response(
        data=data,
        message="Schedule generated successfully and saved as draft."
    )

@router.get("/schedule/{tahun}/{bulan}")
def get_admin_schedule(tahun: int, bulan: int, admin_user: dict = Depends(admin_only)):
    data = fetch_admin_schedule(tahun, bulan)
    return success_response(data=data)

@router.put("/schedule/{tahun}/{bulan}/update-draft")
def update_schedule_draft(tahun: int, bulan: int, request: SchedulePublishRequest, admin_user: dict = Depends(admin_only)):
    modify_schedule_draft(tahun, bulan, request.hari_list)
    return success_response(message="Draft updated successfully")

@router.put("/schedule/{tahun}/{bulan}/publish")
def publish_schedule(tahun: int, bulan: int, request: SchedulePublishRequest, admin_user: dict = Depends(admin_only)):
    set_schedule_published(tahun, bulan, request.hari_list)
    return success_response(message="Schedule published successfully")

@router.put("/schedule/{tahun}/{bulan}/finalize")
def finalize_schedule(tahun: int, bulan: int, admin_user: dict = Depends(admin_only)):
    data = set_schedule_finalized(tahun, bulan)
    return success_response(data=data, message="Schedule finalized successfully")

@router.delete("/schedule/{tahun}/{bulan}/slot")
def delete_schedule_slot(tahun: int, bulan: int, tanggal: str, uid: str, admin_user: dict = Depends(admin_only)):
    remove_schedule_slot(tahun, bulan, tanggal, uid)
    return success_response(message=f"Successfully deleted BSU slot on {tanggal}")

@router.delete("/schedule/{tahun}/{bulan}")
def delete_monthly_schedule(tahun: int, bulan: int, admin_user: dict = Depends(admin_only)):
    remove_monthly_schedule(tahun, bulan)
    return success_response(message=f"Schedule for {tahun}-{bulan} has been deleted")
