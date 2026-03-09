from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from payments.services_fee_waiver import ensure_fee_waiver_for_new_seller
from products.models import Product


@receiver(pre_save, sender=Product)
def _capture_previous_active_state(sender, instance: Product, **kwargs):
    """
    Cache prior activation state so post_save can detect false->true transitions.
    """
    if not instance.pk:
        instance._was_active = False
        return
    prev = Product.objects.filter(pk=instance.pk).values_list("is_active", flat=True).first()
    instance._was_active = bool(prev)


@receiver(post_save, sender=Product)
def _start_fee_waiver_on_first_live_listing(sender, instance: Product, created: bool, **kwargs):
    """
    Start seller fee waiver when the seller gets their first live listing.
    """
    was_active = bool(getattr(instance, "_was_active", False))
    is_now_active = bool(instance.is_active)
    became_active = bool(created and is_now_active) or (not created and not was_active and is_now_active)
    if not became_active:
        return

    ensure_fee_waiver_for_new_seller(seller_user=instance.seller)
