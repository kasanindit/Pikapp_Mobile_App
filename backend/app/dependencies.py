from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# import jwt
from firebase_admin import auth

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials

        if token.startswith("Bearer "):
            token = token.split(" ")[1]

        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        return decoded_token

    except Exception as e:
        print("ERROR VERIFY:", e)
        raise HTTPException(status_code=401, detail="Invalid token")
