from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Organization(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username} ({self.organization})"


class Device(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=128, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    battery_pct = models.FloatField(null=True, blank=True)
    rssi = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.label or self.device_id


class Person(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="people")
    name = models.CharField(max_length=128)
    tag = models.CharField(max_length=64, blank=True)
    device = models.OneToOneField(Device, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.organization})"


class Reading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="readings")
    ts = models.DateTimeField(auto_now_add=True)

    heart_rate = models.IntegerField(null=True, blank=True)
    bp_sys = models.IntegerField(null=True, blank=True)
    bp_dia = models.IntegerField(null=True, blank=True)
    spo2 = models.FloatField(null=True, blank=True)
    temp_c = models.FloatField(null=True, blank=True)

    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

    battery_pct = models.FloatField(null=True, blank=True)
    rssi = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["device", "-ts"])]

    def __str__(self):
        return f"{self.device.device_id} @ {self.ts:%Y-%m-%d %H:%M:%S}"


class CurrentVital(models.Model):
    """
    Single-row snapshot of the *latest* values per device for fast reads.
    Auto-updated by a signal when new Reading rows arrive.
    """
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name="current")
    person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name="current_vitals")

    ts = models.DateTimeField()  # timestamp of the latest reading

    heart_rate = models.IntegerField(null=True, blank=True)
    bp_sys = models.IntegerField(null=True, blank=True)
    bp_dia = models.IntegerField(null=True, blank=True)
    spo2 = models.FloatField(null=True, blank=True)
    temp_c = models.FloatField(null=True, blank=True)

    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)

    battery_pct = models.FloatField(null=True, blank=True)
    rssi = models.IntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["-updated_at"]),
            models.Index(fields=["ts"]),
        ]

    def __str__(self):
        return f"Current {self.device.device_id} @ {self.ts:%H:%M:%S}"


# --- Keep CurrentVital fresh whenever a Reading is saved ---
@receiver(post_save, sender=Reading)
def update_current_vital(sender, instance: Reading, created, **kwargs):
    dev = instance.device
    # link the person if you have Person.device set
    person = getattr(dev, "person", None)

    try:
        cv = CurrentVital.objects.get(device=dev)
        # only replace if this reading is newer
        if instance.ts <= cv.ts:
            return
    except CurrentVital.DoesNotExist:
        cv = CurrentVital(device=dev)

    cv.person = person
    cv.ts = instance.ts
    cv.heart_rate = instance.heart_rate
    cv.bp_sys = instance.bp_sys
    cv.bp_dia = instance.bp_dia
    cv.spo2 = instance.spo2
    cv.temp_c = instance.temp_c
    cv.lat = instance.lat
    cv.lon = instance.lon
    cv.battery_pct = instance.battery_pct
    cv.rssi = instance.rssi
    cv.save()
