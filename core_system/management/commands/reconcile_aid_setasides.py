"""
Read-only reconciliation of the President's split approval booking.

Every approved MemberAssessment should be booked as up to three inflows that
sum back to actual_deduction:

    monthly_dues            -> dues portion (non-aid allocations + prior
                               collected + change)
    aid_setaside_medical    -> medical-aid allocations
    aid_setaside_death      -> death-aid allocations

Months approved before the split existed carry the whole figure on one
``monthly_dues`` row. This command derives what each member's split *should*
be from the stored allocations and reports, without writing anything:

    OK        the booked rows already match the derived split
    LEGACY    a single monthly_dues row for the full amount (pre-split month)
    SPLIT     the aid rows exist but their amounts do not match
    MISSING   approved with money deducted but no ledger row at all

Run:
    python manage.py reconcile_aid_setasides
    python manage.py reconcile_aid_setasides --month 2026-09
    python manage.py reconcile_aid_setasides --since 2026-01 --show-ok
    python manage.py reconcile_aid_setasides --json > report.json
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch

from core_system.aid_setaside import (
    BOOKING_SOURCE_TYPES,
    SETASIDE_SOURCE_TYPES,
    derive_split,
)
from core_system.models import (
    FundTransaction,
    MemberAssessment,
    MemberAssessmentAllocation,
)

CENT = Decimal("0.01")


def _month_key(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise CommandError("--month/--since expect YYYY-MM (e.g. 2026-09)")


class Command(BaseCommand):
    help = "Report how each approved deduction was booked (dues vs aid set-aside). Read-only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            action="append",
            default=[],
            metavar="YYYY-MM",
            help="Limit to these covered months (repeatable).",
        )
        parser.add_argument(
            "--since",
            metavar="YYYY-MM",
            help="Limit to covered months from this one onward.",
        )
        parser.add_argument(
            "--show-ok",
            action="store_true",
            help="Also print rows whose booking already matches.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit the report as JSON instead of a table.",
        )

    def handle(self, *args, **options):
        months = sorted({_month_key(m) for m in options["month"]})
        since = _month_key(options["since"]) if options["since"] else None
        show_ok = options["show_ok"]

        qs = (
            MemberAssessment.objects.select_related(
                "assessment_id_FK", "member_id_FK"
            )
            .prefetch_related(
                Prefetch(
                    "allocations",
                    queryset=MemberAssessmentAllocation.objects.select_related(
                        "assessment_item_id_FK"
                    ),
                )
            )
            .order_by("assessment_id_FK__month", "member_id_FK__full_name")
        )
        if months:
            wanted = set(months)
            qs = [
                ma
                for ma in qs
                if ma.assessment_id_FK.month
                and ma.assessment_id_FK.month.strftime("%Y-%m") in wanted
            ]
        elif since:
            qs = qs.filter(assessment_id_FK__month__gte=f"{since}-01")

        report = []
        for ma in qs:
            row = self._inspect(ma)
            if row is None:
                continue
            report.append(row)

        mismatches = [r for r in report if r["status"] in ("SPLIT", "MISSING")]
        legacy = [r for r in report if r["status"] == "LEGACY"]
        ok = [r for r in report if r["status"] == "OK"]
        missing = [r for r in report if r["status"] == "MISSING"]
        mismatched = [r for r in report if r["status"] == "SPLIT"]
        legacy_aid = sum((Decimal(r["legacy_aid_as_dues"]) for r in legacy), Decimal("0.00"))

        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                        "summary": {
                            "rows": len(report),
                            "ok": len(ok),
                            "legacy": len(legacy),
                            "mismatch": len(mismatched),
                            "missing": len(missing),
                            "aid_booked_as_dues": str(legacy_aid),
                        },
                        "rows": report,
                    },
                    indent=2,
                    default=str,
                )
            )
            return

        shown = [r for r in report if r["status"] != "OK" or show_ok]
        if not shown:
            self.stdout.write("No member assessments matched.")
        for r in shown:
            self.stdout.write(self._line(r))

        self.stdout.write("")
        self.stdout.write(
            "rows=%d  ok=%d  legacy=%d  mismatch=%d  missing=%d"
            % (len(report), len(ok), len(legacy), len(mismatched), len(missing))
        )
        if legacy_aid:
            self.stdout.write(
                "aid portion currently booked as monthly_dues: %s" % legacy_aid
            )
        if mismatches:
            self.stdout.write(self.style.WARNING("%d row(s) need attention." % len(mismatches)))

    def _inspect(self, ma) -> dict | None:
        actual = (ma.actual_deduction or Decimal("0.00")).quantize(CENT)
        dues_portion, medical_total, death_total, _ = derive_split(ma)
        derived_total = (dues_portion + medical_total + death_total).quantize(CENT)

        rows = {
            r.source_type: r
            for r in FundTransaction.objects.filter(
                source_type__in=BOOKING_SOURCE_TYPES, source_id=ma.member_assessment_id_PK
            )
        }
        booked = {
            st: (rows[st].amount.quantize(CENT) if st in rows else Decimal("0.00"))
            for st in BOOKING_SOURCE_TYPES
        }
        booked_total = sum(booked.values(), Decimal("0.00")).quantize(CENT)

        aid_expected = (medical_total + death_total).quantize(CENT)
        has_aid_rows = any(st in rows for st in SETASIDE_SOURCE_TYPES)

        if not rows:
            # A month still in flight (or one that was returned/rejected) has
            # no ledger rows yet — nothing to reconcile until it is approved.
            if ma.status != MemberAssessment.STATUS_APPROVED:
                return None
            status = "MISSING" if actual > 0 else "OK"
        elif has_aid_rows:
            status = (
                "OK"
                if booked["monthly_dues"] == dues_portion
                and booked["aid_setaside_medical"] == medical_total
                and booked["aid_setaside_death"] == death_total
                else "SPLIT"
            )
        elif aid_expected > 0:
            status = "LEGACY"
        else:
            status = "OK"

        if status == "LEGACY":
            legacy_aid = min(aid_expected, booked["monthly_dues"])
        else:
            legacy_aid = Decimal("0.00")

        return {
            "month": ma.assessment_id_FK.month.strftime("%Y-%m"),
            "member_assessment": ma.member_assessment_id_PK,
            "member": ma.member_id_FK.full_name,
            "actual": str(actual),
            "derived": {
                "monthly_dues": str(dues_portion),
                "aid_setaside_medical": str(medical_total),
                "aid_setaside_death": str(death_total),
                "total": str(derived_total),
            },
            "booked": {k: str(v) for k, v in booked.items()},
            "booked_total": str(booked_total),
            "status": status,
            "legacy_aid_as_dues": str(legacy_aid),
            "variance": str((booked_total - actual).quantize(CENT)),
        }

    @staticmethod
    def _line(r) -> str:
        return (
            "%-7s %s  ma=%-6s %-32s actual=%9s  dues=%9s med=%9s death=%9s  booked_total=%9s"
            % (
                r["status"],
                r["month"],
                r["member_assessment"],
                (r["member"] or "")[:32],
                r["actual"],
                r["derived"]["monthly_dues"],
                r["derived"]["aid_setaside_medical"],
                r["derived"]["aid_setaside_death"],
                r["booked_total"],
            )
        )
