from fastapi import APIRouter, Depends
from dependencies import verify_token
from models.request_models import ProfileUpdate, ScheduleRequestInput
from utils.firestore_helper import get_user_by_uid
from utils.response import success_response

from services.bsu_service import get_bsu_detail, update_bsu_profile
from services.periode_service import fetch_periode_status
from services.request_service import submit_schedule_request, remove_schedule_request
from services.schedule_service import fetch_published_schedule, fetch_my_schedule
from services.history_service import fetch_user_history
from services.holiday_service import fetch_indonesia_holidays

router = APIRouter(tags=["user"])

@router.get("/bsu-detail")
def get_current_bsu(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    data = get_bsu_detail(uid)
    return data

@router.put("/bsu/update")
def UpdateProfile(
    request: ProfileUpdate,
    target_uid: str | None = None,
    decoded_token: dict = Depends(verify_token)
):
    requester_uid = decoded_token["uid"]
    requester = get_user_by_uid(requester_uid) or {}
    is_admin = requester.get("role") == "admin"
    uid = target_uid if is_admin and target_uid else requester_uid
    update_payload = request.dict(exclude_unset=True)

    if not is_admin:
        update_payload.pop("is_active", None)

    user_data = update_bsu_profile(uid, update_payload)
    
    return {
        "message": "Profile updated successfully",
        "user_data": user_data
    }

@router.get("/periode/{tahun}/{bulan}/active")
def get_periode_active(tahun: int, bulan: int, decoded_token: dict = Depends(verify_token)):
    data = fetch_periode_status(tahun, bulan)
    return success_response(data=data)

@router.post("/schedule-request")
def create_schedule_request(request: ScheduleRequestInput, decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    data = submit_schedule_request(uid, request)
    return success_response(
        data=data,
        message="Schedule request submitted successfully"
    )

@router.get("/schedule")
def get_published_schedule(tahun: int, bulan: int, decoded_token: dict = Depends(verify_token)):
    data = fetch_published_schedule(tahun, bulan)
    return success_response(
        data=data,
        message="Successfully fetched published schedule"
    )

@router.get("/my-schedule")
def get_my_schedule(tahun: int, bulan: int, decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    data = fetch_my_schedule(uid, tahun, bulan)
    return success_response(
        data=data,
        message="Successfully fetched my schedule"
    )

@router.get("/history")
def get_history(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    data = fetch_user_history(uid)
    return success_response(
        data=data,
        message="Successfully fetched pickup history"
    )

@router.delete("/schedule-request/{request_id}")
def delete_my_request(request_id: str, decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]
    remove_schedule_request(uid, request_id)
    return success_response(message="Schedule request deleted successfully")

@router.get("/holidays")
def get_indonesia_holidays(
    tahun: int,
    bulan: int,
    decoded_token: dict = Depends(verify_token)
):
    data = fetch_indonesia_holidays(tahun, bulan)
    return success_response(
        data=data,
        message="Successfully fetched holidays"
    )
