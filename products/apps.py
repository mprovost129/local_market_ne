# products/apps.py
from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "products"

    def ready(self) -> None:
        # Register product lifecycle signals.
        from . import signals  # noqa: F401
