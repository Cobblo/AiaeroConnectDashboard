# core/urls.py
from django.contrib import admin
from django.urls import path, include
from telemetry import views

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth (login/logout + built-ins for password change/reset)
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/profile/", views.profile, name="profile"),

    # Request-by-email password change (asks for confirmation and emails link)
    path("accounts/password/request/", views.password_change_request, name="password_change_request"),

    # Root router
    path("", views.home, name="home"),

    # App pages
    path("dashboard/", views.dashboard, name="dashboard"),
    path("person/<slug:pid>/", views.person_page, name="person_page"),

    # APIs and tools (unchanged)
    path("api/current/", views.api_current_all, name="api_current_all"),
    path("api/mock/people/", views.api_mock_people, name="api_mock_people"),
    path("api/mock/person/<slug:pid>/", views.api_mock_person, name="api_mock_person"),
    path("debug/postbox/", views.postbox_page, name="postbox_page"),
    path("debug/postbox/data/", views.postbox_ingest, name="postbox_ingest"),
    path("download/latest.xlsx", views.download_latest_workbook, name="download_latest_workbook"),
]
