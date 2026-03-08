# core/urls.py

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("version/", views.version, name="version"),
    path("", views.home, name="home"),
    path("coming-soon/", views.coming_soon, name="coming_soon"),
    path("waitlist/", views.waitlist_signup, name="waitlist"),

    # Reference pages (static v1)
    # Canonical routes are short and user-friendly.
    path("about/", views.about_page, name="about"),
    path("help/", views.help_page, name="help"),
    path("faqs/", views.faqs_page, name="faqs"),
    path("tips/", views.tips_page, name="tips"),
    path("contact/", views.contact_page, name="contact"),

    # Legacy routes (kept for backward compatibility)
    path("references/about/", views.reference_redirect, {"to": "core:about"}),
    path("references/help/", views.reference_redirect, {"to": "core:help"}),
    path("references/faqs/", views.reference_redirect, {"to": "core:faqs"}),
    path("references/tips/", views.reference_redirect, {"to": "core:tips"}),
]