import json
from datetime import datetime, date, time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from telemetry.models import Organization, Device, Person, Reading

def _combine_today(hhmm_or_label: str) -> datetime:
    """
    Convert labels like '10:05' into a datetime today.
    If label is already ISO-like, try parsing it directly.
    """
    today = date.today()
    txt = str(hhmm_or_label).strip()
    # try HH:MM
    try:
        hh, mm = txt.split(":")[:2]
        return datetime.combine(today, time(int(hh), int(mm)))
    except Exception:
        pass
    # try ISO datetime
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(txt, fmt)
        except Exception:
            continue
    # fallback: now
    return datetime.now()

class Command(BaseCommand):
    help = "Import people.json (mock) into Organization/Device/Person/Reading tables."

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str, help="Path to people.json")
        parser.add_argument("--org", type=str, default="Default",
                            help="Organization name to import into (default: Default)")
        parser.add_argument("--wipe", action="store_true",
                            help="Delete existing Devices/People/Readings for this org before import")

    @transaction.atomic
    def handle(self, *args, **opts):
        json_path = Path(opts["json_path"])
        if not json_path.exists():
            raise CommandError(f"JSON not found: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        org_name = opts["org"].strip()
        org, _ = Organization.objects.get_or_create(name=org_name)

        if opts["wipe"]:
            # Remove existing org data (in right order)
            self.stdout.write(self.style.WARNING(f"Wiping existing data for org '{org_name}'…"))
            Reading.objects.filter(device__organization=org).delete()
            Person.objects.filter(organization=org).update(device=None)
            Device.objects.filter(organization=org).delete()
            Person.objects.filter(organization=org).delete()

        people = payload.get("people", [])
        if not people:
            raise CommandError("JSON has no 'people' array")

        created_devices = 0
        created_people = 0
        created_readings = 0

        for p in people:
            name = p.get("name", "Unknown")
            device_id = p.get("device_id")
            if not device_id:
                self.stdout.write(self.style.WARNING(f"Skipping {name}: missing device_id"))
                continue

            # Upsert Device
            device, _dev_created = Device.objects.get_or_create(
                organization=org,
                device_id=device_id,
                defaults={"label": name},
            )
            if _dev_created:
                created_devices += 1

            # Upsert Person
            person, _p_created = Person.objects.get_or_create(
                organization=org,
                name=name,
                defaults={"tag": p.get("tag", "")}
            )
            if _p_created:
                created_people += 1

            # Link person to device if not already linked
            if person.device_id != device.id:
                person.device = device
                person.save(update_fields=["device"])

            series = p.get("series", {})
            labels = series.get("ts", [])
            hr = series.get("hr", [])
            spo2 = series.get("spo2", [])
            temp = series.get("temp", [])
            bp_sys = series.get("bp_sys", [])
            bp_dia = series.get("bp_dia", [])
            path = p.get("path", [])
            latest = p.get("latest", {})

            # We’ll import N readings where N = len(labels)
            N = len(labels)
            for i in range(N):
                ts = _combine_today(labels[i])

                r = Reading(
                    device=device,
                    ts=ts,
                    heart_rate=hr[i] if i < len(hr) else None,
                    spo2=spo2[i] if i < len(spo2) else None,
                    temp_c=temp[i] if i < len(temp) else None,
                    bp_sys=bp_sys[i] if i < len(bp_sys) else None,
                    bp_dia=bp_dia[i] if i < len(bp_dia) else None,
                    battery_pct=latest.get("battery"),
                    rssi=latest.get("rssi"),
                )

                # attach a coordinate if we have a path item at same index
                if i < len(path):
                    r.lat = path[i].get("lat")
                    r.lon = path[i].get("lon")

                r.save()
                created_readings += 1

            # If there were path points beyond series length, insert location-only rows
            if len(path) > N:
                for j in range(N, len(path)):
                    ts = _combine_today(path[j].get("ts", datetime.now().strftime("%H:%M")))
                    Reading.objects.create(
                        device=device, ts=ts,
                        lat=path[j].get("lat"), lon=path[j].get("lon"),
                        battery_pct=latest.get("battery"),
                        rssi=latest.get("rssi"),
                    )
                    created_readings += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported into org '{org_name}': devices={created_devices}, people={created_people}, readings={created_readings}"
        ))
