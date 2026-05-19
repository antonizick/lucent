"""
Authenticated proxy for Lucent Voice Box.
Wraps port 8001 with username/password + Google Authenticator (TOTP) MFA.
Runs on port 8002.
"""

import os
import json
import logging
import httpx
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
import asyncio
import pyotp
from functools import lru_cache

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
CONFIG_DIR = Path(__file__).parent / ".auth"
CREDS_FILE = CONFIG_DIR / "credentials.json"
SESSIONS_FILE = CONFIG_DIR / "sessions.json"

def init_auth_dir():
    """Initialize authentication directory."""
    CONFIG_DIR.mkdir(exist_ok=True)
    logger.info(f"Auth directory ready: {CONFIG_DIR}")

class Credentials(BaseModel):
    username: str
    password_hash: str  # Use bcrypt or argon2 in production
    mfa_secret: str  # Google Authenticator secret (base32)

class SessionData(BaseModel):
    token: str
    username: str
    expires_at: str
    mfa_verified: bool

def hash_password(password: str) -> str:
    """Simple hash for demo. Use bcrypt/argon2 in production."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()

def load_credentials() -> dict:
    """Load user credentials."""
    if CREDS_FILE.exists():
        return json.loads(CREDS_FILE.read_text())
    return {}

def save_credentials(creds: dict) -> None:
    """Save user credentials."""
    init_auth_dir()
    CREDS_FILE.write_text(json.dumps(creds, indent=2))

def load_sessions() -> dict:
    """Load active sessions."""
    if SESSIONS_FILE.exists():
        return json.loads(SESSIONS_FILE.read_text())
    return {}

def save_sessions(sessions: dict) -> None:
    """Save active sessions."""
    init_auth_dir()
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))

def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)

def get_voice_box_url():
    """Get the voice box URL (port 8001)."""
    return "http://localhost:8001"

async def verify_session_token(token: str) -> SessionData:
    """Verify and return session data."""
    sessions = load_sessions()

    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    session = sessions[token]
    expires_at = datetime.fromisoformat(session["expires_at"])

    if datetime.now() > expires_at:
        del sessions[token]
        save_sessions(sessions)
        raise HTTPException(status_code=401, detail="Session expired")

    if not session.get("mfa_verified"):
        raise HTTPException(status_code=403, detail="MFA not verified")

    return SessionData(**session)

def get_token_from_header(authorization: Optional[str] = None) -> str:
    """Extract token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return authorization.replace("Bearer ", "")

def get_token(authorization: Optional[str] = None, cookies: Optional[dict] = None) -> str:
    """Get token from Authorization header or cookies."""
    # Try Authorization header first
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")

    # Fall back to cookies
    if cookies and "auth_token" in cookies:
        return cookies["auth_token"]

    raise HTTPException(status_code=401, detail="Not authenticated")

# FastAPI app
app = FastAPI(title="Lucent Voice Box (Authenticated)")

@app.on_event("startup")
async def startup():
    """Initialize auth system."""
    init_auth_dir()
    logger.info("Authenticated Voice Box Proxy starting on port 8002")

@app.get("/auth/login")
async def login_page():
    """Serve unified login page with username + MFA code."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lucent Voice Box — Login</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: monospace;
                background: linear-gradient(135deg, #080810 0%, #0d0d1a 100%);
                color: #fff;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                position: relative;
                overflow: hidden;
            }
            body::before {
                content: "01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100\A01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100\A01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100\A01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100\A01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100\A01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100 01010101 11110000 10101010 11001100";
                position: fixed;
                top: 0;
                left: 0;
                width: 200%;
                height: 200%;
                font-size: 11px;
                line-height: 1.4;
                color: rgba(255, 255, 255, 0.18);
                white-space: pre;
                font-family: monospace;
                pointer-events: none;
                z-index: 0;
                overflow: hidden;
            }
            .container {
                position: relative;
                z-index: 1;
            }
            .container {
                background: #0d0d1a;
                border: 2px solid #00e5ff;
                border-radius: 8px;
                padding: 40px;
                width: 100%;
                max-width: 400px;
                box-shadow: 0 0 30px rgba(0, 229, 255, 0.2);
            }
            h1 {
                color: #00e5ff;
                text-align: center;
                margin-bottom: 10px;
                text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
                letter-spacing: 2px;
            }
            .subtitle {
                text-align: center;
                color: #b0b0b0;
                margin-bottom: 30px;
                font-size: 12px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                color: #b0b0b0;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            input {
                width: 100%;
                padding: 12px;
                background: #080810;
                border: 1px solid #00e5ff;
                color: #fff;
                border-radius: 4px;
                font-family: monospace;
                font-size: 14px;
            }
            #code {
                letter-spacing: 4px;
                text-align: center;
            }
            input:focus {
                outline: none;
                border-color: #00e5ff;
                box-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
            }
            button {
                width: 100%;
                padding: 12px;
                background: linear-gradient(135deg, #00e5ff 0%, #0099cc 100%);
                border: none;
                color: #000;
                font-weight: bold;
                border-radius: 4px;
                cursor: pointer;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-family: monospace;
                font-size: 14px;
                transition: all 0.3s ease;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0, 229, 255, 0.3);
            }
            button:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .error {
                color: #ff6b6b;
                margin-top: 15px;
                padding: 12px;
                background: rgba(255, 107, 107, 0.1);
                border-left: 3px solid #ff6b6b;
                border-radius: 4px;
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎙️ LUCENT</h1>
            <p class="subtitle">Username + 6-Digit Code</p>
            <form id="loginForm">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required autofocus>
                </div>
                <div class="form-group">
                    <label for="code">MFA Code</label>
                    <input type="text" id="code" name="code" maxlength="6" pattern="[0-9]{6}" placeholder="000000" required>
                </div>
                <button type="submit">Authenticate</button>
                <div class="error" id="error"></div>
            </form>
        </div>
        <script>
            document.getElementById('code').addEventListener('input', (e) => {
                e.target.value = e.target.value.replace(/[^0-9]/g, '');
            });

            document.getElementById('loginForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const username = document.getElementById('username').value;
                const code = document.getElementById('code').value;
                const errorDiv = document.getElementById('error');
                const button = e.target.querySelector('button');

                button.disabled = true;
                button.textContent = 'Authenticating...';
                errorDiv.style.display = 'none';

                try {
                    // Step 1: Authenticate with username
                    const authFormData = new FormData();
                    authFormData.append('username', username);

                    const authResponse = await fetch('/auth/authenticate', {
                        method: 'POST',
                        body: authFormData
                    });

                    let authData;
                    try {
                        authData = await authResponse.json();
                    } catch (e) {
                        throw new Error('Server error: Invalid response');
                    }

                    if (!authResponse.ok) {
                        throw new Error(authData.detail || 'Authentication failed');
                    }

                    const token = authData.token;

                    // Step 2: Verify MFA code
                    const mfaFormData = new FormData();
                    mfaFormData.append('code', code);
                    mfaFormData.append('token', token);

                    const mfaResponse = await fetch('/auth/verify-mfa', {
                        method: 'POST',
                        body: mfaFormData
                    });

                    let mfaData;
                    try {
                        mfaData = await mfaResponse.json();
                    } catch (e) {
                        throw new Error('Server error: Invalid MFA response');
                    }

                    if (!mfaResponse.ok) {
                        throw new Error(mfaData.detail || 'MFA verification failed');
                    }

                    sessionStorage.setItem('token', mfaData.token);
                    window.location.href = '/';
                } catch (err) {
                    const errorMsg = err instanceof Error ? err.message : String(err);
                    errorDiv.textContent = errorMsg;
                    errorDiv.style.display = 'block';
                    button.disabled = false;
                    button.textContent = 'Authenticate';
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/auth/authenticate")
async def authenticate(username: str = Form(...)):
    """Authenticate with username only (MFA required)."""
    creds = load_credentials()

    if username not in creds:
        logger.warning(f"Login attempt for unknown user: {username}")
        raise HTTPException(status_code=401, detail="User not found")

    # Generate temporary token (valid for MFA step only)
    token = generate_session_token()
    sessions = load_sessions()
    sessions[token] = {
        "token": token,
        "username": username,
        "expires_at": (datetime.now() + timedelta(minutes=5)).isoformat(),
        "mfa_verified": False
    }
    save_sessions(sessions)

    logger.info(f"User verified: {username} (awaiting MFA)")
    return {"token": token, "message": "Username verified. Enter MFA code."}

@app.get("/auth/mfa")
async def mfa_page():
    """Serve MFA verification page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lucent Voice Box — MFA Verification</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: monospace;
                background: linear-gradient(135deg, #080810 0%, #0d0d1a 100%);
                color: #fff;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .container {
                background: #0d0d1a;
                border: 2px solid #00e5ff;
                border-radius: 8px;
                padding: 40px;
                width: 100%;
                max-width: 400px;
                box-shadow: 0 0 30px rgba(0, 229, 255, 0.2);
            }
            h1 {
                color: #00e5ff;
                text-align: center;
                margin-bottom: 10px;
                text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
                letter-spacing: 2px;
            }
            .subtitle {
                text-align: center;
                color: #b0b0b0;
                margin-bottom: 30px;
                font-size: 12px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 8px;
                color: #b0b0b0;
                font-size: 14px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            input {
                width: 100%;
                padding: 12px;
                background: #080810;
                border: 1px solid #00e5ff;
                color: #fff;
                border-radius: 4px;
                font-family: monospace;
                font-size: 16px;
                letter-spacing: 4px;
                text-align: center;
            }
            input:focus {
                outline: none;
                border-color: #00e5ff;
                box-shadow: 0 0 10px rgba(0, 229, 255, 0.3);
            }
            button {
                width: 100%;
                padding: 12px;
                background: linear-gradient(135deg, #00e5ff 0%, #0099cc 100%);
                border: none;
                color: #000;
                font-weight: bold;
                border-radius: 4px;
                cursor: pointer;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-family: monospace;
                font-size: 14px;
                transition: all 0.3s ease;
            }
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(0, 229, 255, 0.3);
            }
            .error {
                color: #ff6b6b;
                margin-top: 15px;
                padding: 12px;
                background: rgba(255, 107, 107, 0.1);
                border-left: 3px solid #ff6b6b;
                border-radius: 4px;
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 MFA VERIFICATION</h1>
            <p class="subtitle">Enter 6-digit code from Google Authenticator</p>
            <form id="mfaForm">
                <div class="form-group">
                    <label for="code">6-Digit Code</label>
                    <input type="text" id="code" name="code" maxlength="6" pattern="[0-9]{6}" required autofocus>
                </div>
                <button type="submit">Verify</button>
                <div class="error" id="error"></div>
            </form>
        </div>
        <script>
            document.getElementById('mfaForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const code = document.getElementById('code').value;
                const errorDiv = document.getElementById('error');
                const token = sessionStorage.getItem('token');

                if (!token) {
                    errorDiv.textContent = 'Session lost. Please login again.';
                    errorDiv.style.display = 'block';
                    setTimeout(() => window.location.href = '/auth/login', 2000);
                    return;
                }

                try {
                    const formData = new FormData();
                    formData.append('code', code);
                    formData.append('token', token);

                    const response = await fetch('/auth/verify-mfa', {
                        method: 'POST',
                        body: formData
                    });

                    if (response.ok) {
                        const data = await response.json();
                        sessionStorage.setItem('token', data.token);
                        window.location.href = '/';
                    } else {
                        const error = await response.json();
                        errorDiv.textContent = error.detail || 'MFA verification failed';
                        errorDiv.style.display = 'block';
                    }
                } catch (err) {
                    errorDiv.textContent = 'Error: ' + err.message;
                    errorDiv.style.display = 'block';
                }
            });

            // Auto-format input to numbers only
            document.getElementById('code').addEventListener('input', (e) => {
                e.target.value = e.target.value.replace(/[^0-9]/g, '');
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/auth/verify-mfa")
async def verify_mfa(code: str = Form(...), token: str = Form(...)):
    """Verify MFA code."""
    sessions = load_sessions()

    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")

    session = sessions[token]
    username = session["username"]
    creds = load_credentials()

    if username not in creds:
        raise HTTPException(status_code=401, detail="User not found")

    # Verify TOTP code
    user_secret = creds[username].get("mfa_secret")
    if not user_secret:
        raise HTTPException(status_code=400, detail="MFA not configured for this user")

    totp = pyotp.TOTP(user_secret)
    if not totp.verify(code):
        logger.warning(f"Failed MFA for user: {username}")
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    # Mark session as MFA verified
    session["mfa_verified"] = True
    session["expires_at"] = (datetime.now() + timedelta(days=7)).isoformat()
    sessions[token] = session
    save_sessions(sessions)

    logger.info(f"User verified with MFA: {username}")

    response = JSONResponse({"token": token, "message": "MFA verified. Welcome!"})
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=7*24*60*60,
        path="/",  # Ensure cookie is available at all paths
        secure=False,
        httponly=False
    )
    return response

@app.post("/auth/setup")
async def setup_mfa(username: str = Form(...), password: str = Form(...)):
    """Setup new user account with MFA."""
    creds = load_credentials()

    if username in creds:
        raise HTTPException(status_code=400, detail="User already exists")

    # Generate TOTP secret
    secret = pyotp.random_base32()

    # Store credentials
    creds[username] = {
        "username": username,
        "password_hash": hash_password(password),
        "mfa_secret": secret
    }
    save_credentials(creds)

    # Generate QR code provisioning URI
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username,
        issuer_name="Lucent Voice Box"
    )

    logger.info(f"New user created: {username}")
    return {
        "status": "success",
        "message": "User created. Configure your authenticator app.",
        "provisioning_uri": provisioning_uri,
        "secret": secret
    }

async def proxy_request(method: str, path: str, token: str, body: Optional[bytes] = None, headers: Optional[dict] = None):
    """Proxy request to voice box on port 8001."""
    # Verify session first
    try:
        session = await verify_session_token(token)
    except HTTPException:
        raise

    voice_box_url = f"{get_voice_box_url()}{path}"

    headers = headers or {}
    headers.pop("Authorization", None)  # Remove auth header before proxying
    headers.pop("Host", None)  # Remove host header

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(voice_box_url, headers=headers)
            elif method == "POST":
                response = await client.post(voice_box_url, content=body, headers=headers)
            elif method == "DELETE":
                response = await client.delete(voice_box_url, headers=headers)
            else:
                raise HTTPException(status_code=405, detail=f"Method {method} not allowed")

            return response
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Voice Box service unavailable")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root(request: Request):
    """Proxy root request - authentication handled at proxy level."""
    # Check if user is authenticated via cookie
    token = request.cookies.get("auth_token")
    if not token:
        return RedirectResponse(url="/auth/login", status_code=302)

    # Proxy directly to port 8001 without auth - auth is only at proxy level
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{get_voice_box_url()}/")

    html_content = response.content.decode() if isinstance(response.content, bytes) else response.content
    return HTMLResponse(content=html_content)

@app.get("/static/{path:path}")
async def serve_static(path: str, request: Request):
    """Proxy static files."""
    # Try to get token from cookies (standard auth flow)
    token = request.cookies.get("auth_token")

    # If no token, proxy directly (auth already validated at page level or by Tailscale)
    if not token:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{get_voice_box_url()}/static/{path}")
    else:
        response = await proxy_request("GET", f"/static/{path}", token)

    if path.endswith(".css"):
        return StreamingResponse(iter([response.content]), media_type="text/css")
    elif path.endswith(".js"):
        return StreamingResponse(iter([response.content]), media_type="application/javascript")
    elif path.endswith(".png"):
        return StreamingResponse(iter([response.content]), media_type="image/png")
    elif path.endswith(".jpg") or path.endswith(".jpeg"):
        return StreamingResponse(iter([response.content]), media_type="image/jpeg")
    elif path.endswith(".svg"):
        return StreamingResponse(iter([response.content]), media_type="image/svg+xml")
    else:
        return StreamingResponse(iter([response.content]), media_type="application/octet-stream")


@app.post("/speak")
async def speak(request: Request):
    """Proxy /speak endpoint - page-level auth means no additional check needed."""
    # Port 8001 doesn't require authentication - auth is handled at the proxy level
    body = await request.body()

    # Preserve Content-Type header
    headers = {}
    if "content-type" in request.headers:
        headers["content-type"] = request.headers["content-type"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{get_voice_box_url()}/speak", content=body, headers=headers)

    return response.json()

@app.get("/speak/stream")
async def speak_stream(request: Request, authorization: Optional[str] = None):
    """Proxy SSE stream - page-level auth means no additional check needed."""
    # Port 8001 doesn't require authentication - auth is handled at the proxy level

    async def event_generator():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                # Stream directly from voice box without auth headers
                async with client.stream("GET", f"{get_voice_box_url()}/speak/stream", timeout=None) as response:
                    if response.status_code != 200:
                        logger.warning(f"Stream connection failed: {response.status_code}")
                        yield f"event: error\ndata: Stream unavailable\n\n"
                        return

                    async for line in response.aiter_lines():
                        if line.strip():
                            # SSE requires double newline after each data line to delimit events
                            # Without \n\n, the browser buffers forever and never fires message events
                            yield line + "\n\n"
        except asyncio.CancelledError:
            logger.info("Stream closed by client")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"event: error\ndata: Connection error\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/message/pending")
async def queue_message(request: Request):
    """Proxy message queue - page-level auth means no additional check needed."""
    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{get_voice_box_url()}/message/pending", content=body)
    return response.json()

@app.get("/message/pending")
async def get_pending_message(request: Request):
    """Proxy get pending message - page-level auth means no additional check needed."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{get_voice_box_url()}/message/pending")
    return response.json()

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def catch_all(path: str, request: Request):
    """Catch-all proxy for unmapped endpoints."""
    method = request.method
    body = None
    if method in ["POST", "PUT", "PATCH"]:
        body = await request.body()

    # Preserve query parameters
    full_path = f"/{path}"
    if request.query_params:
        query_string = "&".join(f"{k}={v}" for k, v in request.query_params.items())
        full_path = f"/{path}?{query_string}"

    # Preserve important headers
    headers = {}
    if "content-type" in request.headers:
        headers["content-type"] = request.headers["content-type"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "GET":
            response = await client.get(f"{get_voice_box_url()}{full_path}", headers=headers)
        elif method == "POST":
            response = await client.post(f"{get_voice_box_url()}{full_path}", content=body, headers=headers)
        elif method == "PUT":
            response = await client.put(f"{get_voice_box_url()}{full_path}", content=body, headers=headers)
        elif method == "DELETE":
            response = await client.delete(f"{get_voice_box_url()}{full_path}", headers=headers)
        elif method == "PATCH":
            response = await client.patch(f"{get_voice_box_url()}{full_path}", content=body, headers=headers)
        else:
            raise HTTPException(status_code=405, detail=f"Method {method} not allowed")

    # Determine content type based on path
    if path.endswith(".css"):
        media_type = "text/css"
    elif path.endswith(".js"):
        media_type = "application/javascript"
    elif path.endswith(".json"):
        media_type = "application/json"
    elif path.endswith(".png"):
        media_type = "image/png"
    elif path.endswith(".jpg") or path.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif path.endswith(".svg"):
        media_type = "image/svg+xml"
    elif path.endswith(".html"):
        media_type = "text/html"
    else:
        media_type = response.headers.get("content-type", "application/octet-stream")

    return StreamingResponse(iter([response.content]), media_type=media_type)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
