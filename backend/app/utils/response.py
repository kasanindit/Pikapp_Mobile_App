from fastapi.responses import JSONResponse

def success_response(data=None, message="Success", status_code=200) -> dict:
    response = {
        "success": True,
        "message": message
    }
    if data is not None:
        response["data"] = data
    
    return response

def error_response(message="Error", status_code=400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message
        }
    )
