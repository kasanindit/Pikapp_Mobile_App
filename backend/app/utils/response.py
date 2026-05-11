from fastapi.responses import JSONResponse

def success_response(data=None, message="Success", status_code=200) -> dict:
    """Standard success response format."""
    response = {
        "success": True,
        "message": message
    }
    if data is not None:
        response["data"] = data
        
    # We return dict directly so FastAPI can serialize it and handle the status_code in the router,
    # OR we can return a JSONResponse if we want to enforce status code here.
    # Given the existing code mostly returns dicts, returning a dict is safer for compatibility.
    return response

def error_response(message="Error", status_code=400) -> JSONResponse:
    """Standard error response format using JSONResponse."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message
        }
    )
