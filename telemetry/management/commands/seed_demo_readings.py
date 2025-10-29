# telemetry/management/commands/seed_demo_readings.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from telemetry.models import Organization, Device, Person, Reading
import random

class Command(BaseCommand):
    help = "Insert demo devices/people and a short time-series of vitals."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=24,
                            help="How many points per device (5-min spacing).")

    def handle(self, *args, **opts):
        org, _ = Organization.objects.get_or_create(name="Demo Org")

        # Ensure 10 devices and matching people exist + are linked
        devices = []
        for i in range(1, 11):
            dev, _ = Device.objects.get_or_create(
                organization=org,
                device_id=f"NODE_{i:02d}",
                defaults={"label": f"Soldier {i}"}
            )
            person, _ = Person.objects.get_or_create(
                organization=org,
                name=f"Soldier {i}",
                defaults={"device": dev},
            )
            if person.device_id != dev.id:
                person.device = dev
                person.save()
            devices.append(dev)

        # Insert time-series
        per = int(opts["count"])
        now = timezone.now()

        for dev in devices:
            for k in range(per):
                ts = now - timezone.timedelta(minutes=5 * (per - k))
                Reading.objects.create(
                    device=dev,
                    ts=ts,
                    heart_rate=78 + (k % 12),
                    spo2=96 - (k % 4),
                    temp_c=36.5 + (k % 5) * 0.1,
                    bp_sys=112 + (k % 10),
                    bp_dia=74 + (k % 7),
                    lat=28.6139 + random.uniform(-0.005, 0.005),  # Delhi-ish
                    lon=77.2090 + random.uniform(-0.005, 0.005),
                    battery_pct=100 - (k % 30),
                    rssi=-90 + (k % 12),
                )

        self.stdout.write(self.style.SUCCESS("Inserted demo readings."))
