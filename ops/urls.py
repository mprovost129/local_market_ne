from __future__ import annotations

from django.urls import path

from . import views

app_name = "ops"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("funnel/", views.funnel_dashboard, name="funnel_dashboard"),
    path("emails/failed/", views.failed_emails, name="failed_emails"),
    path("emails/failed/<int:pk>/", views.failed_email_detail, name="failed_email_detail"),
    path("emails/failed/<int:pk>/resend/", views.failed_email_resend, name="failed_email_resend"),
    path("health/", views.ops_health, name="ops_health"),
    path("alerts/summary/", views.alerts_summary, name="alerts_summary"),
    path("launch-check/", views.launch_check, name="launch_check"),
    path("runbook/", views.runbook, name="runbook"),
    path("runbook/run-reconciliation-check/", views.runbook_run_reconciliation_check, name="runbook_run_reconciliation_check"),
    path("runbook/run-alert-summary/", views.runbook_run_alert_summary, name="runbook_run_alert_summary"),
    path("runbook/run-launch-gate/", views.runbook_run_launch_gate, name="runbook_run_launch_gate"),
    path("audit/", views.audit_log, name="audit_log"),

    path("errors/", views.error_events, name="error_events"),
    path("errors/<int:pk>/", views.error_event_detail, name="error_event_detail"),
    path("errors/<int:pk>/resolve/", views.error_event_resolve, name="error_event_resolve"),

    path("orders/", views.orders_list, name="orders_list"),
    path("orders/<uuid:pk>/", views.order_detail, name="order_detail"),
    path("orders/<uuid:pk>/retry-transfers/", views.order_retry_transfers, name="order_retry_transfers"),

    path("reconciliation/", views.reconciliation_list, name="reconciliation_list"),
    path("reconciliation/mismatches/", views.reconciliation_mismatches, name="reconciliation_mismatches"),

    path("webhooks/", views.webhooks_list, name="webhooks_list"),
    path("webhooks/reprocess-filtered/", views.webhooks_reprocess_filtered, name="webhooks_reprocess_filtered"),
    path("webhooks/<int:pk>/", views.webhook_detail, name="webhook_detail"),
    path("webhooks/<int:pk>/reprocess/", views.webhook_reprocess, name="webhook_reprocess"),


    path("sellers/", views.sellers_list, name="sellers_list"),
    path("sellers/<int:pk>/", views.seller_detail, name="seller_detail"),
    path("companies/", views.sellers_list, name="companies_list"),
    path("companies/<int:pk>/", views.seller_detail, name="company_detail"),
    path("consumers/", views.consumers_list, name="consumers_list"),
    path("consumers/<int:pk>/", views.consumer_detail, name="consumer_detail"),

    path("moderation/qa-reports/", views.qa_reports_queue, name="qa_reports_queue"),
    path("moderation/qa-reports/<int:pk>/resolve/", views.qa_report_resolve, name="qa_report_resolve"),

    path("refunds/requests/", views.refund_requests_queue, name="refund_requests_queue"),
]
