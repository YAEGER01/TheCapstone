from django.db import migrations


# Standard Philippine SUC faculty ladder (NBC 461) + kept legacy buckets.
# Additive only: existing rows are never renamed or deleted.
CATEGORIES = [
    "Instructor",
    "Assistant Professor",
    "Associate Professor",
    "Professor",
    "Full Professor",
    "Administrative",
    "Staff",
    "Other",
]

RANKS = (
    [("Instructor %s" % n, "Instructor") for n in ("I", "II", "III")]
    + [("Assistant Professor %s" % n, "Assistant Professor") for n in ("I", "II", "III", "IV")]
    + [("Associate Professor %s" % n, "Associate Professor") for n in ("I", "II", "III", "IV", "V")]
    + [("Professor %s" % n, "Professor") for n in ("I", "II", "III", "IV", "V", "VI")]
    + [("University Professor", "Professor")]
)


def seed_academic_ranks(apps, schema_editor):
    PositionCategory = apps.get_model("core_system", "PositionCategory")
    PositionRank = apps.get_model("core_system", "PositionRank")

    for name in CATEGORIES:
        PositionCategory.objects.get_or_create(
            name=name, defaults={"is_active": True}
        )

    for rank_name, category_name in RANKS:
        PositionCategory.objects.get_or_create(
            name=category_name, defaults={"is_active": True}
        )
        # Case-insensitive match so live rows such as "ASSISTANT PROFESSOR II"
        # are not duplicated by the title-case seed.
        if not PositionRank.objects.filter(name__iexact=rank_name).exists():
            PositionRank.objects.create(
                name=rank_name, category=category_name, is_active=True
            )


def unseed_academic_ranks(apps, schema_editor):
    # Seeded rows become user-managed; leave data intact on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0150_backupjob_system_archive_path_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_academic_ranks, unseed_academic_ranks),
    ]
