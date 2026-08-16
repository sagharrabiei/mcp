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

ACCESS_TOKEN_TTL = 3600              # 1 hour
REFRESH_TOKEN_TTL = 30 * 24 * 3600   # 30 days


def _issue_access_token(sub: str) -> str:
    """Self-contained access token (JWT) verified statelessly by the MCP server."""
    return jwt.encode(
        {"sub": sub, "token_type": "access", "exp": time.time() + ACCESS_TOKEN_TTL},
        SECRET_KEY,
        algorithm="HS256",
    )


def _issue_refresh_token(sub: str) -> str:
    """Long-lived, rotation-capable refresh token. Stateless so it verifies on any instance."""
    return jwt.encode(
        {"sub": sub, "token_type": "refresh", "exp": time.time() + REFRESH_TOKEN_TTL},
        SECRET_KEY,
        algorithm="HS256",
    )


def _token_response(sub: str) -> dict:
    return {
        "access_token": _issue_access_token(sub),
        "refresh_token": _issue_refresh_token(sub),
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL,
    }    

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
    grant_type = form.get("grant_type", "authorization_code")

    # grant_type=refresh_token: swap an unexpired refresh token for a fresh pair
    if grant_type == "refresh_token":
        refresh_token = form.get("refresh_token")
        if not refresh_token:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        if payload.get("token_type") != "refresh":
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        sub = payload.get("sub")
        if not sub:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        # Rotate: return a brand-new pair so a leaked token can't be replayed.
        return JSONResponse(_token_response(sub))

    # default: authorization_code + PKCE
    entry = auth_codes.pop(form.get("code"), None)
    if entry is None or entry["expires_at"] < time.time():
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    check = base64.urlsafe_b64encode(
        hashlib.sha256(form["code_verifier"].encode()).digest()
    ).decode().rstrip("=")
    if check != entry["code_challenge"]:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    return JSONResponse(_token_response("user"))

async def metadata(request):                # <-- new
    return JSONResponse({
        "issuer": BASE_URL,
        "authorization_endpoint": f"{BASE_URL}/authorize",
        "token_endpoint": f"{BASE_URL}/token",
        "registration_endpoint": f"{BASE_URL}/register",
        "code_challenge_methods_supported": ["S256"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
    })

auth_routes = [
    Route("/.well-known/oauth-authorization-server", metadata),   # <-- new
    Route("/register", register, methods=["POST"]),     
    Route("/authorize", authorize),
    Route("/token", token, methods=["POST"]),
]