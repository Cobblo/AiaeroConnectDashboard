# telemetry/views.py
from __future__ import annotations

import json
import logging
import os
import csv
import math
from io import StringIO
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from collections import deque
from typing import Any, Iterable

import requests
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.http import (
    JsonResponse,
    Http404,
    FileResponse,
    HttpResponseBadRequest,
    HttpResponse,
)
from django.shortcuts import render, redirect
from django.utils import timezone as dj_tz
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .models import Device, Reading

log = logging.getLogger(__name__)

# ----------------------------- AUTH -----------------------------


def signup(request):
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
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


@login_required
def dashboard(request):
    return render(request, "telemetry/dashboard.html")


@login_required
def person_page(request, pid: str):
    return render(request, "telemetry/person.html", {"pid": pid})


@login_required
def person_auto(request):
    """Renders the same template but signals the frontend to auto-select the newest device."""
    return render(request, "telemetry/person.html", {"pid": "AUTO"})


# -------------------------- DOWNLOADS --------------------------


@login_required
def download_latest_workbook(request):
    excel_dir = Path(getattr(settings, "EXCEL_DIR", Path.cwd()))
    if not excel_dir.exists():
        raise Http404("EXCEL_DIR does not exist.")
    xlsxs = sorted(excel_dir.glob("vitals_*.xlsx"))
    if not xlsxs:
        raise Http404("No workbook found in EXCEL_DIR.")
    latest = xlsxs[-1]
    return FileResponse(open(latest, "rb"), as_attachment=True, filename=latest.name)


# ---------------------------- MOCK -----------------------------


def _mock_people_json():
    path = (
        Path(__file__).resolve().parent.parent
        / "static"
        / "data"
        / "people.json"
    )
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


# ------------------------ Helpers ------------------------------


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_ts_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except Exception:
        return None


def _parse_ts_any(ts_raw):
    """Accept ISO, epoch number, or numeric string."""
    if ts_raw is None or ts_raw == "":
        return None
    if isinstance(ts_raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
        except Exception:
            return None
    s = str(ts_raw).strip()
    if s.isdigit():
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except Exception:
            pass
    return _parse_ts_iso(s)


def _sanitize_ts(ts: datetime | None):
    """
    STRICT mode: return ts if valid; otherwise None.
    (Prevents missing/bad timestamps from being treated as 'now'.)
    """
    if not ts:
        return None
    try:
        if ts.year < 2010:
            return None
    except Exception:
        return None
    return ts


def _shape_to_list(obj: Any) -> list[dict]:
    """Accept {"items":[...]}, {"Items":[...]}, [...],
    {"dev1":{...},"dev2":{...}}?,
    {"body":"<json>"} (API Gateway), or stringified JSON.
    """
    import json as _json

    if obj is None:
        return []

    if isinstance(obj, dict):
        # API Gateway proxy: body can be string JSON
        if "body" in obj and isinstance(obj["body"], str):
            try:
                return _shape_to_list(_json.loads(obj["body"]))
            except Exception:
                return []

        if isinstance(obj.get("items"), list):
            return [x for x in obj["items"] if isinstance(x, dict)]
        if isinstance(obj.get("Items"), list):
            return [x for x in obj["Items"] if isinstance(x, dict)]

        # dict-of-dicts
        vals = list(obj.values())
        return [v for v in vals if isinstance(v, dict)]

    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]

    if isinstance(obj, str):
        try:
            return _shape_to_list(_json.loads(obj))
        except Exception:
            return []

    return []


def _pick(data: dict, *keys, default=None):
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    return default


def _merge_rows_into(items: list[dict], rows: Iterable[dict], cutoff_utc: datetime):
    """
    Merge rows from a live API into the unified items list.

    Supports both per-reading rows and the /vitals/devices registry rows:
      - timestamp/ts/last_seen/lastSeen
      - lat/lon OR last_lat/last_lon or gps.{lat,lon}
    Drops rows whose timestamp is missing/invalid or older than cutoff.
    """
    for it in rows or []:
        ts_raw = _pick(it, "timestamp", "ts", "last_seen", "lastSeen")
        ts = _sanitize_ts(_parse_ts_any(ts_raw))
        if not ts or ts < cutoff_utc:
            continue

        lat = _to_float(_pick(it, "lat", "last_lat", "latitude", "Latitude"))
        lon = _to_float(_pick(it, "lon", "last_lon", "longitude", "Longitude"))
        if lat is None or lon is None:
            gps = it.get("gps") or {}
            lat = _to_float(_pick(gps, "lat", "latitude", "Latitude"))
            lon = _to_float(_pick(gps, "lon", "longitude", "Longitude"))
        if lat is None or lon is None:
            continue

        dev_id = _pick(it, "device_id", "deviceId", "node_id", "id")
        label = _pick(it, "label", "person", default=dev_id)

        data_blk = it.get("data") or {}
        hr = _pick(it, "hr", "HR", default=_pick(data_blk, "hr", "HR"))
        spo2 = _pick(it, "spo2", "SpO2", default=_pick(data_blk, "spo2", "SpO2"))
        temp = _pick(
            it,
            "temp_c",
            "temp",
            "temperature",
            default=_pick(data_blk, "temp_c", "Temp", "temperature"),
        )
        bp_sys = _pick(
            it, "bp_sys", "systolic", default=_pick(data_blk, "bp_sys", "systolic")
        )
        bp_dia = _pick(
            it, "bp_dia", "diastolic", default=_pick(data_blk, "bp_dia", "diastolic")
        )

        items.append(
            {
                "device_id": dev_id,
                "person_id": dev_id,
                "person": label,
                "label": label,
                "lat": lat,
                "lon": lon,
                "hr": hr,
                "spo2": spo2,
                "temp": temp,
                "bp_sys": bp_sys,
                "bp_dia": bp_dia,
                "ts": ts.isoformat(),
            }
        )


# ----- TRACKING HELPERS (distance + trip grouping) -----


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Returns distance in kilometres between two lat/lon points.
    """
    R = 6371.0  # Earth radius in km

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _build_segment_from_readings(readings: list[Reading], seg_index: int) -> dict:
    """
    Build a single trip segment dict from a list of Reading rows.
    """
    total_km = 0.0
    coords: list[dict] = []
    prev_lat: float | None = None
    prev_lon: float | None = None

    for r in readings:
        if r.lat is None or r.lon is None:
            continue

        lat = float(r.lat)
        lon = float(r.lon)
        local_ts = dj_tz.localtime(r.ts)

        coords.append(
            {
                "lat": lat,
                "lng": lon,
                "time": local_ts.strftime("%H:%M:%S"),
            }
        )

        if prev_lat is not None and prev_lon is not None:
            total_km += _haversine_km(prev_lat, prev_lon, lat, lon)

        prev_lat, prev_lon = lat, lon

    if not coords:
        return {}

    start_local = dj_tz.localtime(readings[0].ts)
    end_local = dj_tz.localtime(readings[-1].ts)

    return {
        "id": seg_index,
        "start_time": start_local.strftime("%H:%M"),
        "end_time": end_local.strftime("%H:%M"),
        "distance_km": round(total_km, 2),
        "points": coords,
    }


def _build_trip_segments_from_readings(
    readings: list[Reading], max_gap_minutes: int = 30
) -> list[dict]:
    """
    Group Reading rows into trips based on time gaps.
    If gap between two points > max_gap_minutes → new trip.
    """
    segments: list[dict] = []
    if not readings:
        return segments

    current: list[Reading] = []
    prev_ts: datetime | None = None
    gap = timedelta(minutes=max_gap_minutes)

    for r in readings:
        ts = r.ts
        if prev_ts is not None and (ts - prev_ts) > gap:
            if len(current) >= 2:
                seg = _build_segment_from_readings(current, len(segments) + 1)
                if seg:
                    segments.append(seg)
            current = []

        current.append(r)
        prev_ts = ts

    # close last trip
    if len(current) >= 2:
        seg = _build_segment_from_readings(current, len(segments) + 1)
        if seg:
            segments.append(seg)

    return segments


# --------------------- CLOUD API PROXIES -----------------------


@login_required
@require_GET
def api_devices(request):
    devices_url = (getattr(settings, "VITALS_DEVICES_URL", "") or "").strip()
    if not devices_url:
        return JsonResponse([], safe=False)

    mins = int(
        request.GET.get(
            "active_minutes", getattr(settings, "DEVICES_MAX_AGE_MIN", 10)
        )
    )
    headers = (
        {"x-ingest-secret": settings.VITALS_API_SECRET}
        if getattr(settings, "VITALS_API_SECRET", "")
        else {}
    )
    try:
        r = requests.get(
            devices_url,
            params={"active_minutes": mins},
            headers=headers,
            timeout=getattr(settings, "VITALS_API_TIMEOUT", 10),
        )
        if r.ok:
            return JsonResponse(r.json(), safe=False)
        log.warning(
            "api_devices proxy failed %s -> %s body=%s",
            r.url,
            r.status_code,
            r.text[:300],
        )
    except requests.RequestException:
        log.exception("api_devices proxy error")
    return JsonResponse([], safe=False)


@login_required
@require_GET
def api_readings(request):
    base_url = (getattr(settings, "VITALS_API_URL", "") or "").strip()
    if not base_url:
        return JsonResponse([], safe=False)

    device_id = request.GET.get("device_id")
    limit = int(request.GET.get("limit", 50))
    headers = (
        {"x-ingest-secret": settings.VITALS_API_SECRET}
        if getattr(settings, "VITALS_API_SECRET", "")
        else {}
    )
    try:
        r = requests.get(
            base_url,
            params={"device_id": device_id, "limit": str(limit)},
            headers=headers,
            timeout=getattr(settings, "VITALS_API_TIMEOUT", 10),
        )
        if r.ok:
            return JsonResponse(r.json(), safe=False)
        log.warning(
            "api_readings proxy failed %s -> %s body=%s",
            r.url,
            r.status_code,
            r.text[:300],
        )
    except requests.RequestException:
        log.exception("api_readings proxy error")
    return JsonResponse([], safe=False)


# ------------------------ RECENT DEVICES API -------------------


@login_required
@require_GET
def api_current_recent(request):
    """
    Returns latest vitals for all devices seen recently from:
      A) Local ingest cache (/ingest/v1)
      B) Cloud LoRa registry (/vitals/devices)
      C) GSM cloud registry (/vitals_gsm/devices)
      D) LoRa fallback (/vitals or per-device)

    This version ensures that all devices are shown on the map,
    even if their 'ts' is old — it uses last_seen or ts_iso as the current timestamp.
    """
    # ---- Active minutes ----
    try:
        override = request.GET.get("active_minutes")
        max_age_min = (
            int(override)
            if override
            else int(getattr(settings, "DEVICES_MAX_AGE_MIN", 10))
        )
    except (TypeError, ValueError):
        max_age_min = int(getattr(settings, "DEVICES_MAX_AGE_MIN", 10))

    cutoff = dj_tz.now().astimezone(timezone.utc) - timedelta(minutes=max_age_min)
    items: list[dict] = []

    # ==========================================================
    # A) Local ingest cache
    # ==========================================================
    global _RECENT_CACHE
    cache_vals = []
    try:
        cache_vals = list(_RECENT_CACHE.values())
    except NameError:
        pass

    for it in cache_vals:
        ts = it.get("ts")
        if isinstance(ts, datetime):
            ts_utc = _sanitize_ts(ts.astimezone(timezone.utc))
        else:
            ts_utc = _sanitize_ts(_parse_ts_any(ts))
        if not ts_utc:
            continue

        lat = _to_float(it.get("lat"))
        lon = _to_float(it.get("lon"))
        if lat is None or lon is None:
            continue

        dev_id = it.get("device_id")
        label = it.get("label") or dev_id
        items.append(
            {
                "device_id": dev_id,
                "person_id": dev_id,
                "person": label,
                "label": label,
                "lat": lat,
                "lon": lon,
                "hr": it.get("hr"),
                "spo2": it.get("spo2"),
                "temp": it.get("temp_c"),
                "bp_sys": it.get("bp_sys"),
                "bp_dia": it.get("bp_dia"),
                "ts": ts_utc.isoformat(),
            }
        )

    # ==========================================================
    # B) Cloud LoRa registry (/vitals/devices)
    # ==========================================================
    devices_url = (getattr(settings, "VITALS_DEVICES_URL", "") or "").strip()
    base_url = (getattr(settings, "VITALS_API_URL", "") or "").strip()
    secret = (
        getattr(settings, "VITALS_API_SECRET", "")
        or getattr(settings, "VITALS_SECRET", "")
        or ""
    ).strip()
    timeout = int(getattr(settings, "VITALS_API_TIMEOUT", 10))
    headers = {"x-ingest-secret": secret} if secret else {}

    def merge_rows(rows: list[dict]):
        """Internal helper to append normalized items from AWS JSON."""
        for it in rows or []:
            # ✅ prefer last_seen or ts_iso (they are newest)
            ts_raw = _pick(
                it,
                "last_seen",
                "lastSeen",
                "ts_iso",
                "timestamp",
                "ts",
            )
            ts = _sanitize_ts(_parse_ts_any(ts_raw))
            if not ts:
                continue

            lat = _to_float(_pick(it, "lat", "last_lat", "latitude"))
            lon = _to_float(_pick(it, "lon", "last_lon", "longitude"))
            if lat is None or lon is None:
                gps = it.get("gps") or {}
                lat = _to_float(_pick(gps, "lat", "latitude"))
                lon = _to_float(_pick(gps, "lon", "longitude"))
            if lat is None or lon is None:
                continue

            dev_id = _pick(it, "device_id", "deviceId", "node_id", "id")
            label = _pick(it, "label", "person", default=dev_id)
            data_blk = it.get("data") or {}

            items.append(
                {
                    "device_id": dev_id,
                    "person_id": dev_id,
                    "person": label,
                    "label": label,
                    "lat": lat,
                    "lon": lon,
                    "hr": _pick(it, "hr", default=_pick(data_blk, "hr")),
                    "spo2": _pick(it, "spo2", default=_pick(data_blk, "spo2")),
                    "temp": _pick(it, "temp_c", "temp", default=_pick(data_blk, "temp")),
                    "bp_sys": _pick(it, "bp_sys", default=_pick(data_blk, "bp_sys")),
                    "bp_dia": _pick(it, "bp_dia", default=_pick(data_blk, "bp_dia")),
                    "ts": ts.isoformat(),
                }
            )

    registry_ok = False
    if devices_url:
        try:
            r = requests.get(devices_url, headers=headers, timeout=timeout)
            log.info("AWS registry GET %s -> %s", r.url, r.status_code)
            if r.ok:
                rows = _shape_to_list(r.json() if r.content else {})
                if rows:
                    merge_rows(rows)
                    registry_ok = True
            else:
                log.warning("AWS registry body: %s", (r.text or "")[:500])
        except requests.RequestException:
            log.exception("AWS registry fetch failed")

    # ==========================================================
    # C) LoRa fallbacks (/vitals or per-device)
    # ==========================================================
    if base_url and not registry_ok:
        try:
            r = requests.get(base_url, headers=headers, params={"limit": "50"}, timeout=timeout)
            if r.ok:
                rows = _shape_to_list(r.json() if r.content else {})
                merge_rows(rows)
        except requests.RequestException:
            log.exception("LoRa bulk fetch failed")

    # ==========================================================
    # D) GSM registry (vitals_latest_gsm)
    # ==========================================================
    gsm_devices_url = (getattr(settings, "VITALS_GSM_DEVICES_URL", "") or "").strip()
    gsm_base_url = (getattr(settings, "VITALS_GSM_API_URL", "") or "").strip()
    gsm_url = gsm_devices_url or gsm_base_url

    if gsm_url:
        try:
            r = requests.get(gsm_url, headers=headers, timeout=timeout)
            log.info("GSM registry GET %s -> %s", r.url, r.status_code)
            if r.ok:
                rows = _shape_to_list(r.json() if r.content else {})
                merge_rows(rows)
        except requests.RequestException:
            log.exception("GSM registry fetch failed")

    # ----------------------------------------------------------
    # E) Normalize and de-duplicate by device_id
    # ----------------------------------------------------------
    latest_by_id: dict[str, dict] = {}
    for it in items:
        dev_id = str(it.get("device_id") or "").strip()
        if not dev_id:
            continue
        label = (it.get("label") or dev_id).strip()
        it["device_id"] = dev_id
        it["label"] = label

        ts = _parse_ts_any(it.get("ts"))
        if not ts:
            continue

        prev = latest_by_id.get(dev_id)
        if not prev:
            latest_by_id[dev_id] = it
        else:
            prev_ts = _parse_ts_any(prev.get("ts"))
            if not prev_ts or ts > prev_ts:
                latest_by_id[dev_id] = it

    items = list(latest_by_id.values())

    # ----------------------------------------------------------
    # Final payload
    # ----------------------------------------------------------
    return JsonResponse({"items": items})


# ✅ LEGACY WRAPPER (for old URL /api/current/)
@login_required
@require_GET
def api_current_all(request):
    """
    Legacy wrapper so existing URLs that point to api_current_all
    will still work. It simply delegates to api_current_recent().
    """
    return api_current_recent(request)


# ---------------------- LOCAL INGEST (POST) --------------------


@csrf_exempt
@require_http_methods(["POST"])
def ingest_vitals(request):
    """
    Devices POST JSON here (header: x-ingest-secret must match settings.INGEST_SECRET):
    Accepts node_id OR device_id and optional label.
    """
    if request.headers.get("x-ingest-secret", "") != settings.INGEST_SECRET:
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"error": "invalid json"}, status=400)

    device_id = (
        (payload.get("device_id") or payload.get("node_id") or payload.get("id") or "").strip()
    )
    if not device_id:
        return JsonResponse({"error": "device_id required"}, status=400)

    # For ingest, if timestamp is missing we use "now" (device is online right now).
    ts = _parse_ts_any(payload.get("timestamp")) or dj_tz.now().astimezone(
        timezone.utc
    )

    # Minimal in-memory cache
    global _RECENT_CACHE
    try:
        _RECENT_CACHE
    except NameError:
        _RECENT_CACHE = {}

    def _fi(k, default=None):
        try:
            return float(payload.get(k))
        except Exception:
            return default

    def _ii(k, default=None):
        try:
            return int(payload.get(k))
        except Exception:
            return default

    entry = {
        "device_id": device_id,
        "label": (payload.get("label") or payload.get("person") or device_id),
        "lat": _fi("lat"),
        "lon": _fi("lon"),
        "hr": _ii("hr"),
        "spo2": _ii("spo2"),
        "temp_c": _fi("temp_c")
        if payload.get("temp_c") is not None
        else _fi("temp"),
        "bp_sys": _ii("bp_sys"),
        "bp_dia": _ii("bp_dia"),
        "ts": ts,
    }

    _RECENT_CACHE[device_id] = entry
    return JsonResponse({"ok": True})


# ---------------------- TEMP TEST POSTBOX ----------------------


_POSTBOX = deque(maxlen=50)


@csrf_exempt
def postbox_ingest(request):
    if request.method == "POST":
        try:
            payload = json.loads(request.body or "{}")
        except Exception:
            return HttpResponseBadRequest("invalid JSON")
        _POSTBOX.appendleft({"ts": dj_tz.now().isoformat(), "payload": payload})
        return JsonResponse({"ok": True, "count": len(_POSTBOX)})
    return JsonResponse({"items": list(_POSTBOX)})


# ---------------------- PROFILE & PASSWORD ---------------------


@login_required
def postbox_page(request):
    return render(request, "telemetry/postbox.html")


@login_required
def profile(request):
    return render(request, "registration/profile.html", {"user_obj": request.user})


@login_required
@require_http_methods(["GET", "POST"])
def password_change_request(request):
    if not request.user.email:
        messages.error(
            request,
            "No email address on your account. Please add one and try again.",
        )
        return redirect("profile")
    if request.method == "POST":
        form = PasswordResetForm({"email": request.user.email})
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure(),
                email_template_name="registration/password_reset_email.html",
                subject_template_name=(
                    "registration/password_reset_subject.txt"
                ),
            )
            return redirect("password_reset_done")
        messages.error(request, "Could not send email. Please try again.")
    return render(
        request,
        "registration/password_change_request.html",
        {"user_email": request.user.email},
    )


# ---------------------- DAILY TRACK HISTORY (LEGACY SIMPLE) ----------------------


@login_required
@require_GET
def api_track_history(request, device_id: str):
    """
    Legacy: Returns all GPS points of a device for a particular date
    using the HTTP API (VITALS_API_URL).
    URL: /api/track/<device_id>?date=YYYY-MM-DD
    """
    base_url = (getattr(settings, "VITALS_API_URL", "") or "").strip()
    secret = (getattr(settings, "VITALS_API_SECRET", "") or "").strip()
    timeout = int(getattr(settings, "VITALS_API_TIMEOUT", 10))

    if not base_url:
        return JsonResponse({"items": [], "note": "VITALS_API_URL not configured"})

    date_str = request.GET.get("date")
    if not date_str:
        return JsonResponse({"error": "date=YYYY-MM-DD required"}, status=400)

    headers = {"x-ingest-secret": secret} if secret else {}
    # use a SAFE limit that Lambda accepts
    params = {"device_id": device_id, "limit": "1000"}

    try:
        r = requests.get(base_url, params=params, headers=headers, timeout=timeout)
        if not r.ok:
            return JsonResponse(
                {
                    "items": [],
                    "note": f"upstream status {r.status_code}: {(r.text or '')[:120]}",
                }
            )
        raw = r.json().get("items") or []
    except Exception:
        log.exception("api_track_history upstream error")
        return JsonResponse({"items": []})

    out = []
    for it in raw:
        ts = _parse_ts_any(it.get("timestamp") or it.get("ts"))
        if not ts:
            continue
        if str(ts.date()) != date_str:
            continue

        lat = _to_float(it.get("lat"))
        lon = _to_float(it.get("lon"))
        if lat is None or lon is None:
            continue

        out.append(
            {
                "ts": ts.isoformat(),
                "lat": lat,
                "lon": lon,
                "hr": it.get("hr"),
                "spo2": it.get("spo2"),
                "temp": it.get("temp") or it.get("temp_c"),
            }
        )

    return JsonResponse({"items": out})


# ---------------------- DAILY TRACK – MAIN PAGE ----------------------


@login_required
def tracking_page(request):
    """
    Route tracking UI.

    - Builds device list from AWS /vitals (and /vitals/devices if configured),
      with local Device table as fallback.
    - Reads ?device_id= and ?date= from query string.
    - If both are present, calls /api/tracking to get trip segments.
    """

    devices: list[dict] = []
    seen: set[str] = set()

    devices_url = (getattr(settings, "VITALS_DEVICES_URL", "") or "").strip()
    base_url = (getattr(settings, "VITALS_API_URL", "") or "").strip()
    secret = (
        getattr(settings, "VITALS_API_SECRET", "")
        or getattr(settings, "VITALS_SECRET", "")
        or ""
    ).strip()
    timeout = int(getattr(settings, "VITALS_API_TIMEOUT", 10))
    headers = {"x-ingest-secret": secret} if secret else {}

    def _add_from_rows(rows):
        if not isinstance(rows, list):
            return
        for it in rows:
            if not isinstance(it, dict):
                continue
            dev_id = str(
                it.get("device_id")
                or it.get("node_id")
                or it.get("id")
                or ""
            ).strip()
            if not dev_id or dev_id in seen:
                continue
            label = str(
                it.get("label")
                or it.get("person")
                or dev_id
            ).strip()
            devices.append({"device_id": dev_id, "label": label})
            seen.add(dev_id)

    # A) Try /devices registry first (if configured) – use active_minutes like live map
    if devices_url:
        try:
            try:
                max_age = int(getattr(settings, "DEVICES_MAX_AGE_MIN", 1440))
            except (TypeError, ValueError):
                max_age = 1440

            r = requests.get(
                devices_url,
                params={"active_minutes": str(max_age)},
                headers=headers,
                timeout=timeout,
            )
            log.info("tracking_page devices GET %s -> %s", r.url, r.status_code)
            if r.ok and r.content:
                payload = r.json()
                rows = payload.get("items", payload)
                if isinstance(rows, dict):
                    rows = list(rows.values())
                _add_from_rows(rows)
        except requests.RequestException:
            log.exception("tracking_page: devices registry fetch failed")

    # B) Fallback: main VITALS_API_URL with no device_id (returns all latest)
    if not devices and base_url:
        try:
            r = requests.get(base_url, headers=headers, timeout=timeout)
            log.info("tracking_page base GET %s -> %s", r.url, r.status_code)
            if r.ok and r.content:
                payload = r.json()
                rows = payload.get("items", payload)
                if isinstance(rows, dict):
                    rows = list(rows.values())
                _add_from_rows(rows)
        except requests.RequestException:
            log.exception("tracking_page: base vitals fetch failed")

    # C) Final fallback: local Device table (TEST01 etc.)
    if not devices:
        try:
            org = getattr(getattr(request.user, "profile", None), "organization", None)
            qs = Device.objects.all()
            if org:
                qs = qs.filter(organization=org)
            qs = qs.order_by("label", "device_id")[:200]
            for d in qs:
                if d.device_id in seen:
                    continue
                devices.append(
                    {
                        "device_id": d.device_id,
                        "label": d.label or d.device_id,
                    }
                )
                seen.add(d.device_id)
        except Exception:
            log.exception("tracking_page: local Device fallback failed")

    devices.sort(key=lambda x: (x["label"].lower(), x["device_id"].lower()))

    # ---- Selected device + date from query ----
    selected_device_id = (request.GET.get("device_id") or "").strip()
    if not selected_device_id and devices:
        selected_device_id = devices[0]["device_id"]

    date_raw = (request.GET.get("date") or "").strip()

    selected_date_input = ""      # YYYY-MM-DD for <input type="date">
    selected_date_display = ""    # dd-mm-yyyy for summary text
    api_date_param = None         # what we send to /api/tracking

    if date_raw:
        dt = None
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(date_raw, fmt).date()
                break
            except ValueError:
                continue

        if dt:
            selected_date_input = dt.strftime("%Y-%m-%d")
            selected_date_display = dt.strftime("%d-%m-%Y")
            api_date_param = dt.strftime("%d-%m-%Y")  # dd-mm-yyyy to API
        else:
            api_date_param = date_raw

    # ---- Call /api/tracking if we have device + date ----
    trip_segments: list[dict] = []
    total_km = 0.0

    if selected_device_id and api_date_param:
        try:
            api_url = request.build_absolute_uri("/api/tracking")
            params = {
                "device_id": selected_device_id,
                "date": api_date_param,
            }
            r = requests.get(api_url, params=params, timeout=10)
            log.info("tracking_page: /api/tracking GET %s -> %s", r.url, r.status_code)

            if r.ok and r.content:
                payload = r.json()
                trip_segments = payload.get("trips") or payload.get("trip_segments") or []
                try:
                    total_km = float(payload.get("total_km", 0.0))
                except Exception:
                    total_km = 0.0
        except Exception:
            log.exception("tracking_page: failed to call /api/tracking")

    if not selected_date_display:
        selected_date_display = "No date selected"

    ctx = {
        "devices": devices,
        "selected_device_id": selected_device_id,
        # for older template versions:
        "selected_date": selected_date_input,
        # for newer template:
        "selected_date_input": selected_date_input,
        "selected_date_display": selected_date_display,
        "trip_segments": trip_segments,
        "trip_segments_json": json.dumps(trip_segments, cls=DjangoJSONEncoder),
        "total_km": f"{total_km:.1f}",
    }
    return render(request, "telemetry/tracking.html", ctx)


# ---------------------- DAILY TRACK – JSON API ----------------------


@login_required
@require_GET
def api_tracking(request):
    """
    JSON endpoint used by the /tracking page.

    - Requires ?device_id=
    - Requires ?date= (dd-mm-yyyy or yyyy-mm-dd)
    - Calls VITALS_API_URL, filters rows by that date, groups into trips.
    """
    device_id = (request.GET.get("device_id") or "").strip()
    date_raw = (request.GET.get("date") or "").strip()

    if not device_id:
        return JsonResponse({"error": "device_id required"}, status=400)
    if not date_raw:
        return JsonResponse({"error": "date required"}, status=400)

    # Parse date
    target_date: date | None = None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            target_date = datetime.strptime(date_raw, fmt).date()
            break
        except ValueError:
            continue

    if target_date is None:
        return JsonResponse({"error": "invalid date format"}, status=400)

    # Call VITALS_API_URL
    base_url = (getattr(settings, "VITALS_API_URL", "") or "").strip()
    secret = (
        getattr(settings, "VITALS_API_SECRET", "")
        or getattr(settings, "VITALS_SECRET", "")
        or ""
    ).strip()
    timeout = int(getattr(settings, "VITALS_API_TIMEOUT", 10))
    headers = {"x-ingest-secret": secret} if secret else {}

    rows = []
    if base_url:
        params = {"device_id": device_id, "limit": "1000"}
        try:
            r = requests.get(base_url, headers=headers, params=params, timeout=timeout)
            log.info("api_tracking: vitals GET %s -> %s", r.url, r.status_code)
            if r.ok and r.content:
                payload = r.json()
                rows = payload.get("items", payload)
                if isinstance(rows, dict):
                    rows = list(rows.values())
        except requests.RequestException:
            log.exception("api_tracking: vitals fetch failed")

    # Filter + normalize points
    points = []

    for it in rows or []:
        dev_id = str(
            it.get("device_id")
            or it.get("node_id")
            or it.get("id")
            or ""
        ).strip()
        if dev_id != device_id:
            continue

        ts = _sanitize_ts(_parse_ts_any(it.get("timestamp") or it.get("ts")))
        if not ts:
            continue
        if ts.date() != target_date:
            continue

        lat = _to_float(_pick(it, "lat", "last_lat", "latitude", "Latitude"))
        lon = _to_float(_pick(it, "lon", "last_lon", "longitude", "Longitude"))
        if lat is None or lon is None:
            gps = it.get("gps") or {}
            lat = _to_float(_pick(gps, "lat", "latitude", "Latitude"))
            lon = _to_float(_pick(gps, "lon", "longitude", "Longitude"))
        if lat is None or lon is None:
            continue

        points.append({"dt": ts, "lat": lat, "lon": lon})

    points.sort(key=lambda p: p["dt"])

    # Group into trips with time gap
    trips_raw: list[list[dict]] = []
    current: list[dict] = []
    last_time: datetime | None = None
    MAX_GAP_MIN = 20

    for p in points:
        if not current:
            current.append(p)
            last_time = p["dt"]
            continue

        gap_min = (p["dt"] - last_time).total_seconds() / 60.0
        if gap_min > MAX_GAP_MIN:
            trips_raw.append(current)
            current = [p]
        else:
            current.append(p)
        last_time = p["dt"]

    if current:
        trips_raw.append(current)

    # Build payload
    trips_payload = []
    total_km = 0.0
    trip_id = 1

    for seg in trips_raw:
        if len(seg) < 2:
            continue

        dist = 0.0
        pts = []

        for i, p in enumerate(seg):
            pts.append(
                {
                    "lat": p["lat"],
                    "lng": p["lon"],
                    "ts": p["dt"].strftime("%H:%M:%S"),
                }
            )
            if i > 0:
                prev = seg[i - 1]
                dist += _haversine_km(
                    prev["lat"], prev["lon"], p["lat"], p["lon"]
                )

        total_km += dist
        trips_payload.append(
            {
                "id": trip_id,
                "start_time": seg[0]["dt"].strftime("%H:%M"),
                "end_time": seg[-1]["dt"].strftime("%H:%M"),
                "distance_km": round(dist, 2),
                "points": pts,
            }
        )
        trip_id += 1

    # ✅ FIX: no json_dumps_params with 'cls' here
    return JsonResponse(
        {"trips": trips_payload, "total_km": round(total_km, 2)}
    )


# ---------------------- CSV DOWNLOAD FOR TRACK ----------------------


@login_required
@require_GET
def api_tracking_download(request):
    """
    CSV download for a device + date track.
    URL: /api/tracking/download/?device_id=X&date=YYYY-MM-DD
    """
    device_id = (request.GET.get("device_id") or "").strip()
    date_str = (request.GET.get("date") or "").strip()

    if not device_id or not date_str:
        return HttpResponseBadRequest(
            "device_id and date (YYYY-MM-DD) are required"
        )

    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return HttpResponseBadRequest(
            "invalid date format (expected YYYY-MM-DD)"
        )

    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        return HttpResponseBadRequest("device not found")

    day_start = dj_tz.make_aware(
        datetime.combine(selected_date, datetime.min.time())
    )
    day_end = day_start + timedelta(days=1)

    readings = list(
        Reading.objects.filter(
            device=device,
            ts__gte=day_start,
            ts__lt=day_end,
            lat__isnull=False,
            lon__isnull=False,
        ).order_by("ts")
    )

    trips = _build_trip_segments_from_readings(readings)

    buffer = StringIO()
    writer = csv.writer(buffer)

    writer.writerow(
        [
            "trip_id",
            "device_id",
            "date",
            "point_time",
            "lat",
            "lon",
            "segment_start_time",
            "segment_end_time",
            "segment_distance_km",
        ]
    )

    for seg in trips:
        seg_id = seg.get("id")
        seg_start = seg.get("start_time")
        seg_end = seg.get("end_time")
        dist = seg.get("distance_km", 0.0)
        for p in seg.get("points", []):
            writer.writerow(
                [
                    seg_id,
                    device_id,
                    date_str,
                    p.get("time"),
                    p.get("lat"),
                    p.get("lng"),
                    seg_start,
                    seg_end,
                    dist,
                ]
            )

    csv_data = buffer.getvalue()
    buffer.close()

    filename = f"track_{device_id}_{date_str}.csv"
    resp = HttpResponse(csv_data, content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ---------------------- ACCOUNT (MY ACCOUNT) ----------------------


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    user = request.user

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip()
        password = (request.POST.get("password") or "").strip()
        confirm_password = (request.POST.get("confirm_password") or "").strip()

        ctx = {"username": username or user.username, "email": email or user.email}

        if not username or not email:
            ctx["error"] = "Username and email are required."
            return render(request, "registration/account.html", ctx)

        if password and password != confirm_password:
            ctx["error"] = "Passwords do not match."
            return render(request, "registration/account.html", ctx)

        if User.objects.filter(username=username).exclude(pk=user.pk).exists():
            ctx["error"] = "This username is already taken."
            return render(request, "registration/account.html", ctx)

        if User.objects.filter(email=email).exclude(pk=user.pk).exists():
            ctx["error"] = "This email is already used."
            return render(request, "registration/account.html", ctx)

        user.username = username
        user.email = email
        if password:
            user.set_password(password)
        user.save()

        if password:
            update_session_auth_hash(request, user)

        messages.success(request, "Account updated successfully.")
        return redirect("dashboard")

    ctx = {
        "username": user.username,
        "email": user.email,
    }
    return render(request, "registration/account.html", ctx)
