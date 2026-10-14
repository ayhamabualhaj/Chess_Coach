"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("games/", include("apps.games.urls")),
    path("coaching/", include("apps.coaching.urls")),
    # JSON API (Django REST Framework). Log in with a token from /api/token/ or the session.
    path("api/token/", obtain_auth_token, name="api_token"),
    path("api/", include("apps.games.api_urls")),
    path("api/", include("apps.coaching.api_urls")),
    # The home page sends users to their games list for now.
    path("", RedirectView.as_view(url="/games/", permanent=False)),
]