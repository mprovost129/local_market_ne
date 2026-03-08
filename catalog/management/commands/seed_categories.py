from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category


GOODS_TREE: dict[str, list[str]] = {
    # Broad “big box” style buckets (Walmart-like), tuned for a local marketplace.
    "Grocery": [
        "Pantry", "Snacks", "Beverages", "Frozen", "Fresh Produce", "Meat & Seafood", "Dairy & Eggs", "Baked Goods",
        "Specialty & Local", "Household Essentials",
    ],
    "Home, Furniture & Kitchen": [
        "Furniture", "Kitchen & Dining", "Bedding", "Bath", "Home Decor", "Storage & Organization", "Lighting",
        "Appliances", "Cleaning Supplies",
    ],
    "Patio, Lawn & Garden": [
        "Outdoor Furniture", "Grills", "Lawn Care", "Gardening", "Outdoor Decor", "Snow & Seasonal",
    ],
    "Tools & Home Improvement": [
        "Power Tools", "Hand Tools", "Hardware", "Plumbing", "Electrical", "Paint", "Building Materials", "Safety & Security",
    ],
    "Electronics": [
        "Computers", "Phones", "TV & Video", "Audio", "Cameras", "Gaming", "Smart Home", "Accessories",
    ],
    "Clothing, Shoes & Accessories": [
        "Women", "Men", "Kids", "Shoes", "Jewelry", "Watches", "Bags & Accessories",
    ],
    "Baby & Kids": [
        "Baby Gear", "Baby Clothing", "Kids Clothing", "Feeding", "Diapers", "Kids Furniture", "Kids Room",
    ],
    "Toys & Games": [
        "Outdoor Play", "Board Games", "Puzzles", "Action Figures", "Dolls", "STEM & Learning", "Collectibles",
    ],
    "Health & Wellness": [
        "OTC", "Vitamins", "Personal Care", "Medical Supplies", "Fitness", "Wellness",
    ],
    "Beauty": [
        "Makeup", "Skin Care", "Hair Care", "Fragrance", "Nails", "Bath & Body",
    ],
    "Pets": [
        "Dog", "Cat", "Bird", "Fish", "Small Pet", "Pet Supplies",
    ],
    "Sports & Outdoors": [
        "Fitness", "Camping", "Hunting & Fishing", "Cycling", "Team Sports", "Water Sports", "Fan Shop",
    ],
    "Auto & Tires": [
        "Car Care", "Parts & Accessories", "Tools & Equipment", "Tires", "Motorcycle & ATV",
    ],
    "Office, School & Crafts": [
        "Office Supplies", "School Supplies", "Art Supplies", "Crafts & Sewing", "Printing",
    ],
    "Books, Movies & Music": [
        "Books", "Movies", "Music", "Video Games", "Magazines",
    ],
    "Seasonal": [
        "Holiday", "Party Supplies", "Gifts", "Back-to-School", "Outdoor Seasonal",
    ],
}


SERVICES_TREE: dict[str, list[str]] = {
    "Home Services": [
        "Cleaning", "Handyman", "Plumbing", "Electrical", "HVAC", "Landscaping", "Snow Removal", "Moving & Labor",
        "Painting", "Home Improvement",
    ],
    "Automotive Services": [
        "Detailing", "Oil Change", "Tires", "Diagnostics", "Repairs", "Body Work",
    ],
    "Beauty & Wellness Services": [
        "Hair", "Nails", "Massage", "Fitness Training", "Wellness",
    ],
    "Lessons & Tutoring": [
        "Academic Tutoring", "Music Lessons", "Sports Coaching", "Arts & Crafts",
    ],
    "Events & Entertainment": [
        "Photography", "DJ", "Catering", "Party Services", "Venue Support",
    ],
    "Pet Services": [
        "Grooming", "Walking", "Sitting", "Training",
    ],
    "Business Services": [
        "Marketing", "Design", "Bookkeeping", "IT Support", "Consulting",
    ],
}


class Command(BaseCommand):
    help = "Seed broad Product and Services categories (Walmart-like top-level buckets) for LocalMarketNE."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing categories first (both goods and services).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = bool(options.get("reset"))
        if reset:
            Category.objects.all().delete()

        created = 0
        updated = 0

        def upsert_root(cat_type: str, name: str, sort: int) -> Category:
            nonlocal created, updated
            slug = None
            obj, was_created = Category.objects.get_or_create(
                type=cat_type,
                parent=None,
                slug=(slug or ""),
                defaults={"name": name, "sort_order": sort, "is_active": True},
            )
            # get_or_create can't key on slug if auto-generated; so we lookup by name instead
            if not was_created:
                obj_qs = Category.objects.filter(type=cat_type, parent=None, name=name)
                if obj_qs.exists():
                    obj = obj_qs.first()
                else:
                    obj.name = name
                    obj.sort_order = sort
                    obj.is_active = True
                    obj.save()
                    updated += 1
                    return obj

            if was_created:
                # ensure proper slug generation
                obj.name = name
                obj.sort_order = sort
                obj.is_active = True
                obj.save()
                created += 1
            return obj

        def upsert_child(parent: Category, name: str, sort: int) -> None:
            nonlocal created, updated
            qs = Category.objects.filter(type=parent.type, parent=parent, name=name)
            if qs.exists():
                obj = qs.first()
                changed = False
                if obj.sort_order != sort:
                    obj.sort_order = sort
                    changed = True
                if not obj.is_active:
                    obj.is_active = True
                    changed = True
                if changed:
                    obj.save()
                    updated += 1
                return

            obj = Category(type=parent.type, parent=parent, name=name, sort_order=sort, is_active=True)
            obj.save()
            created += 1

        # Goods
        for idx, (root_name, children) in enumerate(GOODS_TREE.items(), start=1):
            root = Category.objects.filter(type=Category.CategoryType.GOOD, parent=None, name=root_name).first()
            if not root:
                root = Category(type=Category.CategoryType.GOOD, parent=None, name=root_name, sort_order=idx * 10)
                root.save()
                created += 1
            else:
                if root.sort_order != idx * 10:
                    root.sort_order = idx * 10
                    root.save()
                    updated += 1

            for c_idx, child_name in enumerate(children, start=1):
                upsert_child(root, child_name, c_idx * 10)

        # Services
        for idx, (root_name, children) in enumerate(SERVICES_TREE.items(), start=1):
            root = Category.objects.filter(type=Category.CategoryType.SERVICE, parent=None, name=root_name).first()
            if not root:
                root = Category(type=Category.CategoryType.SERVICE, parent=None, name=root_name, sort_order=idx * 10)
                root.save()
                created += 1
            else:
                if root.sort_order != idx * 10:
                    root.sort_order = idx * 10
                    root.save()
                    updated += 1

            for c_idx, child_name in enumerate(children, start=1):
                upsert_child(root, child_name, c_idx * 10)

        self.stdout.write(self.style.SUCCESS(f"Seed complete. created={created}, updated={updated}"))
