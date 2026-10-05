"""Officer feedback forms.

A Superadmin-authored instrument (multiple choice / Likert / freeform text)
that renders as one shared card on the President, Treasurer and Auditor
dashboards. Officers submit once per form; the Superadmin reviews and exports.

Design notes:

* Officer identity always comes from the validated ``AccessSession``, never
  from a submitted field. ``_officer_for_request`` is the only place an
  officer is resolved.
* Every answer is re-validated against the *question's own definition* on the
  server, and every question is looked up scoped to the posted form, so a
  crafted submission cannot attach answers to questions it does not own.
* Officers may read only their own response. Listings and exports are
  Superadmin-only and are audited.
* CSV export guards against spreadsheet formula injection: a cell beginning
  with ``= + - @`` (or a tab/CR) is prefixed with a single quote so Excel and
  Sheets treat it as text rather than executing it.
* PDF export escapes freeform text with ``xml.sax.saxutils.escape`` before
  handing it to reportlab, whose ``Paragraph`` parser would otherwise treat
  angle brackets in a response as markup.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core_system.guards import require_role
from core_system.models import (
    AccessSession,
    FeedbackAnswer,
    FeedbackForm,
    FeedbackQuestion,
    FeedbackResponse,
    OfficerUser,
    FEEDBACK_ROLES,
    FEEDBACK_TEXT_MAX,
)

logger = logging.getLogger(__name__)

# Officer dashboards that host the shared card.
DASHBOARD_ROLES = ("President", "Treasurer", "Auditor")

# Leading characters that make a spreadsheet treat a cell as a formula.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

_MAX_EXPORT_ROWS = 2000


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _officer_for_request(request: HttpRequest) -> OfficerUser | None:
    """Resolve the officer behind the current AccessSession.

    Never trusts request.POST/GET. Returns None when the session is dead.
    """
    token = request.session.get("access_token")
    if not token:
        return None
    sess = AccessSession.objects.select_related("user_id_FK").filter(token_id=token).first()
    if sess is None:
        return None
    return sess.user_id_FK


def _wants_json(request: HttpRequest) -> bool:
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in (request.headers.get("Accept") or "")
    )


def _strip_control(value: str) -> str:
    """Drop NUL and C0 control characters, keeping tab/newline."""
    return "".join(
        ch for ch in value
        if ch in ("\n", "\t") or (ord(ch) >= 32 and ord(ch) != 127)
    )


def _clean_text(raw: Any) -> str:
    text = _strip_control(str(raw or "")).strip()
    return text[:FEEDBACK_TEXT_MAX]


def _csv_safe(value: Any) -> str:
    """Neutralise spreadsheet formula injection in an exported cell."""
    text = str(value if value is not None else "")
    if text[:1] in _CSV_FORMULA_PREFIXES:
        return "'" + text
    return text


def _audit(request: HttpRequest, *, table: str, record_id: int, action: str,
           actor: OfficerUser, new: dict | None = None, notes: str = "") -> None:
    try:
        from core_system.shared_view_utils import _record_audit_trail

        _record_audit_trail(
            table=table,
            record_id=record_id,
            action=action,
            actor=actor,
            old=None,
            new=new,
            ip=request.META.get("REMOTE_ADDR"),
            device_info=request.META.get("HTTP_USER_AGENT"),
            notes=notes,
        )
    except Exception:
        logger.exception("Feedback audit trail write failed")


def _active_form_for(officer: OfficerUser) -> FeedbackForm | None:
    """The form this officer should be answering, if any."""
    forms = FeedbackForm.objects.filter(
        is_active=True, is_archived=False, is_open=True
    ).prefetch_related("questions")
    for form in forms:
        if form.applies_to(officer.role):
            return form
    return None


def _parse_json_body(request: HttpRequest) -> dict:
    try:
        parsed = json.loads(request.body.decode("utf-8") or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (UnicodeDecodeError, ValueError):
        return {}


def _submitted_answers(request: HttpRequest) -> dict:
    """Answers from either a JSON body or a classic form post."""
    if request.content_type and "json" in request.content_type.lower():
        body = _parse_json_body(request)
        raw = body.get("answers")
        if isinstance(raw, dict):
            return {str(k): v for k, v in raw.items()}
        if isinstance(raw, list):
            # [{"question_id": 1, "value": ...}, ...]
            out = {}
            for item in raw:
                if isinstance(item, dict) and "question_id" in item:
                    out[str(item["question_id"])] = item.get("value")
            return out
        return {}

    out: dict = {}
    for key in request.POST:
        if key.startswith("q_"):
            out[key[2:]] = request.POST.getlist(key) if key in request.POST else request.POST.get(key)
    return out


def _scalar(raw: Any) -> Any:
    """Unwrap a single-element answer list.

    ``request.POST.getlist`` always returns a list, so a radio/Likert answer
    arrives as ``["2"]`` and a textarea as ``["text"]``. Only multiple choice
    is genuinely multi-valued, so the scalar branches unwrap first.
    """
    if isinstance(raw, (list, tuple)) and len(raw) == 1:
        return raw[0]
    return raw


# ---------------------------------------------------------------------------
# Officer-facing: the shared card
# ---------------------------------------------------------------------------

@require_GET
def feedback_card(request: HttpRequest):
    """Server-rendered feedback modal + prompt toast for the signed-in officer.

    Returns an empty body in every case where the officer should not be
    prompted: no officer session, no form published to their role, or the
    officer has already responded. That last rule is what makes the prompt
    one-shot - once a response exists the modal and the toast never render
    again for that form.
    """
    guard = require_role(request, role=list(DASHBOARD_ROLES))
    if guard is not None:
        return guard

    officer = _officer_for_request(request)
    if officer is None:
        return HttpResponse("", content_type="text/html; charset=utf-8")

    form = _active_form_for(officer)
    if form is None:
        return HttpResponse("", content_type="text/html; charset=utf-8")

    # One-shot prompt: an existing response means this officer is done.
    already_answered = FeedbackResponse.objects.filter(
        form_id_FK=form, officer_id_FK=officer
    ).exists()
    if already_answered:
        return HttpResponse("", content_type="text/html; charset=utf-8")

    questions = list(form.questions.all())
    if not questions:
        return HttpResponse("", content_type="text/html; charset=utf-8")

    first_name = (officer.full_name or officer.username or "officer").split(" ")[0]

    html = render(
        request,
        "website/shared/feedback_card_content.html",
        {
            "fb_form": form,
            "fb_officer_first": first_name,
            "fb_questions": questions,
            "fb_question_count": len(questions),
            "fb_max_text": FEEDBACK_TEXT_MAX,
        },
    ).content.decode("utf-8")
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@require_POST
def feedback_submit(request: HttpRequest):
    """Validate and store one officer's answers for the active form."""
    guard = require_role(request, role=list(DASHBOARD_ROLES))
    if guard is not None:
        return guard

    officer = _officer_for_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session expired."}, status=401)

    submitted_form_id = request.POST.get("form_id") or _parse_json_body(request).get("form_id")
    raw_answers = _submitted_answers(request)

    if not submitted_form_id:
        return JsonResponse({"ok": False, "error": "Missing form reference."}, status=400)

    # Scope the form lookup to the officer's role: a form that is not being
    # shown to this officer cannot be answered by them.
    form = (
        FeedbackForm.objects
        .filter(form_id_PK=submitted_form_id)
        .prefetch_related("questions")
        .first()
    )
    if form is None:
        return JsonResponse({"ok": False, "error": "Unknown form."}, status=404)
    if not form.applies_to(officer.role):
        return JsonResponse({"ok": False, "error": "This form is not open to your role."}, status=403)
    if not form.is_open:
        return JsonResponse({"ok": False, "error": "This form is no longer accepting responses."}, status=403)

    questions = list(form.questions.all())
    by_id = {str(q.question_id_PK): q for q in questions}

    unknown = [k for k in raw_answers if k not in by_id]
    if unknown:
        return JsonResponse(
            {"ok": False, "error": "Submission contains questions that are not part of this form."},
            status=400,
        )

    errors: list[str] = []
    cleaned: list[tuple[FeedbackQuestion, Any]] = []

    for question in questions:
        key = str(question.question_id_PK)
        raw = raw_answers.get(key)
        provided = raw is not None and raw != "" and raw != []

        if not provided:
            if question.is_required:
                errors.append(f"'{question.prompt[:60]}' is required.")
            continue

        if question.qtype == "mc":
            values = raw if isinstance(raw, list) else [raw]
            values = [str(v).strip() for v in values if str(v).strip()]
            allowed = set(question.option_labels())
            bad = [v for v in values if v not in allowed]
            if bad:
                errors.append(f"'{question.prompt[:60]}' has an invalid selection.")
                continue
            if len(values) < question.min_choices or len(values) > question.max_choices:
                errors.append(
                    f"'{question.prompt[:60]}' needs between {question.min_choices} "
                    f"and {question.max_choices} selection(s)."
                )
                continue
            # De-duplicate while preserving the authored option order.
            ordered = [o for o in question.option_labels() if o in set(values)]
            cleaned.append((question, ordered))

        elif question.qtype == "likert":
            try:
                value = int(str(_scalar(raw)).strip())
            except (TypeError, ValueError):
                errors.append(f"'{question.prompt[:60]}' needs a numeric rating.")
                continue
            if value < question.scale_min or value > question.scale_max:
                errors.append(
                    f"'{question.prompt[:60]}' must be between {question.scale_min} "
                    f"and {question.scale_max}."
                )
                continue
            cleaned.append((question, value))

        else:  # freeform text
            text = _clean_text(_scalar(raw))
            if not text:
                if question.is_required:
                    errors.append(f"'{question.prompt[:60]}' is required.")
                continue
            cleaned.append((question, text))

    if errors:
        return JsonResponse({"ok": False, "error": " ".join(errors)}, status=400)

    existing = FeedbackResponse.objects.filter(form_id_FK=form, officer_id_FK=officer).first()
    created = existing is None

    response = existing
    if response is None:
        response = FeedbackResponse(
            form_id_FK=form,
            officer_id_FK=officer,
            ip_address=request.META.get("REMOTE_ADDR") or None,
            device_info=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        )
    # The response row must have a PK before its related answers can be
    # traversed, so save first and only then clear the previous answers.
    response.save()
    response.answers.all().delete()

    for question, value in cleaned:
        answer = FeedbackAnswer(
            response_id_FK=response,
            question_id_FK=question,
        )
        if question.qtype == "likert":
            answer.value_int = int(value)
        elif question.qtype == "mc":
            answer.value_list = list(value)
        else:
            answer.value_text = value
        answer.save()

    _audit(
        request,
        table="feedback_response",
        record_id=response.response_id_PK,
        action="FEEDBACK_SUBMITTED" if created else "FEEDBACK_UPDATED",
        actor=officer,
        new={"form": form.title, "answers": len(cleaned)},
        notes=f"{'Submitted' if created else 'Updated'} feedback for '{form.title}'",
    )

    first_name = (officer.full_name or officer.username or "officer").split(" ")[0]
    return JsonResponse({
        "ok": True,
        "created": created,
        "first_name": first_name,
        "message": f"Thanks {first_name} for submitting your feedback",
    })


# ---------------------------------------------------------------------------
# Superadmin: authoring
# ---------------------------------------------------------------------------

@require_GET
def feedback_admin(request: HttpRequest):
    """Authoring screen: list forms, edit one, view its responses."""
    guard = require_role(request, role="Superadmin")
    if guard is not None:
        return guard

    officer = _officer_for_request(request)
    if officer is None:
        return guard or JsonResponse({"ok": False, "error": "Session expired."}, status=401)

    forms = list(
        FeedbackForm.objects
        .all()
        .prefetch_related("questions")
        .annotate(
            n_questions=Count("questions"),
            n_responses=Count("responses"),
        )
    )
    selected_id = request.GET.get("form")
    selected = None
    if selected_id:
        selected = next((f for f in forms if str(f.form_id_PK) == str(selected_id)), None)

    selected_responses = []
    response_rows = []
    if selected is not None:
        selected_questions = list(selected.questions.all())
        selected_responses = list(
            selected.responses
            .select_related("officer_id_FK")
            .prefetch_related("answers__question_id_FK")
        )
        for response in selected_responses:
            answers = response.answer_map()
            response_rows.append({
                "officer": response.officer_id_FK.full_name or response.officer_id_FK.username,
                "role": response.officer_id_FK.role or "",
                "submitted": response.submitted_at,
                "cells": [
                    answers[q.question_id_PK].display_value() if q.question_id_PK in answers else ""
                    for q in selected_questions
                ],
            })

    return render(request, "website/Superadmin/feedback_admin.html", {
        "fb_forms": forms,
        "fb_selected": selected,
        "fb_selected_questions": list(selected.questions.all()) if selected is not None else [],
        "fb_selected_responses": selected_responses,
        "fb_response_rows": response_rows,
        "fb_roles": FEEDBACK_ROLES,
        "fb_form_type_choices": FeedbackQuestion._meta.get_field("qtype").choices,
    })


@require_POST
def feedback_admin_save(request: HttpRequest):
    """Create or update a form and its questions from one payload."""
    guard = require_role(request, role="Superadmin")
    if guard is not None:
        return guard

    officer = _officer_for_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session expired."}, status=401)

    body = _parse_json_body(request) if (
        request.content_type and "json" in request.content_type.lower()
    ) else request.POST.dict()
    questions_in = body.get("questions")
    if isinstance(questions_in, str):
        questions_in = _parse_json_body(request).get("questions")
    if not isinstance(questions_in, list):
        questions_in = []

    title = _clean_text(body.get("title"))[:200]
    if not title:
        return JsonResponse({"ok": False, "error": "A form title is required."}, status=400)

    section_title = _clean_text(body.get("section_title"))[:200]
    description = _clean_text(body.get("description"))[:2000]

    roles = body.get("show_on_roles")
    if isinstance(roles, str):
        roles = [r for r in roles.split(",") if r.strip()]
    if not isinstance(roles, list):
        roles = []
    valid_roles = [r for r in roles if r in FEEDBACK_ROLES]

    form_id = body.get("form_id")
    form = None
    if form_id:
        form = FeedbackForm.objects.filter(form_id_PK=form_id).first()
        if form is None:
            return JsonResponse({"ok": False, "error": "Unknown form."}, status=404)

    created = form is None
    if form is None:
        form = FeedbackForm(created_by_id_FK=officer)
    form.title = title
    form.section_title = section_title
    form.description = description
    form.show_on_roles = valid_roles
    form.is_active = str(body.get("is_active", "on")).lower() not in ("off", "false", "0", "")
    form.is_open = str(body.get("is_open", "on")).lower() not in ("off", "false", "0", "")
    form.save()

    # Questions are replaced wholesale: a simple, predictable authoring model
    # for a Superadmin-only screen with no concurrent editors.
    form.questions.all().delete()

    order = 0
    saved = 0
    for item in questions_in:
        if not isinstance(item, dict):
            continue
        prompt = _clean_text(item.get("prompt"))[:400]
        if not prompt:
            continue
        qtype = str(item.get("qtype") or "mc")
        if qtype not in ("mc", "likert", "text"):
            qtype = "mc"

        options = item.get("options")
        if isinstance(options, str):
            options = [o.strip() for o in options.split("\n")]
        if not isinstance(options, list):
            options = []
        options = [_clean_text(o)[:200] for o in options if _clean_text(o)][:12]

        try:
            scale_min = int(item.get("scale_min") or 1)
            scale_max = int(item.get("scale_max") or 5)
        except (TypeError, ValueError):
            scale_min, scale_max = 1, 5
        if scale_min >= scale_max:
            scale_max = scale_min + 1

        try:
            min_choices = max(1, int(item.get("min_choices") or 1))
            max_choices = max(1, int(item.get("max_choices") or 1))
        except (TypeError, ValueError):
            min_choices = max_choices = 1
        if max_choices < min_choices:
            max_choices = min_choices

        if qtype == "likert":
            min_choices = max_choices = 1

        FeedbackQuestion.objects.create(
            form_id_FK=form,
            prompt=prompt,
            qtype=qtype,
            options=options,
            scale_min=scale_min,
            scale_max=scale_max,
            min_choices=min_choices,
            max_choices=max_choices,
            is_required=str(item.get("is_required", "on")).lower() not in ("off", "false", "0", ""),
            display_order=order,
            help_text=_clean_text(item.get("help_text"))[:300],
        )
        order += 1
        saved += 1

    _audit(
        request,
        table="feedback_form",
        record_id=form.form_id_PK,
        action="FEEDBACK_FORM_SAVED",
        actor=officer,
        new={"title": title, "questions": saved, "roles": valid_roles},
        notes=f"{'Created' if created else 'Updated'} feedback form '{title}'",
    )

    return JsonResponse({
        "ok": True,
        "form_id": form.form_id_PK,
        "created": created,
        "message": f"Feedback form saved with {saved} question(s).",
    })


@require_POST
def feedback_admin_toggle(request: HttpRequest):
    """Flip is_active / is_open / is_archived on a form."""
    guard = require_role(request, role="Superadmin")
    if guard is not None:
        return guard

    officer = _officer_for_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session expired."}, status=401)

    body = _parse_json_body(request) if (
        request.content_type and "json" in request.content_type.lower()
    ) else request.POST.dict()

    form = FeedbackForm.objects.filter(form_id_PK=body.get("form_id")).first()
    if form is None:
        return JsonResponse({"ok": False, "error": "Unknown form."}, status=404)

    changed = []
    for field in ("is_active", "is_open", "is_archived"):
        if field in body:
            value = str(body.get(field)).lower() not in ("off", "false", "0", "")
            if getattr(form, field) != value:
                changed.append(f"{field}={'on' if value else 'off'}")
            setattr(form, field, value)
    form.save(update_fields=["is_active", "is_open", "is_archived", "updated_at"])

    _audit(
        request,
        table="feedback_form",
        record_id=form.form_id_PK,
        action="FEEDBACK_FORM_TOGGLED",
        actor=officer,
        new={f: getattr(form, f) for f in ("is_active", "is_open", "is_archived")},
        notes=f"{', '.join(changed) or 'no change'} on '{form.title}'",
    )
    return JsonResponse({"ok": True, "message": "Form updated."})


@require_POST
def feedback_admin_delete(request: HttpRequest):
    """Archive a form, or delete it outright when it has no responses."""
    guard = require_role(request, role="Superadmin")
    if guard is not None:
        return guard

    officer = _officer_for_request(request)
    if officer is None:
        return JsonResponse({"ok": False, "error": "Session expired."}, status=401)

    body = _parse_json_body(request) if (
        request.content_type and "json" in request.content_type.lower()
    ) else request.POST.dict()

    form = FeedbackForm.objects.filter(form_id_PK=body.get("form_id")).first()
    if form is None:
        return JsonResponse({"ok": False, "error": "Unknown form."}, status=404)

    if form.responses.exists():
        form.is_archived = True
        form.is_active = False
        form.is_open = False
        form.save(update_fields=["is_archived", "is_active", "is_open", "updated_at"])
        action, message = "FEEDBACK_FORM_ARCHIVED", "Form archived (responses retained)."
    else:
        form.delete()
        action, message = "FEEDBACK_FORM_DELETED", "Form deleted."

    _audit(
        request,
        table="feedback_form",
        record_id=body.get("form_id"),
        action=action,
        actor=officer,
        notes=message,
    )
    return JsonResponse({"ok": True, "message": message})


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def _export_matrix(form: FeedbackForm, limit: int = _MAX_EXPORT_ROWS):
    """Return (header_rows, data_rows) shared by every export format."""
    questions = list(form.questions.all())
    responses = list(
        form.responses
        .select_related("officer_id_FK")
        .prefetch_related("answers__question_id_FK")[:limit]
    )

    header = ["Officer", "Role", "Submitted"] + [f"Q{i}" for i in range(1, len(questions) + 1)]

    rows = []
    for response in responses:
        answers = response.answer_map()
        row = [
            response.officer_id_FK.full_name or response.officer_id_FK.username,
            response.officer_id_FK.role or "",
            timezone.localtime(response.submitted_at).strftime("%Y-%m-%d %H:%M"),
        ]
        for question in questions:
            answer = answers.get(question.question_id_PK)
            row.append(answer.display_value() if answer else "")
        rows.append(row)

    return questions, responses, header, rows


@require_GET
def feedback_export(request: HttpRequest, form_id: int):
    """Superadmin-only export of a form's responses as CSV, PDF or TXT."""
    guard = require_role(request, role="Superadmin")
    if guard is not None:
        return guard

    form = (
        FeedbackForm.objects
        .filter(form_id_PK=form_id)
        .prefetch_related("questions")
        .first()
    )
    if form is None:
        return JsonResponse({"ok": False, "error": "Unknown form."}, status=404)

    fmt = (request.GET.get("format") or "csv").lower()
    if fmt not in ("csv", "pdf", "txt"):
        return JsonResponse({"ok": False, "error": "Unsupported export format."}, status=400)

    questions, responses, header, rows = _export_matrix(form)

    # Prompts go in a legend so the columns stay narrow and readable.
    legend = [f"Q{i}: {q.prompt}" + (f" [{q.qtype}]" if q.qtype != "mc" else "") for i, q in enumerate(questions, 1)]

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (form.title or "feedback"))[:60]

    if fmt == "csv":
        buffer = io.StringIO()
        # QUOTE_ALL plus _csv_safe guards spreadsheet formula injection on
        # every cell, including officer-supplied free text.
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
        writer.writerow([_csv_safe(form.title)])
        writer.writerow([_csv_safe(f"Generated {timezone.localtime().strftime('%Y-%m-%d %H:%M')}")])
        writer.writerow([])
        writer.writerow([_csv_safe(h) for h in header])
        for row in rows:
            writer.writerow([_csv_safe(c) for c in row])
        writer.writerow([])
        for line in legend:
            writer.writerow([_csv_safe(line)])

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_responses.csv"'

    elif fmt == "txt":
        lines = [
            form.title,
            f"Generated {timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
            f"Responses: {len(rows)}",
            "",
            "QUESTIONS",
        ]
        lines += [f"  {line}" for line in legend] or ["  (none)"]
        lines += ["", "RESPONSES", ""]
        if not rows:
            lines.append("  (no responses yet)")
        for row in rows:
            lines.append("-" * 60)
            lines.append(f"  {row[0]}  ({row[1]})  -  {row[2]}")
            for i, value in enumerate(row[3:], 1):
                lines.append(f"    Q{i}: {value if value else '(no answer)'}")

        response = HttpResponse("\n".join(lines), content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_responses.txt"'

    else:  # pdf
        from xml.sax.saxutils import escape as xml_escape

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
            title=form.title or "Feedback responses",
        )
        cell = ParagraphStyle("cell", fontSize=7.5, leading=10, wordWrap="CJK")
        head_cell = ParagraphStyle("head", fontSize=7.5, leading=10, textColor=colors.white)
        heading = ParagraphStyle("heading", fontSize=13, leading=16, textColor=colors.HexColor("#2d5016"))
        sub = ParagraphStyle("sub", fontSize=8, leading=11, textColor=colors.HexColor("#555555"))

        story = [
            Paragraph(xml_escape(form.title or "Feedback responses"), heading),
            Paragraph(
                xml_escape(
                    f"Generated {timezone.localtime().strftime('%Y-%m-%d %H:%M')} &middot; "
                    f"{len(rows)} response(s)"
                ),
                sub,
            ),
            Spacer(1, 6 * mm),
        ]

        if legend:
            story.append(Paragraph("Questions", head_cell))
            story.append(Spacer(1, 2 * mm))
            for line in legend:
                story.append(Paragraph(xml_escape(line), sub))
            story.append(Spacer(1, 5 * mm))

        if not rows:
            story.append(Paragraph("No responses have been submitted yet.", sub))
        else:
            data = [[Paragraph(xml_escape(h), head_cell) for h in header]]
            for row in rows:
                data.append([Paragraph(xml_escape(str(c)), cell) for c in row])

            table = Table(data, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5016")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f2")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(table)

        doc.build(story)
        response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_responses.pdf"'

    # Freeform text is caller-controlled: never let a browser sniff it.
    response["X-Content-Type-Options"] = "nosniff"
    _audit(
        request,
        table="feedback_form",
        record_id=form.form_id_PK,
        action="FEEDBACK_EXPORTED",
        actor=_officer_for_request(request),
        new={"format": fmt, "rows": len(rows)},
        notes=f"Exported '{form.title}' as {fmt.upper()} ({len(rows)} response(s))",
    )
    return response
