from django.db import migrations


DEFAULT_CATEGORIES = [
    "Instructor",
    "Assistant Professor",
    "Associate Professor",
    "Full Professor",
    "Administrative",
    "Staff",
    "Other",
]


def seed_categories(apps, schema_editor):
    """Seed the previous hardcoded categories plus any already used by ranks."""
    PositionCategory = apps.get_model("core_system", "PositionCategory")
    PositionRank = apps.get_model("core_system", "PositionRank")

    names = list(DEFAULT_CATEGORIES)
    existing = (
        PositionRank.objects.exclude(category__isnull=True)
        .exclude(category="")
        .values_list("category", flat=True)
        .distinct()
    )
    for name in existing:
        if name not in names:
            names.append(name)

    for name in names:
        PositionCategory.objects.get_or_create(name=name)


def unseed_categories(apps, schema_editor):
    # Categories become user-managed; leave existing data intact on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0133_positioncategory"),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]
