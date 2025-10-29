from django.contrib import admin
from .models import Organization, UserProfile, Device, Person, Reading, CurrentVital

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "organization")
    search_fields = ("user__username", "organization__name")
    autocomplete_fields = ("user", "organization")

class ReadingInline(admin.TabularInline):
    model = Reading
    extra = 0
    fields = ("ts", "heart_rate", "spo2", "temp_c", "bp_sys", "bp_dia", "battery_pct", "rssi", "lat", "lon")
    readonly_fields = ("ts",)
    ordering = ("-ts",)
    show_change_link = True

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "label", "organization", "is_active", "last_seen", "battery_pct", "rssi")
    list_filter = ("organization", "is_active")
    search_fields = ("device_id", "label", "organization__name")
    ordering = ("organization", "device_id")
    inlines = [ReadingInline]
    autocomplete_fields = ("organization",)

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "device", "tag")
    list_filter = ("organization",)
    search_fields = ("name", "tag", "device__device_id", "organization__name")
    autocomplete_fields = ("organization", "device")

@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    date_hierarchy = "ts"
    list_display = ("ts", "device", "heart_rate", "spo2", "temp_c", "bp_sys", "bp_dia", "battery_pct", "rssi", "lat", "lon")
    list_filter = ("device__organization", "device",)
    search_fields = ("device__device_id", "device__label")
    ordering = ("-ts",)
    autocomplete_fields = ("device",)

@admin.register(CurrentVital)
class CurrentVitalAdmin(admin.ModelAdmin):
    list_display = ("device", "person_name", "ts", "heart_rate", "spo2", "temp_c", "bp_sys", "bp_dia", "battery_pct", "rssi")
    list_filter = ("device__organization", "device",)
    search_fields = ("device__device_id", "device__label", "person__name")
    ordering = ("-ts",)
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("device", "person")

    def person_name(self, obj):
        return getattr(obj.person, "name", None)
    person_name.short_description = "Person"
