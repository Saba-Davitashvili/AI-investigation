"""Small shared-password gate for a single-reviewer demo, not multi-user auth."""
import base64
import binascii
import os
import secrets

from starlette.responses import JSONResponse


def authorize_demo(request):
    password = os.getenv("DEMO_PASSWORD", "")
    if not password:
        if os.getenv("APP_ENV", "local") == "production":
            return JSONResponse({"detail": "Demo access is not configured."}, status_code=503)
        return None

    challenge = {"WWW-Authenticate": 'Basic realm="Trace demo", charset="UTF-8"'}
    try:
        scheme, value = request.headers.get("authorization", "").split(" ", 1)
        if scheme.lower() != "basic":
            raise ValueError("Unsupported authentication scheme")
        username, supplied = base64.b64decode(value, validate=True).decode("utf-8").split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return JSONResponse({"detail": "Authentication required."}, status_code=401, headers=challenge)

    user_ok = secrets.compare_digest(username.encode(), os.getenv("DEMO_USERNAME", "reviewer").encode())
    password_ok = secrets.compare_digest(supplied.encode(), password.encode())
    if not (user_ok and password_ok):
        return JSONResponse({"detail": "Invalid demo credentials."}, status_code=401, headers=challenge)

    # Browser Basic credentials are ambient. Reject cross-origin writes.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site writes are not allowed."}, status_code=403)
        origin = request.headers.get("origin")
        expected = (os.getenv("PUBLIC_ORIGIN") or str(request.base_url).rstrip("/"))
        if origin and origin.rstrip("/") != expected.rstrip("/"):
            return JSONResponse({"detail": "Cross-origin writes are not allowed."}, status_code=403)
    return None
