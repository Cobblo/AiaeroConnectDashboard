from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

import pandas as pd

from telemetry.models import CurrentVital


def _snapshot_to_excel():
    """
    Read all CurrentVital rows (one per device), append them into today's Excel.
    Returns (filepath, added_count)
    """
    now = timezone.now()
    local_now = timezone.localtime(now)
    out_dir = Path(getattr(settings, "EXCEL_EXPORT_DIR", settings.BASE_DIR / "excel_exports"))
    out_dir.mkdir(parents=True, exist_ok=True)

    excel_path = out_dir / f"vitals_{local_now:%Y-%m-%d}.xlsx"

    # Build new rows from CurrentVital (latest snapshot per device/person)
    rows = []
    cvs = CurrentVital.objects.select_related("device", "person", "device__organization")
    for cv in cvs:
        ts_local = timezone.localtime(cv.ts)
        rows.append({
            "date": ts_local.date().isoformat(),
            "time": ts_local.strftime("%H:%M:%S"),
            "ts_local": ts_local,  # keep a proper datetime for dedupe
            "organization": cv.device.organization.name if cv.device and cv.device.organization_id else "",
            "person": cv.person.name if cv.person_id else "",
            "device_id": cv.device.device_id if cv.device_id else "",
            "heart_rate": cv.heart_rate,
            "spo2": cv.spo2,
            "temp_c": cv.temp_c,
            "bp_sys": cv.bp_sys,
            "bp_dia": cv.bp_dia,
            "battery_pct": cv.battery_pct,
            "rssi": cv.rssi,
            "lat": cv.lat,
            "lon": cv.lon,
        })

    df_new = pd.DataFrame(rows)

    # If nothing to write, still keep/return path
    if df_new.empty:
        if not excel_path.exists():
            # write an empty-but-friendly sheet the first time
            with pd.ExcelWriter(excel_path, engine="openpyxl") as w:
                df_new.to_excel(w, index=False, sheet_name="vitals")
        return str(excel_path), 0

    # Merge with existing (to avoid duplicates of same device/timestamp)
    if excel_path.exists():
        try:
            df_old = pd.read_excel(excel_path)
        except Exception:
            df_old = pd.DataFrame()
        df_all = pd.concat([df_old, df_new], ignore_index=True)
        # dedupe on (device_id, ts_local)
        if "device_id" in df_all.columns and "ts_local" in df_all.columns:
            df_all.drop_duplicates(subset=["device_id", "ts_local"], inplace=True, keep="last")
    else:
        df_all = df_new

    # Write atomically
    tmp = excel_path.with_suffix(".tmp.xlsx")
    with pd.ExcelWriter(tmp, engine="openpyxl", mode="w") as w:
        df_all.to_excel(w, index=False, sheet_name="vitals")
    tmp.replace(excel_path)

    # How many *new* rows got added this time?
    added = len(df_new)
    return str(excel_path), added


class Command(BaseCommand):
    help = "Append latest vitals of all devices to today's Excel file (runs safely multiple times)."

    def handle(self, *args, **options):
        path, added = _snapshot_to_excel()
        self.stdout.write(self.style.SUCCESS(f"Excel updated: {path}  (+{added} rows)"))
