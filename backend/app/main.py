from fastapi import FastAPI, Depends, HTTPException
from routers import admin, user
from dependencies import verify_token
from database import db
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print("Validation Error (422):", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

@app.get("/")
def welcome():
    return {
        "success": True,
        "message": "Welcome to API",
        "data": {
            "app_name": "ScheduleApp API",
            "version": "1.0.0"
        },
        "errors": None,
        "meta": {}
    }

@app.get("/user")
def get_current_user(decoded_token: dict = Depends(verify_token)):
    uid = decoded_token["uid"]

    docs = db.collection("users").where("uid", "==", uid).limit(1).stream()

    doc = next(docs, None)

    if not doc:
        raise HTTPException(404)

    data = doc.to_dict()

    return {
        "uid": uid,
        "email": data.get("email"),
        "username": data.get("username"),
        "role": data.get("role"),
    }

app.include_router(admin.router)
app.include_router(user.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
