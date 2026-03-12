# products/views_seller.py
from __future__ import annotations

from typing import List

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse

from catalog.models import Category
from core.throttle import throttle
from core.throttle_rules import SELLER_MUTATE, CATEGORY_LOOKUP

from payments.models import SellerStripeAccount
from payments.decorators import stripe_ready_required

from .forms import ProductForm, ProductImageUploadForm, ProductImageBulkUploadForm, ProductImageForm
from .models import Product, ProductImage
from .permissions import seller_required, is_owner_user


SELLER_PRODUCT_MUTATE_RULE = SELLER_MUTATE
SELLER_UPLOAD_RULE = SELLER_MUTATE
SELLER_DELETE_RULE = SELLER_MUTATE
SELLER_CATEGORY_AJAX_RULE = CATEGORY_LOOKUP


def _can_edit_product(user, product: Product) -> bool:
    if is_owner_user(user):
        return True
    return product.seller == user


def _get_owned_product_or_404(request, pk: int) -> Product:
    product = get_object_or_404(Product, pk=pk)
    if not _can_edit_product(request.user, product):
        raise Http404("Not found")
    return product


def _publish_checklist(product: Product) -> tuple[bool, list[str]]:
    missing: list[str] = []

    if not (product.title or "").strip():
        missing.append("Title")
    if not product.category:
        missing.append("Category")
    if not (product.short_description or "").strip():
        missing.append("Short description")
    if not (product.description or "").strip():
        missing.append("Description")

    if not product.images.exists():
        missing.append("At least 1 image")
    else:
        if not product.images.filter(is_primary=True).exists():
            missing.append("Primary image")

    if not product.is_free:
        try:
            if product.price is None or product.price <= 0:
                missing.append("Price > 0 (or mark Free)")
        except Exception:
            missing.append("Valid price (or mark Free)")

    if product.kind == Product.Kind.SERVICE:
        if not product.service_duration_minutes:
            missing.append("Service duration (minutes)")

    return (len(missing) == 0), missing


def _field_step_for_listing_form(field_name: str) -> int:
    name = (field_name or "").strip().lower()
    if not name:
        return 1
    if name in {"kind"}:
        return 1
    if name in {"category", "subcategory"}:
        return 2
    if name in {"title", "short_description", "description", "slug", "price", "is_free"}:
        return 3
    return 4


def _form_error_step(form: ProductForm) -> int:
    # Use first field error in form field order so wizard opens where correction is needed.
    for field_name in form.fields.keys():
        if field_name in form.errors:
            return _field_step_for_listing_form(field_name)
    if form.non_field_errors():
        return 4
    return 1


def _first_error_field_name(form: ProductForm) -> str:
    for field_name in form.fields.keys():
        if field_name in form.errors:
            return field_name
    return ""


def _requested_step(request, *, default: int = 1) -> int:
    raw = (request.POST.get("current_step") or request.GET.get("step") or "").strip()
    try:
        step = int(raw)
    except Exception:
        step = int(default)
    return max(1, min(4, step))


@seller_required
def seller_product_list(request):
    qs = (
        Product.objects.select_related("category", "subcategory")
        .prefetch_related("images")
        .order_by("-created_at")
    )

    if not is_owner_user(request.user):
        qs = qs.filter(seller=request.user)

    products = list(qs)
    product_data = []
    for p in products:
        ok, missing = _publish_checklist(p)
        product_data.append({
            "product": p,
            "publish_ok": ok,
            "publish_missing": missing,
        })

    # Determine if the seller has a connected Stripe account
    stripe_ready = SellerStripeAccount.objects.filter(
        user=request.user,
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True
    ).exists()

    # Onboarding checklist (mirrors seller dashboard)
    profile = getattr(request.user, "profile", None)
    has_public_location = bool((getattr(profile, "zip_code", "") or "").strip())
    has_shop_name = bool((getattr(profile, "shop_name", "") or "").strip())
    email_verified = bool(getattr(profile, "email_verified", False))
    age_ok = bool(getattr(profile, "is_age_18_confirmed", False))
    policy_ack = bool(getattr(profile, "seller_prohibited_items_ack", False))
    has_listing = len(products) > 0

    onboarding_steps = [
        {"key": "email", "label": "Verify your email", "done": email_verified, "url": reverse("accounts:verify_email_status")},
        {"key": "age", "label": "Confirm you're 18+", "done": age_ok, "url": reverse("accounts:profile")},
        {"key": "policy", "label": "Acknowledge prohibited items policy", "done": policy_ack, "url": reverse("accounts:profile")},
        {"key": "stripe", "label": "Connect Stripe payouts", "done": bool(stripe_ready), "url": reverse("payments:connect_status")},
        {"key": "shop", "label": "Add your shop name", "done": has_shop_name, "url": reverse("accounts:profile")},
        {"key": "location", "label": "Set your ZIP code", "done": has_public_location, "url": reverse("accounts:profile")},
        {"key": "listing", "label": "Create your first listing", "done": has_listing, "url": reverse("products:seller_create")},
    ]
    onboarding_done = all(s.get("done") for s in onboarding_steps)

    return render(
        request,
        "products/seller/product_list.html",
        {
            "products": product_data,
            "stripe_ready": stripe_ready,
            "onboarding_steps": onboarding_steps,
            "onboarding_done": onboarding_done,
        },
    )


@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_create(request):
    if request.method == "POST":
        save_mode = (request.POST.get("save_mode") or "").strip().lower()
        current_step = _requested_step(request, default=1)
        form = ProductForm(request.POST)
        if form.is_valid():
            obj: Product = form.save(commit=False)
            obj.seller = request.user

            # Draft-save: always force unpublished.
            if save_mode == "draft":
                obj.is_active = False

            raw_slug = (form.cleaned_data.get("slug") or "").strip()
            if raw_slug:
                obj.slug_is_manual = True
                obj.slug = slugify(raw_slug)
            else:
                obj.slug_is_manual = False
                obj.slug = ""

            obj.save()
            if save_mode == "draft":
                messages.success(request, "Draft saved.")
                return redirect(f"{reverse('products:seller_edit', kwargs={'pk': obj.pk})}?step={current_step}")
            if save_mode == "to_media":
                messages.success(request, "Draft saved. Continue with images.")
                return redirect("products:seller_images", pk=obj.pk)
            messages.success(request, "Listing saved.")
            return redirect(f"{reverse('products:seller_edit', kwargs={'pk': obj.pk})}?step={current_step}")
    else:
        form = ProductForm()

    context = {"form": form, "mode": "create"}
    if form.errors:
        context["error_step"] = _form_error_step(form)
        context["error_field"] = _first_error_field_name(form)
    return render(request, "products/seller/product_form.html", context)

@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_edit(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if request.method == "POST":
        save_mode = (request.POST.get("save_mode") or "").strip().lower()
        current_step = _requested_step(request, default=1)
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            obj: Product = form.save(commit=False)

            # Draft-save: always force unpublished.
            if save_mode == "draft":
                obj.is_active = False

            raw_slug = (form.cleaned_data.get("slug") or "").strip()
            if raw_slug:
                obj.slug_is_manual = True
                obj.slug = slugify(raw_slug)
            else:
                obj.slug_is_manual = False
                obj.slug = ""

            obj.save()
            if save_mode == "draft":
                messages.success(request, "Draft saved.")
                return redirect(f"{reverse('products:seller_edit', kwargs={'pk': obj.pk})}?step={current_step}")
            if save_mode == "to_media":
                messages.success(request, "Listing saved. Continue with images.")
                return redirect("products:seller_images", pk=obj.pk)
            messages.success(request, "Listing updated.")
            return redirect(f"{reverse('products:seller_edit', kwargs={'pk': obj.pk})}?step={current_step}")
    else:
        form = ProductForm(instance=product)

    ok, missing = _publish_checklist(product)
    error_step = _form_error_step(form) if form.errors else _requested_step(request, default=1)
    error_field = _first_error_field_name(form) if form.errors else ""
    return render(
        request,
        "products/seller/product_form.html",
        {
            "form": form,
            "product": product,
            "mode": "edit",
            "publish_ok": ok,
            "publish_missing": missing,
            "error_step": error_step,
            "error_field": error_field,
        },
    )


@seller_required
@stripe_ready_required
@throttle(SELLER_UPLOAD_RULE)
def seller_product_images(request, pk: int):
    product = _get_owned_product_or_404(request, pk)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "save_draft":
            if product.is_active:
                product.is_active = False
                product.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Draft saved.")
            return redirect("products:seller_images", pk=product.pk)
        if action == "publish":
            ok, missing = _publish_checklist(product)
            if not ok:
                messages.error(request, "Cannot publish yet. Missing: " + ", ".join(missing))
                return redirect("products:seller_images", pk=product.pk)
            if not product.is_active:
                product.is_active = True
                product.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Listing published.")
            return redirect("products:seller_list")

        bulk_form = ProductImageBulkUploadForm(request.POST, request.FILES)
        single_form = ProductImageUploadForm(request.POST, request.FILES)
        # Prefer bulk if images[] present
        if request.FILES.getlist("images"):
            if bulk_form.is_valid():
                files = bulk_form.cleaned_data["images"]
                made_primary = product.images.filter(is_primary=True).exists()
                for i, f in enumerate(files):
                    img = ProductImage(product=product, image=f, is_primary=False, sort_order=product.images.count() + i)
                    if not made_primary:
                        img.is_primary = True
                        made_primary = True
                    img.save()
                messages.success(request, f"Uploaded {len(files)} image(s).")
                return redirect("products:seller_images", pk=product.pk)
        else:
            if single_form.is_valid():
                img = single_form.save(commit=False)
                img.product = product
                img.save()
                messages.success(request, "Image uploaded.")
                return redirect("products:seller_images", pk=product.pk)
    else:
        bulk_form = ProductImageBulkUploadForm()
        single_form = ProductImageUploadForm()

    ok, missing = _publish_checklist(product)
    return render(
        request,
        "products/seller/product_images.html",
        {
            "product": product,
            "bulk_form": bulk_form,
            "form": single_form,
            "images": product.images.all(),
            "publish_ok": ok,
            "publish_missing": missing,
        },
    )


@seller_required
@stripe_ready_required
@throttle(SELLER_DELETE_RULE)
def seller_product_image_delete(request, pk: int, image_id: int):
    product = _get_owned_product_or_404(request, pk)
    img = get_object_or_404(ProductImage, pk=image_id, product=product)
    img.delete()
    # Ensure a primary image remains if any images exist
    if product.images.exists() and not product.images.filter(is_primary=True).exists():
        first = product.images.first()
        if first:
            first.is_primary = True
            first.save(update_fields=["is_primary"])
    messages.success(request, "Image deleted.")
    return redirect("products:seller_images", pk=product.pk)


@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_toggle_active(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    ok, missing = _publish_checklist(product)
    if not ok and not product.is_active:
        messages.error(request, "Cannot publish yet. Missing: " + ", ".join(missing))
        return redirect("products:seller_edit", pk=product.pk)

    product.is_active = not product.is_active
    product.save(update_fields=["is_active"])
    messages.success(request, "Published." if product.is_active else "Unpublished.")
    return redirect("products:seller_list")


@seller_required
@stripe_ready_required
@throttle(SELLER_DELETE_RULE)
def seller_product_delete(request, pk: int):
    product = _get_owned_product_or_404(request, pk)
    if request.method == "POST":
        product.delete()
        messages.success(request, "Listing deleted.")
        return redirect("products:seller_list")
    return render(request, "products/seller/product_delete.html", {"product": product})


@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_duplicate(request, pk: int):
    source = _get_owned_product_or_404(request, pk)

    clone = Product()
    for field in Product._meta.fields:
        name = field.name
        if name in {"id", "created_at", "updated_at"}:
            continue
        setattr(clone, name, getattr(source, name))

    clone.seller = request.user
    clone.is_active = False  # duplicated listings start as draft
    clone.slug = ""  # trigger auto slug behavior on save
    clone.slug_is_manual = False
    clone.title = (f"{source.title} (Copy)" if source.title else "Listing copy")[:160]
    clone.save()

    # Copy image rows so the duplicate is immediately editable/publishable.
    for img in source.images.all().order_by("sort_order", "created_at"):
        ProductImage.objects.create(
            product=clone,
            image=img.image.name,
            alt_text=img.alt_text,
            is_primary=img.is_primary,
            sort_order=img.sort_order,
        )

    if clone.images.exists() and not clone.images.filter(is_primary=True).exists():
        first = clone.images.order_by("sort_order", "created_at").first()
        if first:
            first.is_primary = True
            first.save(update_fields=["is_primary"])

    messages.success(request, "Listing duplicated as a draft.")
    return redirect("products:seller_edit", pk=clone.pk)


@seller_required
@stripe_ready_required
@throttle(SELLER_PRODUCT_MUTATE_RULE)
def seller_product_image_update(request, pk: int, image_id):
    product = _get_owned_product_or_404(request, pk)
    img = get_object_or_404(ProductImage, pk=image_id, product=product)

    if request.method == "POST":
        form = ProductImageForm(request.POST, instance=img)
        if form.is_valid():
            updated = form.save(commit=False)

            set_primary = str(request.POST.get("set_primary") or request.POST.get("is_primary") or "").lower() in {
                "1", "true", "on", "yes"
            }
            if set_primary:
                product.images.update(is_primary=False)
                updated.is_primary = True

            updated.save()
            messages.success(request, "Image updated.")
        else:
            messages.error(request, "Could not update image. Please correct the fields.")
    else:
        # Convenient GET action for simple "Make primary" links/buttons.
        if str(request.GET.get("set_primary") or "").lower() in {"1", "true", "on", "yes"}:
            product.images.update(is_primary=False)
            img.is_primary = True
            img.save(update_fields=["is_primary"])
            messages.success(request, "Primary image updated.")

    return redirect("products:seller_images", pk=product.pk)


@seller_required
@throttle(SELLER_CATEGORY_AJAX_RULE)
def seller_subcategories_for_category(request):
    raw = (request.GET.get("category_id") or "").strip()
    try:
        parent_id = int(raw)
    except Exception:
        return JsonResponse({"results": []})

    parent = Category.objects.filter(pk=parent_id, parent__isnull=True, is_active=True).first()
    if not parent:
        return JsonResponse({"results": []})

    qs = Category.objects.filter(parent=parent, is_active=True).order_by("sort_order", "name")
    return JsonResponse({"results": [{"id": c.pk, "text": c.name} for c in qs]})
