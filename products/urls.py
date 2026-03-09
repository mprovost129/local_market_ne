# products/urls.py
from django.urls import path

from . import views
from . import views_seller

app_name = "products"

urlpatterns = [
    # Public browsing
    path("", views.product_list, name="list"),
    path("services/", views.services_list, name="services"),

    path("top-sellers/", views.top_sellers, name="top_sellers"),
    path("shop/<int:seller_id>/", views.seller_shop, name="seller_shop"),
    path("saved-searches/", views.saved_search_list, name="saved_search_list"),
    path("saved-searches/create/", views.saved_search_create, name="saved_search_create"),
    path("saved-searches/<int:pk>/update/", views.saved_search_update, name="saved_search_update"),
    path("saved-searches/<int:pk>/delete/", views.saved_search_delete, name="saved_search_delete"),

    # Engagement redirect (logs CLICK then redirects to detail)
    path("go/<int:pk>/<slug:slug>/", views.product_go, name="go"),

    # Canonical detail
    path("<int:pk>/<slug:slug>/", views.product_detail, name="detail"),

    # Seller area
    path("seller/", views_seller.seller_product_list, name="seller_list"),
    path("seller/new/", views_seller.seller_product_create, name="seller_create"),
    path("seller/<int:pk>/edit/", views_seller.seller_product_edit, name="seller_edit"),
    path("seller/<int:pk>/images/", views_seller.seller_product_images, name="seller_images"),
    path("seller/<int:pk>/images/<uuid:image_id>/delete/", views_seller.seller_product_image_delete, name="seller_image_delete"),
    path("seller/<int:pk>/toggle-active/", views_seller.seller_product_toggle_active, name="seller_toggle_active"),
    path("seller/<int:pk>/delete/", views_seller.seller_product_delete, name="seller_delete"),

    # Dependent dropdown endpoint (Category -> Subcategory)
    path("seller/subcategories/", views_seller.seller_subcategories_for_category, name="seller_subcategories_for_category"),
]
