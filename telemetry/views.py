# telemetry/views.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import deque

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.http import (
    JsonResponse,
    Http404,
    FileResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import render, redirect
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

log = logging.getLogger(__name__)

# ----------------------------- AUTH -----------------------------

def signup(request):
    """
    Minimal username/password signup. On success, auto-login and go to dashboard.
    """
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        if not username or not password:
            return render(
                request,
                "registration/signup.html",
                {"error": "Username and password are required."},
            )
        if User.objects.filter(username=username).exists():
            return render(
                request,
                "registration/signup.html",
                {"error": "Username already taken."},
            )
        user = User.objects.create_user(username=username, password=password)
        login(request, user)
        return redirect("dashboard")
    return render(request, "registration/signup.html")


# ------------------------- ROUTER / PAGES -----------------------

def home(request):
    """
    Root router:
      - if not authenticated -> /accounts/login/
      - if authenticated      -> dashboard
    """
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


@login_required
def dashboard(request):
    """
    Single-page dashboard with the square map.
    The map JS hits /api/current/ (real) or /api/mock/... (demo).
    """
    return render(request, "telemetry/dashboard.html")


@login_required
def person_page(request, pid: str):
    """
    Soldier/device detail page. The frontend fetches:
      - /api/mock/person/<pid>/   (demo/offline), OR
      - your real per-person API (if you wire one).
    """
    return render(request, "telemetry/person.html", {"pid": pid})


# -------------------------- DOWNLOADS ---------------------------

@login_required
def download_latest_workbook(request):
    """
    Serve the latest daily Excel workbook if present (e.g., exports created
    by your logger/cron). Expects files named like vitals_YYYY-MM-DD.xlsx
    under settings.EXCEL_DIR. If multiple, picks the newest.
    """
    excel_dir = Path(settings.EXCEL_DIR)
    if not excel_dir.exists():
        raise Http404("EXCEL_DIR does not exist.")
    xlsxs = sorted(excel_dir.glob("vitals_*.xlsx"))
    if not xlsxs:
        raise Http404("No workbook found in EXCEL_DIR.")
    latest = xlsxs[-1]
    return FileResponse(open(latest, "rb"), as_attachment=True, filename=latest.name)


# ---------------------------- MOCK ------------------------------

def _mock_people_json():
    path = Path(__file__).resolve().parent.parent / "static" / "data" / "people.json"
    if not path.exists():
        raise Http404("static/data/people.json not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@login_required
@require_GET
def api_mock_people(request):
    return JsonResponse(_mock_people_json())


@login_required
@require_GET
def api_mock_person(request, pid: str):
    data = _mock_people_json()
    for p in data.get("people", []):
        if str(p.get("id")) == str(pid):
            return JsonResponse(p)
    raise Http404("Person not found")


# ------------------------ REAL (AWS) DATA -----------------------

def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _parse_ts_iso(s: str):
    """
    Accepts '...Z' or ISO8601 with offset; returns aware UTC datetime, or None.
    """
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


@login_required
@require_GET
def api_current_all(request):
    """
    /api/current/ fetches current positions/vitals from your live endpoint.

    Query:
      - ?device_id=ID or ?device_id=ID1,ID2   -> explicit devices
      - ?limit=N (default "1")                -> how many latest items per device
      - ?max_age_min=M (optional)             -> hide items older than M minutes
      - none                                  -> uses settings.VITALS_DEVICE_IDS
      - still none                            -> uses settings.VITALS_DEFAULT_DEVICE_ID

    Returns: {"items":[{device_id, person_id, person, label, lat, lon, hr, spo2, temp, bp_sys, bp_dia, ts}, ...]}
             (only entries with valid lat+lon and fresh timestamps are returned)
    """
    api_url = (getattr(settings, "VITALS_API_URL", "") or "").strip()
    secret  = (getattr(settings, "VITALS_API_SECRET", "") or "").strip()
    timeout = int(getattr(settings, "VITALS_API_TIMEOUT", 10))

    # If you haven't set up the live API yet, return empty (frontend may fall back to mock).
    if not api_url:
        return JsonResponse({"items": [], "note": "VITALS_API_URL not configured"})

    # Devices to pull
    raw_ids = (request.GET.get("device_id") or "").strip()
    ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
    if not ids:
        ids = list(getattr(settings, "VITALS_DEVICE_IDS", []))
    if not ids:
        default_id = (getattr(settings, "VITALS_DEFAULT_DEVICE_ID", "") or "").strip()
        if default_id:
            ids = [default_id]

    # How many records / how fresh
    limit = (request.GET.get("limit") or "1").strip()
    try:
        limit = str(max(1, int(limit)))
    except ValueError:
        limit = "1"

    # Staleness window (minutes)
    try:
        max_age_min = int(request.GET.get("max_age_min") or "")
    except (TypeError, ValueError):
        max_age_min = int(getattr(settings, "DEVICES_MAX_AGE_MIN", 10))
    now_utc = datetime.now(timezone.utc)

    headers = {}
    if secret:
        headers["x-ingest-secret"] = secret

    merged = []
    for dev_id in ids:
        try:
            params = {"device_id": dev_id, "limit": limit}
            r = requests.get(api_url, params=params, headers=headers, timeout=timeout)
            log.info("GET %s | %s", r.url, r.status_code)

            if r.status_code >= 400:
                # log upstream error but keep going for other devices
                try:
                    log.warning("Upstream error for %s: %s", dev_id, r.json())
                except Exception:
                    log.warning("Upstream error for %s: %s", dev_id, r.text)
                continue

            payload = r.json() if r.content else {}
            items = payload.get("items", [])

            for it in items:
                # Timestamp filter
                ts_str = it.get("timestamp")
                ts_dt = _parse_ts_iso(ts_str) if ts_str else None
                if not ts_dt:
                    continue
                age_min = (now_utc - ts_dt).total_seconds() / 60.0
                if age_min > max_age_min:
                    continue

                merged.append({
                    "device_id": it.get("device_id") or dev_id,
                    "person_id": it.get("device_id") or dev_id,
                    "person": it.get("label") or it.get("device_id") or dev_id,
                    "label":  it.get("label") or it.get("device_id") or dev_id,
                    "lat": _to_float(it.get("lat")),
                    "lon": _to_float(it.get("lon")),
                    "hr": it.get("hr"),
                    "spo2": it.get("spo2"),
                    "temp": it.get("temp_c"),
                    "bp_sys": it.get("bp_sys"),
                    "bp_dia": it.get("bp_dia"),
                    "ts": ts_str,
                })

        except requests.RequestException:
            log.exception("Live API request failed for device %s", dev_id)

    # Only plot valid coordinates
    merged = [p for p in merged if p.get("lat") is not None and p.get("lon") is not None]
    return JsonResponse({"items": merged})


# ---------------------- TEMP TEST POSTBOX -----------------------

_POSTBOX = deque(maxlen=50)  # last 50 test posts (for local/dev testing)

@csrf_exempt
def postbox_ingest(request):
    """
    POST any JSON to /debug/postbox/data/ and see it on /debug/postbox/.
    GET returns the stored messages as JSON (page polls this).
    """
    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
        except Exception:
            return HttpResponseBadRequest("invalid JSON")

        _POSTBOX.appendleft({
            "ts": now().isoformat(),
            "payload": payload,
        })
        return JsonResponse({"ok": True, "count": len(_POSTBOX)})
    return JsonResponse({"items": list(_POSTBOX)})


# ---------------------- PROFILE & PASSWORD ----------------------

@login_required
def postbox_page(request):
    return render(request, "telemetry/postbox.html")


@login_required
def profile(request):
    """
    Simple profile page: shows current user's details and a logout button.
    """
    return render(request, "registration/profile.html", {
        "user_obj": request.user,
    })


@login_required
@require_http_methods(["GET", "POST"])
def password_change_request(request):
    """
    Ask for confirmation, then email a password-reset link to the logged-in user's email.
    This uses Django's PasswordResetForm underneath.
    """
    if not request.user.email:
        messages.error(request, "No email address on your account. Please add one and try again.")
        return redirect("profile")

    if request.method == "POST":
        form = PasswordResetForm({"email": request.user.email})
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                email_template_name="registration/password_reset_email.html",
                subject_template_name="registration/password_reset_subject.txt",
            )
            return redirect("password_reset_done")  # builtin Django URL
        messages.error(request, "Could not send email. Please try again.")

    return render(
        request,
        "registration/password_change_request.html",
        {"user_email": request.user.email},
    )
