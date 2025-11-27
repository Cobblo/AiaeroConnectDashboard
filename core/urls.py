from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from telemetry import views

urlpatterns = [
    # ------------------ Admin ------------------
    path("admin/", admin.site.urls),

    # ------------------ Authentication ------------------
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/account/", views.account, name="account"),
    path("accounts/profile/", views.profile, name="profile"),
    path(
        "accounts/password/request/",
        views.password_change_request,
        name="password_change_request",
    ),
    path("accounts/", include("django.contrib.auth.urls")),

    # ------------------ Main UI Pages ------------------
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("person/", views.person_auto, name="person_auto"),
    path("person/<slug:pid>/", views.person_page, name="person_page"),

    # ---- Route tracking page (THIS is the name used in template) ----
    path("tracking/", views.tracking_page, name="tracking_page"),

    # ------------------ Live Cloud Proxies ------------------
    path("api/devices/", views.api_devices, name="api_devices"),
    path("api/readings/", views.api_readings, name="api_readings"),
    path("api/current/recent/", views.api_current_recent, name="api_current_recent"),
    path("api/current/", views.api_current_all, name="api_current_all"),

    # ------------------ Local Ingest (Testing Only) ------------------
    path("ingest/v1/", views.ingest_vitals, name="ingest_vitals"),

    # ------------------ Tracking APIs ------------------
    path("api/tracking/", views.api_tracking, name="api_tracking"),
    path("api/track/<slug:device_id>/", views.api_track_history, name="api_track_history"),
    path(
        "api/tracking/download/",
        views.api_tracking_download,
        name="api_tracking_download",
    ),

    # ------------------ Mock / Demo APIs ------------------
    path("api/mock/people/", views.api_mock_people, name="api_mock_people"),
    path(
        "api/mock/person/<slug:pid>/",
        views.api_mock_person,
        name="api_mock_person",
    ),

    # ------------------ Debug Tools ------------------
    path("debug/postbox/", views.postbox_page, name="postbox_page"),
    path("debug/postbox/data/", views.postbox_ingest, name="postbox_ingest"),

    # ------------------ Downloads ------------------
    path(
        "download/latest.xlsx",
        views.download_latest_workbook,
        name="download_latest_workbook",
    ),
]

# ------------------ Static & Media (Development Only) ------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
