# orders/urls.py
from __future__ import annotations

from django.urls import include, path

from . import views
from . import webhooks

app_name = "orders"

urlpatterns = [
    # Buyer checkout flow
    path("place/", views.place_order, name="place"),
    path("<uuid:order_id>/", views.order_detail, name="detail"),
    path("<uuid:order_id>/offplatform/sent/", views.buyer_mark_offplatform_sent, name="buyer_mark_offplatform_sent"),
    path("<uuid:order_id>/items/<uuid:item_id>/confirm-delivered/", views.mark_item_delivered_buyer, name="mark_item_delivered_buyer"),
    path("<uuid:order_id>/set-fulfillment/", views.order_set_fulfillment, name="set_fulfillment"),
    path("<uuid:order_id>/update-tips/", views.order_update_tips, name="update_tips"),
    path("<uuid:order_id>/checkout/start/", views.checkout_start, name="checkout_start"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("<uuid:order_id>/checkout/paypal/return/", views.paypal_return, name="paypal_return"),
    path("<uuid:order_id>/checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),

    # Buyer order history
    path("mine/", views.my_orders, name="my_orders"),

    # Seller fulfillment
    path("seller/orders/", views.seller_orders_list, name="seller_orders_list"),
    path("seller/payments/", views.seller_payments_queue, name="seller_payments_queue"),
    path("seller/orders/<uuid:order_id>/", views.seller_order_detail, name="seller_order_detail"),
    path("seller/orders/<uuid:order_id>/items/<uuid:item_id>/mark-shipped/", views.mark_item_shipped, name="mark_item_shipped"),
    path("seller/orders/<uuid:order_id>/items/<uuid:item_id>/mark-delivered/", views.mark_item_delivered, name="mark_item_delivered"),
    path("seller/orders/<uuid:order_id>/items/<uuid:item_id>/set-status/", views.seller_set_item_status, name="seller_set_item_status"),
    path("seller/orders/<uuid:order_id>/confirm-payment/", views.seller_confirm_payment, name="seller_confirm_payment"),
    path("seller/orders/<uuid:order_id>/note/", views.seller_update_order_note, name="seller_update_order_note"),

    # Refunds (mounted under Orders)
    path("refunds/", include(("refunds.urls", "refunds"), namespace="refunds")),

    # Stripe webhook endpoint
    path("webhooks/stripe/", webhooks.stripe_webhook, name="stripe_webhook"),
    path("webhooks/paypal/", webhooks.paypal_webhook, name="paypal_webhook"),
]
