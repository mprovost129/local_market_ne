from __future__ import annotations

from django.urls import path

from . import views

app_name = "staff_console"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("orders/", views.orders_list, name="orders_list"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("support/", views.contact_messages_list, name="contact_messages_list"),
    path("support/<int:message_id>/", views.contact_message_detail, name="contact_message_detail"),
    path("support/<int:message_id>/update/", views.contact_message_update, name="contact_message_update"),
    path("support/<int:message_id>/reply/", views.contact_message_reply, name="contact_message_reply"),
    path("support/<int:message_id>/toggle/", views.contact_message_toggle_resolved, name="contact_message_toggle_resolved"),
    path("refunds/queue/", views.refund_requests_queue, name="refund_requests_queue"),
    path("qa/reports/", views.qa_reports_queue, name="qa_reports_queue"),
    path("qa/reports/<int:report_id>/resolve/", views.resolve_qa_report, name="resolve_qa_report"),
    path("listings/", views.listings_list, name="listings_list"),
    path("listings/<int:product_id>/edit/", views.listing_edit, name="listing_edit"),
]
