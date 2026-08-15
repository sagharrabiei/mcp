import time, secrets, hashlib, base64
import jwt
from starlette.responses import RedirectResponse, JSONResponse
from starlette.routing import Route
from dotenv import load_dotenv
import os

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
BASE_URL = os.getenv("BASE_URL") 

auth_codes = {}
registered_clients = {}    

async def register(request):               # <-- new
    body = await request.json()
    client_id = secrets.token_urlsafe(16)
    registered_clients[client_id] = {
        "redirect_uris": body["redirect_uris"],
    }
    return JSONResponse({
        "client_id": client_id,
        "redirect_uris": body["redirect_uris"],
        "token_endpoint_auth_method": "none",
    }, status_code=201)

async def authorize(request):
    params = request.query_params
    
    client = registered_clients.get(params.get("client_id"))   # <-- changed

    if client is None:                                          # <-- changed
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    redirect_uri = params["redirect_uri"]
    if redirect_uri not in client["redirect_uris"]:             # <-- new
        return JSONResponse({"error": "invalid_redirect_uri"}, status_code=400)
    
    state = params.get("state")  # <-- new

    code = secrets.token_urlsafe(32)
    auth_codes[code] = {
        "code_challenge": params["code_challenge"],
        "expires_at": time.time() + 300,
    }

    redirect_url = f"{params['redirect_uri']}?code={code}"
    if state is not None:
        redirect_url += f"&state={state}"

    return RedirectResponse(redirect_url)

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

async def metadata(request):                # <-- new
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/authorize",
        "token_endpoint": f"{BASE_URL}/token",
        "registration_endpoint": f"{BASE_URL}/register",
        "code_challenge_methods_supported": ["S256"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
    })

auth_routes = [
    Route("/.well-known/oauth-authorization-server", metadata),   # <-- new
    Route("/register", register, methods=["POST"]),     
    Route("/authorize", authorize),
    Route("/token", token, methods=["POST"]),
]