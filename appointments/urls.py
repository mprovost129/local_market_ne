from django.urls import path

from . import views

app_name = "appointments"

urlpatterns = [
    path("request/<int:product_id>/", views.request_appointment, name="request"),
    path("api/slots/<int:product_id>/", views.available_slots_api, name="slots_api"),
    path("my/", views.buyer_requests, name="buyer_requests"),
    path("my/<int:req_id>/cancel/", views.buyer_cancel_request, name="buyer_cancel"),
    path("my/<int:req_id>/confirm/", views.buyer_confirm, name="buyer_confirm"),
    path("seller/", views.seller_requests, name="seller_requests"),
    path("seller/availability/", views.seller_availability, name="seller_availability"),
    path("seller/<int:req_id>/<str:action>/", views.seller_request_update, name="seller_update"),
    path("seller/<int:req_id>/reschedule/", views.seller_reschedule, name="seller_reschedule"),
    path("seller/<int:req_id>/complete/", views.seller_mark_completed, name="seller_complete"),
    path("seller/<int:req_id>/cancel/", views.seller_cancel, name="seller_cancel"),
    path("my/<int:req_id>/calendar.ics", views.appointment_ics, name="ics"),
]