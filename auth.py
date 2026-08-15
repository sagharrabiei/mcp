import time, secrets, hashlib, base64
import jwt
from starlette.responses import RedirectResponse, JSONResponse
from starlette.routing import Route
from dotenv import load_dotenv
import os

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")

auth_codes = {}

async def authorize(request):
    params = request.query_params
    if params.get("client_id") != CLIENT_ID:
        return JSONResponse({"error": "invalid_client"}, status_code=400)
    code = secrets.token_urlsafe(32)
    auth_codes[code] = {
        "code_challenge": params["code_challenge"],
        "expires_at": time.time() + 300,
    }
    return RedirectResponse(f"{params['redirect_uri']}?code={code}")

async def token(request):
    form = await request.form()
    entry = auth_codes.pop(form.get("code"), None)
    if entry is None or entry["expires_at"] < time.time():
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    check = base64.urlsafe_b64encode(
        hashlib.sha256(form["code_verifier"].encode()).digest()
    ).decode().rstrip("=")
    if check != entry["code_challenge"]:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    access_token = jwt.encode(
        {"sub": "user", "exp": time.time() + 3600}, SECRET_KEY, algorithm="HS256"
    )
    return JSONResponse({"access_token": access_token, "token_type": "Bearer"})

auth_routes = [
    Route("/authorize", authorize),
    Route("/token", token, methods=["POST"]),
]