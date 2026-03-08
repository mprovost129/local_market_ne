# legal/urls.py
from __future__ import annotations

from django.urls import path

from . import views

app_name = "legal"

urlpatterns = [
    path("", views.legal_index, name="index"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("refund/", views.refund_policy, name="refund"),
    path("content/", views.content_policy, name="content"),
    path("seller-agreement/", views.seller_agreement, name="seller_agreement"),
    path("seller-fees/", views.seller_fees, name="seller_fees"),
    path("fulfillment-policy/", views.fulfillment_policy, name="fulfillment_policy"),
    path("services-policy/", views.services_policy, name="services_policy"),
]
