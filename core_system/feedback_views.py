"""Officer + member feedback forms.

A Superadmin-authored instrument (multiple choice / Likert / freeform text)
that renders as one shared card on the President, Treasurer, Auditor and
Member dashboards. Officers and members submit once per form; the
Superadmin reviews and exports.

Survey kinds: ``normal`` is the one-shot prompt; ``pre``/``post`` surveys
are persistent (pinned toast, no dismiss, logout blocked until answered)
and a ``post`` only unlocks once its paired ``pre`` form is completed.

Design notes:

* Officer identity always comes from the validated ``AccessSession``, never
  from a submitted field. ``_officer_for_request`` is the only place an
  officer is resolved.
* Every answer is re-validated against the *question's own definition* on the
  server, and every question is looked up scoped to the posted form, so a
  crafted submission cannot attach answers to questions it does not own.
* Officers may read only their own response. Listings and exports are
  Superadmin-only and are audited.
* CSV/XLSX export guards against spreadsheet formula injection: a cell
  beginning with ``= + - @`` (or a tab/CR) is prefixed with a single quote so
  Excel and Sheets treat it as text rather than executing it.
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

# Dashboards that host the shared card. Members sign in via the same
# OfficerUser session, so no schema change is needed for their responses.
DASHBOARD_ROLES = ("President", "Treasurer", "Auditor", "Member")

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


# ---------------------------------------------------------------------------
# Question titles + per-question totals (shared by page and all exports)
# ---------------------------------------------------------------------------

def _question_full_title(question: FeedbackQuestion, index: int) -> str:
    """Clear, self-contained header: ``Q1: <prompt> (Scale 1-5)``.

    Likert always carries its author-specified scale so a bare ``4`` in a
    cell is unambiguous. Custom anchor labels are appended when present,
    e.g. ``Q1: Rate us (Scale 1-5) [1=Poor, 5=Excellent]``.
    """
    base = f"Q{index}: {question.prompt}"
    if question.qtype == "likert":
        base += f" (Scale {question.scale_min}-{question.scale_max})"
        try:
            labels = question.likert_labels() or {}
        except Exception:
            labels = {}
        custom = {v: lbl for v, lbl in labels.items() if str(lbl) != str(v)}
        if custom:
            mapping = ", ".join(f"{v}={custom[v]}" for v in sorted(custom))
            base += f" [{mapping}]"
    return base


def _question_scale_text(question: FeedbackQuestion) -> str:
    if question.qtype == "likert":
        return f"Scale {question.scale_min}-{question.scale_max}"
    if question.qtype == "mc":
        n = len(question.option_labels())
        return f"{n} choice(s)" if n else "Multiple choice"
    return "Free text"


def _pct(part: int, whole: int) -> float:
    """Percentage helper: 0.0 when the denominator is 0 (no audience/answers)."""
    try:
        return round(part / whole * 100, 1) if whole else 0.0
    except (TypeError, ValueError):
        return 0.0


def _expected_audience(form: FeedbackForm) -> tuple[int, dict]:
    """Eligible audience size derived from ``show_on_roles``.

    Counts active ``OfficerUser`` rows whose role is targeted by the form.
    Checking Member therefore yields a much larger expected number than an
    officer-only form — exactly the behaviour the summary relies on.
    Returns ``(expected_total, {role: count})`` preserving the form's role
    order. A form targeting nobody has an expected audience of 0.
    """
    roles = [r for r in (form.show_on_roles or []) if r in FEEDBACK_ROLES]
    if not roles:
        return 0, {}
    counts: dict[str, int] = {r: 0 for r in roles}
    try:
        for row in (
            OfficerUser.objects
            .filter(role__in=roles, account_status__iexact="Active")
            .values("role")
            .annotate(c=Count("*"))
        ):
            if row["role"] in counts:
                counts[row["role"]] = row["c"]
    except Exception:
        logger.exception("Feedback expected-audience count failed")
    return sum(counts.values()), counts


def _form_coverage(form: FeedbackForm, responses: list[FeedbackResponse]) -> dict:
    """Uniform coverage block shared by the page and every export format.

    ``responded`` counts stored responses; ``expected`` is the eligible
    audience from :func:`_expected_audience`; ``rate`` is the response rate.
    ``role_rows`` breaks the same numbers down per targeted role so a
    Member-targeted form explains its large denominator.
    """
    expected_total, expected_by_role = _expected_audience(form)
    responded = len(responses)
    rate = _pct(responded, expected_total)
    responded_by_role: dict[str, int] = {}
    for r in responses:
        try:
            role = (r.officer_id_FK.role or "Unknown") if r.officer_id_FK_id else "Unknown"
        except Exception:
            role = "Unknown"
        responded_by_role[role] = responded_by_role.get(role, 0) + 1
    role_rows = []
    for role in (form.show_on_roles or []):
        exp = int(expected_by_role.get(role, 0))
        resp = int(responded_by_role.get(role, 0))
        role_rows.append({
            "role": role,
            "expected": exp,
            "responded": resp,
            "remaining": max(exp - resp, 0),
            "rate": _pct(resp, exp),
        })
    return {
        "roles": list(form.show_on_roles or []),
        "expected": expected_total,
        "responded": responded,
        "remaining": max(expected_total - responded, 0),
        "rate": rate,
        "rate_line": f"{responded}/{expected_total} ({rate}%)" if expected_total else f"{responded}/0 (n/a — no target roles)",
        "expected_by_role": expected_by_role,
        "responded_by_role": responded_by_role,
        "role_rows": role_rows,
    }


def _build_question_summaries(
    questions: list[FeedbackQuestion],
    responses: list[FeedbackResponse],
    expected_total: int = 0,
) -> list[dict]:
    """Totalize answers per question for the page and every export format.

    Uniform output contract (all formats render the same numbers):

    * Headline: ``"<answered> of <respondents> respondents answered
      (<pct_resp>%) | <answered> of <expected> expected (<pct_exp>%)"``
      plus the Likert average when applicable.
    * Each choice: ``"<letter>. <label>: <count> (<pct_a>% of answered,
      <count>/<expected> expected = <pct_e>% of expected)"`` — e.g.
      ``"A. Yes: 10 (100.0% of answered, 10/10 expected = 100.0% of
      expected)"``. When ``expected`` is 0 the expected clause is omitted.
    * ``pct`` is kept as an alias of ``pct_answered`` for backwards
      compatibility; new keys are ``pct_answered``, ``pct_expected``,
      ``frac_answered`` (``"count/answered"``) and ``frac_expected``
      (``"count/expected"``).
    * ``interpretation`` is one deterministic plain-language sentence stating
      the result (top answer, votes, share, Likert average, coverage vs the
      expected audience) — the same numbers always read the same way so the
      sentence can be checked against the table (see :func:`_interpret_summary`).
    """
    total = len(responses)
    expected_total = int(expected_total or 0)
    maps: list[dict] = []
    for r in responses:
        try:
            maps.append(r.answer_map())
        except Exception:
            maps.append({})

    def _headline(answered: int, extra: str = "") -> str:
        pct_resp = _pct(answered, total)
        if expected_total:
            pct_exp = _pct(answered, expected_total)
            base = (
                f"{answered} of {total} respondents answered ({pct_resp}%) | "
                f"{answered} of {expected_total} expected ({pct_exp}%)"
            )
        else:
            base = f"{answered} of {total} answered ({pct_resp}%)"
        return f"{base}{extra}" if extra else base

    def _choice_line(letter: str, label: str, cnt: int, answered: int) -> tuple[str, float, float]:
        pct_a = _pct(cnt, answered)
        pct_e = _pct(cnt, expected_total)
        prefix = f"{letter}. " if letter else ""
        if expected_total:
            line = (
                f"{prefix}{label}: {cnt} "
                f"({pct_a}% of answered, {cnt}/{expected_total} expected = {pct_e}% of expected)"
            )
        else:
            frac = f"{cnt}/{answered}" if answered else f"{cnt}/0"
            line = f"{prefix}{label}: {cnt} ({pct_a}% of answered, {frac} answered)"
        return line, pct_a, pct_e

    out: list[dict] = []
    for idx, q in enumerate(questions, 1):
        qid = q.question_id_PK
        full_title = _question_full_title(q, idx)
        scale_text = _question_scale_text(q)
        if q.qtype == "likert":
            counts = {v: 0 for v in range(q.scale_min, q.scale_max + 1)}
            answered = 0
            total_val = 0
            for m in maps:
                a = m.get(qid)
                if a is None or a.value_int is None:
                    continue
                try:
                    v = int(a.value_int)
                except (TypeError, ValueError):
                    continue
                if q.scale_min <= v <= q.scale_max:
                    counts[v] += 1
                    answered += 1
                    total_val += v
            avg = round(total_val / answered, 2) if answered else None
            try:
                labels = q.likert_labels() or {}
            except Exception:
                labels = {}
            breakdown = []
            for v in range(q.scale_min, q.scale_max + 1):
                cnt = counts.get(v, 0)
                lbl = str(labels.get(v, v))
                label = f"{v} ({lbl})" if lbl != str(v) else f"{v}"
                line, pct_a, pct_e = _choice_line("", label, cnt, answered)
                breakdown.append({
                    "value": v, "label": lbl, "display": label,
                    "count": cnt, "pct": pct_a,
                    "pct_answered": pct_a, "pct_expected": pct_e,
                    "frac_answered": f"{cnt}/{answered}" if answered else f"{cnt}/0",
                    "frac_expected": f"{cnt}/{expected_total}",
                    "line": line,
                })
            extra = (
                f" - average {avg} out of scale {q.scale_max} (scale {q.scale_min}-{q.scale_max})"
                if answered
                else f" (scale {q.scale_min}-{q.scale_max})"
            )
            headline = _headline(answered, extra)
            out.append({
                "code": f"Q{idx}", "prompt": q.prompt, "qtype": q.qtype,
                "full_title": full_title, "scale_text": scale_text,
                "scale_min": q.scale_min, "scale_max": q.scale_max,
                "total": total, "answered": answered, "average": avg,
                "expected": expected_total,
                "pct_answered_of_respondents": _pct(answered, total),
                "pct_answered_of_expected": _pct(answered, expected_total),
                "breakdown": breakdown, "headline": headline,
                "interpretation": _interpret_summary(
                    f"Q{idx}", q.prompt, q.qtype, answered, total,
                    expected_total, breakdown, avg, idx,
                    scale_min=q.scale_min, scale_max=q.scale_max,
                ),
            })
        elif q.qtype == "mc":
            opts = q.option_labels()
            counts = {o: 0 for o in opts}
            answered = 0
            for m in maps:
                a = m.get(qid)
                if a is None or not (a.value_list or []):
                    continue
                answered += 1
                for v in (a.value_list or []):
                    key = str(v)
                    if key in counts:
                        counts[key] += 1
                    else:
                        counts[key] = counts.get(key, 0) + 1
            ordered = list(opts) + [k for k in counts if k not in opts]
            breakdown = []
            for i, o in enumerate(ordered):
                cnt = counts.get(o, 0)
                letter = chr(ord("A") + i) if i < 26 else str(i + 1)
                line, pct_a, pct_e = _choice_line(letter, o, cnt, answered)
                breakdown.append({
                    "choice": letter, "label": o, "count": cnt, "pct": pct_a,
                    "pct_answered": pct_a, "pct_expected": pct_e,
                    "frac_answered": f"{cnt}/{answered}" if answered else f"{cnt}/0",
                    "frac_expected": f"{cnt}/{expected_total}",
                    "line": line,
                })
            headline = _headline(answered)
            out.append({
                "code": f"Q{idx}", "prompt": q.prompt, "qtype": q.qtype,
                "full_title": full_title, "scale_text": scale_text,
                "total": total, "answered": answered, "average": None,
                "expected": expected_total,
                "pct_answered_of_respondents": _pct(answered, total),
                "pct_answered_of_expected": _pct(answered, expected_total),
                "breakdown": breakdown, "headline": headline,
                "interpretation": _interpret_summary(
                    f"Q{idx}", q.prompt, q.qtype, answered, total,
                    expected_total, breakdown, None, idx,
                ),
            })
        else:  # freeform text
            answered = sum(
                1 for m in maps
                if m.get(qid) is not None and str(m[qid].value_text or "").strip()
            )
            headline = _headline(answered)
            out.append({
                "code": f"Q{idx}", "prompt": q.prompt, "qtype": q.qtype,
                "full_title": full_title, "scale_text": scale_text,
                "total": total, "answered": answered, "average": None,
                "expected": expected_total,
                "pct_answered_of_respondents": _pct(answered, total),
                "pct_answered_of_expected": _pct(answered, expected_total),
                "breakdown": [], "headline": headline,
                "interpretation": _interpret_summary(
                    f"Q{idx}", q.prompt, q.qtype, answered, total,
                    expected_total, [], None, idx,
                ),
            })
    return out


def _pick(variants: list[str], seed: int) -> str:
    return variants[seed % len(variants)] if variants else ""


def _join_names(names: list[str]) -> str:
    """'a, b and c' joining for tied options/codes (already quoted if needed)."""
    names = [n for n in (names or []) if n]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _nv(n: Any, noun: str) -> str:
    """Count + noun with pluralization ('1 vote' / '3 votes')."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _interpret_summary(
    code: str, prompt: Any, qtype: str, answered: int, total: int,
    expected: int, breakdown: list[dict], average: float | None, idx: int,
    scale_min: int = 1, scale_max: int = 5,
) -> str:
    """One plain-language sentence stating the result factually.

    Deliberately deterministic (no rotating synonyms): the same numbers
    always read the same way, so the sentence can be checked against the
    table above it. Every figure in the sentence also appears in the
    headline/breakdown — no new claims, no metaphors.
    """
    total = int(total or 0)
    answered = int(answered or 0)
    expected = int(expected or 0)

    def _coverage_tail() -> str:
        if not expected:
            return ""
        return (
            f" Coverage: {answered} of {expected} targeted "
            f"officers/members answered ({_pct(answered, expected)}%)."
        )

    if total <= 0:
        return f"{code}: no responses yet — nothing to interpret."
    if answered <= 0:
        return f"{code}: all {total} respondents skipped this question."

    if qtype == "likert":
        counts = [int(b.get("count", 0) or 0) for b in breakdown]
        maxcnt = max(counts) if counts else 0
        leaders = [b for b in breakdown if int(b.get("count", 0) or 0) == maxcnt]
        share = _pct(maxcnt, answered)
        avg = average if average is not None else 0

        def _vname(b: dict) -> str:
            lbl = str(b.get("label", ""))
            v = b.get("value", "")
            return f"{v} \u201c{lbl}\u201d" if lbl != str(v) else str(v)

        scale = f"the {scale_min}\u2013{scale_max} scale"
        if len(leaders) > 1:
            peak = _join_names([_vname(b) for b in leaders])
            return (
                f"{code}: tied — {peak} each got {_nv(maxcnt, 'vote')} "
                f"({share}% of the {answered} answers). "
                f"Average is {avg} on {scale}."
            ) + _coverage_tail()
        vtxt = _vname(leaders[0]) if leaders else ""
        return (
            f"{code}: most chosen is {vtxt} with {maxcnt} of {answered} "
            f"answers ({share}%). Average is {avg} on {scale}."
        ) + _coverage_tail()

    if qtype == "mc" and breakdown:
        maxcnt = max(int(b.get("count", 0) or 0) for b in breakdown)
        leaders = [b for b in breakdown if int(b.get("count", 0) or 0) == maxcnt]
        share = _pct(maxcnt, answered)
        if len(leaders) > 1:
            # Tied: naming one option the winner would be arbitrary.
            names = _join_names([f"\u201c{str(b.get('label', ''))}\u201d" for b in leaders])
            return (
                f"{code}: tied — {names} each got {_nv(maxcnt, 'vote')} "
                f"({share}% of the {answered} answers)."
            ) + _coverage_tail()
        top = leaders[0]
        label = str(top.get("label", ""))
        if share >= 100:
            main = (
                f"{code}: everyone who answered chose \u201c{label}\u201d "
                f"({maxcnt} of {answered})."
            )
        else:
            main = (
                f"{code}: \u201c{label}\u201d leads with {maxcnt} of {answered} "
                f"answers ({share}%)."
            )
        runner_rows = [
            b for b in breakdown
            if int(b.get("count", 0) or 0) < maxcnt
        ]
        runner_cnt = max(
            [int(b.get("count", 0) or 0) for b in runner_rows] or [0]
        )
        if runner_cnt > 0:
            rlabel = next(
                (
                    str(b.get("label", ""))
                    for b in runner_rows
                    if int(b.get("count", 0) or 0) == runner_cnt
                ),
                "",
            )
            rshare = _pct(runner_cnt, answered)
            main += f" Closest challenger \u201c{rlabel}\u201d trails with {runner_cnt} ({rshare}%)."
        return main + _coverage_tail()

    # Freeform text (or an MC with no options recorded): read the turnout.
    return (
        f"{code}: {answered} of {total} respondents left a written comment — "
        f"read the entries for the substance."
    ) + _coverage_tail()


def _overall_interpretation(form: FeedbackForm, coverage: dict, summaries: list[dict]) -> str:
    """Two-to-three-sentence read of the whole form: turnout verdict first,
    then where agreement is strongest / where answers ran thin, then what is
    still outstanding. Openings rotate by form so different surveys do not
    open with the same line."""
    resp = int(coverage.get("responded", 0) or 0)
    exp = int(coverage.get("expected", 0) or 0)
    rate = float(coverage.get("rate", 0) or 0)
    remaining = int(coverage.get("remaining", 0) or 0)
    try:
        seed = int(form.form_id_PK or 0)
    except Exception:
        seed = 0

    if exp <= 0:
        head = _pick([
            f"This form targets no roles, so there is no expected audience — {resp} response(s) stand alone.",
            f"With no target roles there is no turnout denominator; the {resp} response(s) below are the whole picture.",
        ], seed)
    elif resp <= 0:
        head = _pick([
            f"Nobody has responded yet out of {exp} expected — the tables below are empty until submissions arrive.",
            f"Zero responses so far against an expected {exp}; check that the card is visible to its target roles.",
        ], seed)
    elif rate >= 80:
        head = _pick([
            f"Turnout is excellent — {resp} of {exp} expected responded ({rate}%), so these results carry real weight.",
            f"With {rate}% of the expected audience responding ({resp}/{exp}), this report reads as representative.",
            f"Strong participation ({resp}/{exp}, {rate}%) gives these findings solid footing.",
        ], seed)
    elif rate >= 50:
        head = _pick([
            f"A solid {rate}% responded ({resp}/{exp}) — enough to trust the broad strokes, with some caution on close splits.",
            f"Turnout reached {resp} of {exp} expected ({rate}%), so majorities here are meaningful even if narrow ones are not.",
        ], seed)
    elif rate >= 30:
        head = _pick([
            f"Turnout is moderate at {rate}% ({resp}/{exp}); treat clear majorities as signal and close calls as tentative.",
            f"With {resp}/{exp} responding ({rate}%), headline patterns are usable but small gaps between options may just be noise.",
        ], seed)
    else:
        head = _pick([
            f"Turnout is low — {resp} of {exp} expected ({rate}%) — so read every share below as indicative, not conclusive.",
            f"Only {rate}% of the expected audience responded ({resp}/{exp}); the percentages describe respondents, not the whole group.",
            f"A thin {resp}/{exp} turnout ({rate}%) means these numbers sketch early sentiment rather than a verdict.",
        ], seed)

    parts = [head]
    if summaries and resp > 0:
        # Strongest agreement: highest top-choice share among answered
        # MC/Likert. Joint leaders inside one question share the max, so the
        # question-level share is what ranks — and tied questions are named
        # together instead of crowning whichever came first.
        best_share = -1.0
        best_hits: list[tuple[str, str]] = []
        worst_answered = None
        for s in summaries:
            a = int(s.get("answered", 0) or 0)
            if worst_answered is None or a < int(worst_answered.get("answered", 0) or 0):
                worst_answered = s
            bd = s.get("breakdown") or []
            if s.get("qtype") in ("mc", "likert") and a > 0 and bd:
                peak = max(float(b.get("pct_answered", b.get("pct", 0)) or 0) for b in bd)
                tops = [b for b in bd
                        if abs(float(b.get("pct_answered", b.get("pct", 0)) or 0) - peak) < 1e-9]
                label = _join_names([
                    (f"{b.get('value', '')} \u201c{b.get('label', '')}\u201d"
                     if s.get("qtype") == "likert" and str(b.get("label", "")) != str(b.get("value", ""))
                     else str(b.get("label", "")))
                    for b in tops
                ])
                if peak > best_share + 1e-9:
                    best_share = peak
                    best_hits = [(s.get("code", ""), label)]
                elif abs(peak - best_share) < 1e-9:
                    best_hits.append((s.get("code", ""), label))
        if best_hits and len(best_hits) > 1:
            codes = _join_names([c for c, _ in best_hits])
            if best_share >= 60:
                parts.append(_pick([
                    f"Strongest agreement is shared by {codes} ({best_share}% of answered).",
                    f"{codes} tie for the clearest consensus at {best_share}%.",
                ], seed + 1))
            else:
                parts.append(_pick([
                    f"No question reaches a firm consensus — {codes} jointly top out at {best_share}%.",
                    f"Agreement is soft everywhere; {codes} share the highest mark at {best_share}%.",
                ], seed + 1))
        elif best_hits and best_share >= 60:
            code, label = best_hits[0]
            parts.append(_pick([
                f"Strongest agreement is on {code} (\u201c{label}\u201d, {best_share}% of answered).",
                f"{code} carries the clearest consensus at {best_share}% for \u201c{label}\u201d.",
            ], seed + 1))
        elif best_hits:
            code, label = best_hits[0]
            parts.append(_pick([
                f"No question reaches a firm consensus — {code} tops out at {best_share}% for \u201c{label}\u201d.",
                f"Agreement is soft everywhere; the highest share is {code} at {best_share}% (\u201c{label}\u201d).",
            ], seed + 1))
        if worst_answered is not None and int(worst_answered.get("answered", 0) or 0) < resp:
            wa = int(worst_answered.get("answered", 0) or 0)
            parts.append(_pick([
                f"{worst_answered.get('code', 'One question')} was the most skipped ({wa}/{resp} answered).",
                f"The thinnest item is {worst_answered.get('code', 'one question')} with {wa} of {resp} answering.",
            ], seed + 2))
    if exp > 0 and resp > 0:
        if remaining > 0:
            parts.append(_pick([
                f"Still outstanding: {remaining} of {exp} have yet to respond.",
                f"{remaining} expected respondents have not answered yet.",
            ], seed + 3))
        else:
            parts.append(_pick([
                "Full house — everyone expected has responded.",
                "Nobody is outstanding; the whole expected audience has answered.",
            ], seed + 3))
    return " ".join(parts)


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
    """The form this officer should be answering, if any.

    Skips forms already answered. A Post-Survey additionally requires its
    paired Pre-Survey to be completed first, so the pairing order holds.
    """
    forms = FeedbackForm.objects.filter(
        is_active=True, is_archived=False, is_open=True
    ).prefetch_related("questions")
    answered_ids = set(
        FeedbackResponse.objects.filter(officer_id_FK=officer).values_list(
            "form_id_FK_id", flat=True
        )
    )
    for form in forms:
        if form.form_id_PK in answered_ids:
            continue
        if not form.applies_to(officer.role):
            continue
        if form.kind == "post":
            pre_id = form.paired_pre_FK_id
            if not pre_id or pre_id not in answered_ids:
                continue
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


# Fields that define a question's identity for change detection. Excludes
# ``display_order`` (a pure reorder keeps every answer valid).
_QUESTION_DEF_FIELDS = (
    "prompt", "qtype", "options", "scale_min", "scale_max",
    "min_choices", "max_choices", "is_required", "help_text",
)


def _normalize_question_defs(questions_in: Any) -> list[dict]:
    """Clean raw authoring payload into canonical question definitions.

    Applies exactly the same cleaning the save path uses at creation, so a
    round-tripped payload compares equal to what is stored. Items with an
    empty prompt are skipped (they are never created).
    """
    defs: list[dict] = []
    for item in questions_in if isinstance(questions_in, list) else []:
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

        defs.append({
            "prompt": prompt,
            "qtype": qtype,
            "options": options,
            "scale_min": scale_min,
            "scale_max": scale_max,
            "min_choices": min_choices,
            "max_choices": max_choices,
            "is_required": str(item.get("is_required", "on")).lower() not in ("off", "false", "0", ""),
            "help_text": _clean_text(item.get("help_text"))[:300],
        })
    return defs


def _existing_question_defs(form: FeedbackForm) -> list[dict]:
    """Canonical definitions of the stored questions, in display order."""
    defs: list[dict] = []
    for q in form.questions.all().order_by("display_order", "question_id_PK"):
        defs.append({
            "prompt": q.prompt or "",
            "qtype": q.qtype or "mc",
            "options": [str(o) for o in (q.options or [])],
            "scale_min": int(q.scale_min or 1),
            "scale_max": int(q.scale_max or 5),
            "min_choices": int(q.min_choices or 1),
            "max_choices": int(q.max_choices or 1),
            "is_required": bool(q.is_required),
            "help_text": q.help_text or "",
        })
    return defs


def _question_defs_equal(a: list[dict], b: list[dict]) -> bool:
    """True when two definition lists match item-for-item (order matters)."""
    if len(a) != len(b):
        return False
    return all(
        all(x.get(f) == y.get(f) for f in _QUESTION_DEF_FIELDS)
        for x, y in zip(a, b)
    )


def _question_defs_same_set(a: list[dict], b: list[dict]) -> bool:
    """True when the multisets match (a pure reorder keeps answers valid)."""
    if len(a) != len(b):
        return False
    def _key(d: dict) -> str:
        return json.dumps({f: d.get(f) for f in _QUESTION_DEF_FIELDS}, sort_keys=True)
    from collections import Counter
    return Counter(_key(d) for d in a) == Counter(_key(d) for d in b)


def _bulk_create_questions(form: FeedbackForm, defs: list[dict]) -> int:
    """Create questions from canonical defs. Returns the number created."""
    saved = 0
    for order, d in enumerate(defs):
        FeedbackQuestion.objects.create(
            form_id_FK=form,
            prompt=d["prompt"],
            qtype=d["qtype"],
            options=list(d["options"]),
            scale_min=d["scale_min"],
            scale_max=d["scale_max"],
            min_choices=d["min_choices"],
            max_choices=d["max_choices"],
            is_required=d["is_required"],
            display_order=order,
            help_text=d["help_text"],
        )
        saved += 1
    return saved


def _apply_question_order(form: FeedbackForm, incoming_defs: list[dict]) -> None:
    """Persist a pure reorder in place, keeping every PK (and answer) intact."""
    def _key(d: dict) -> str:
        return json.dumps({f: d.get(f) for f in _QUESTION_DEF_FIELDS}, sort_keys=True)
    from collections import defaultdict, deque
    by_key: dict[str, deque] = defaultdict(deque)
    for q in form.questions.all().order_by("display_order", "question_id_PK"):
        by_key[_key({
            "prompt": q.prompt or "", "qtype": q.qtype or "mc",
            "options": [str(o) for o in (q.options or [])],
            "scale_min": int(q.scale_min or 1), "scale_max": int(q.scale_max or 5),
            "min_choices": int(q.min_choices or 1), "max_choices": int(q.max_choices or 1),
            "is_required": bool(q.is_required), "help_text": q.help_text or "",
        })].append(q)
    for order, d in enumerate(incoming_defs):
        q = by_key[_key(d)].popleft()
        if q.display_order != order:
            q.display_order = order
            q.save(update_fields=["display_order"])


def _purge_answerless_responses(form: FeedbackForm) -> int:
    """Delete responses that hold zero answers (legacy wholesale-replace orphans).

    An answerless row carries no information yet counts as "responded" and —
    via the one-response-per-officer rule — permanently blocks that officer
    from answering. Returns the number removed.
    """
    shell_ids = list(
        form.responses.annotate(_n=Count("answers")).filter(_n=0)
        .values_list("response_id_PK", flat=True)
    )
    if not shell_ids:
        return 0
    FeedbackResponse.objects.filter(response_id_PK__in=shell_ids).delete()
    return len(shell_ids)


# ---------------------------------------------------------------------------
# Officer-facing: the shared card
# ---------------------------------------------------------------------------

@require_GET
def feedback_card(request: HttpRequest):
    """Server-rendered feedback modal + prompt toast for the signed-in viewer.

    Returns an empty body in every case where nobody should be prompted:
    no session, no form published to their role, the form already answered,
    or (for a Post-Survey) its paired Pre-Survey not yet completed. Normal
    surveys are one-shot; Pre/Post surveys are persistent (pinned toast, no
    dismiss, logout blocked until answered).
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

    # One-shot prompt: an existing response means this viewer is done.
    already_answered = FeedbackResponse.objects.filter(
        form_id_FK=form, officer_id_FK=officer
    ).exists()
    if already_answered:
        return HttpResponse("", content_type="text/html; charset=utf-8")

    questions = list(form.questions.all())
    if not questions:
        return HttpResponse("", content_type="text/html; charset=utf-8")

    first_name = (officer.full_name or officer.username or "officer").split(" ")[0]

    kind = form.kind or "normal"
    html = render(
        request,
        "website/shared/feedback_card_content.html",
        {
            "fb_form": form,
            "fb_officer_first": first_name,
            "fb_questions": questions,
            "fb_question_count": len(questions),
            "fb_max_text": FEEDBACK_TEXT_MAX,
            "fb_kind": kind,
            "fb_persistent": kind in ("pre", "post"),
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
            # DISTINCT is required: joining questions × responses multiplies
            # rows, so plain counts inflate (2 questions × 2 responses
            # would read as "4 questions · 4 responses").
            n_questions=Count("questions", distinct=True),
            n_responses=Count("responses", distinct=True),
        )
    )
    selected_id = request.GET.get("form")
    selected = None
    if selected_id:
        selected = next((f for f in forms if str(f.form_id_PK) == str(selected_id)), None)

    selected_responses = []
    response_rows = []
    selected_questions: list[FeedbackQuestion] = []
    question_summaries: list[dict] = []
    coverage: dict | None = None
    overall_interpretation = ""
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
        coverage = _form_coverage(selected, selected_responses)
        question_summaries = _build_question_summaries(
            selected_questions, selected_responses, coverage["expected"]
        )
        overall_interpretation = _overall_interpretation(
            selected, coverage, question_summaries
        )

    pre_forms = [
        {"id": f.form_id_PK, "title": f.title}
        for f in forms
        if (f.kind or "normal") == "pre"
        and (selected is None or f.form_id_PK != selected.form_id_PK)
    ]
    selected_kind = (selected.kind if selected is not None else "normal") or "normal"
    return render(request, "website/Superadmin/feedback_admin.html", {
        "fb_forms": forms,
        "fb_selected": selected,
        "fb_selected_questions": list(selected.questions.all()) if selected is not None else [],
        "fb_selected_responses": selected_responses,
        "fb_response_rows": response_rows,
        "fb_question_summaries": question_summaries,
        "fb_coverage": coverage,
        "fb_overall_interpretation": overall_interpretation,
        "fb_roles": FEEDBACK_ROLES,
        "fb_kind_choices": FeedbackForm._meta.get_field("kind").choices,
        "fb_pre_forms": pre_forms,
        # Post-Survey requires an existing Pre-Survey to pair with. Disable the
        # Post option (and hide the pairing dropdown) until one exists — unless
        # the form being edited is already a Post-Survey.
        "fb_has_pre": bool(pre_forms),
        "fb_post_disabled": not pre_forms and selected_kind != "post",
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

    kind = str(body.get("kind") or "normal").strip().lower()
    if kind not in ("normal", "pre", "post"):
        return JsonResponse({"ok": False, "error": "Unknown survey type."}, status=400)

    paired_pre_id = body.get("paired_pre_id") or body.get("paired_pre")
    paired_pre = None
    if kind == "post":
        if not paired_pre_id:
            return JsonResponse(
                {"ok": False, "error": "A Post-Survey must be paired with a Pre-Survey."},
                status=400,
            )
        paired_pre = FeedbackForm.objects.filter(form_id_PK=paired_pre_id).first()
        if paired_pre is None or paired_pre.kind != "pre":
            return JsonResponse(
                {"ok": False, "error": "Paired form must be an existing Pre-Survey."},
                status=400,
            )

    form_id = body.get("form_id")
    form = None
    if form_id:
        form = FeedbackForm.objects.filter(form_id_PK=form_id).first()
        if form is None:
            return JsonResponse({"ok": False, "error": "Unknown form."}, status=404)

    if kind == "post" and form is not None and paired_pre is not None:
        if str(paired_pre.form_id_PK) == str(form.form_id_PK):
            return JsonResponse(
                {"ok": False, "error": "A Post-Survey cannot be paired with itself."},
                status=400,
            )

    created = form is None
    if form is None:
        form = FeedbackForm(created_by_id_FK=officer)
    form.title = title
    form.section_title = section_title
    form.description = description
    form.show_on_roles = valid_roles
    form.kind = kind
    form.paired_pre_FK = paired_pre if kind == "post" else None
    form.is_active = str(body.get("is_active", "on")).lower() not in ("off", "false", "0", "")
    form.is_open = str(body.get("is_open", "on")).lower() not in ("off", "false", "0", "")
    form.save()

    # Change-aware question write: stored answers are keyed to question PKs,
    # so a blind wholesale replace orphans every response (the old code did
    # exactly that on EVERY save — even a title-only edit wiped all answers
    # while the empty response rows kept counting as "responded" and blocked
    # re-answering). Instead:
    #   * identical set  -> questions untouched, all responses preserved;
    #   * pure reorder   -> display_order updated in place, responses kept;
    #   * real change    -> fresh round: purge responses, recreate questions.
    incoming_defs = _normalize_question_defs(questions_in)
    existing_defs = [] if created else _existing_question_defs(form)

    reset_responses = 0
    purged_shells = 0
    questions_changed = False
    if created:
        saved = _bulk_create_questions(form, incoming_defs)
    elif _question_defs_equal(incoming_defs, existing_defs):
        saved = len(existing_defs)
        purged_shells = _purge_answerless_responses(form)
    elif _question_defs_same_set(incoming_defs, existing_defs):
        _apply_question_order(form, incoming_defs)
        saved = len(existing_defs)
        purged_shells = _purge_answerless_responses(form)
    else:
        questions_changed = True
        reset_responses = form.responses.count()
        if reset_responses:
            form.responses.all().delete()
        form.questions.all().delete()
        saved = _bulk_create_questions(form, incoming_defs)
        # Belt-and-braces: the deletes above cascade, but never leave a shell.
        purged_shells = _purge_answerless_responses(form)
        _audit(
            request,
            table="feedback_form",
            record_id=form.form_id_PK,
            action="FEEDBACK_FORM_RESET",
            actor=officer,
            new={"title": title, "questions": saved, "responses_reset": reset_responses},
            notes=(
                f"Questions on '{title}' changed: reset {reset_responses} "
                f"response(s) so everyone answers the new round"
            ),
        )

    _audit(
        request,
        table="feedback_form",
        record_id=form.form_id_PK,
        action="FEEDBACK_FORM_SAVED",
        actor=officer,
        new={"title": title, "questions": saved, "roles": valid_roles, "kind": kind,
             "questions_changed": questions_changed, "responses_reset": reset_responses,
             "shells_purged": purged_shells},
        notes=f"{'Created' if created else 'Updated'} feedback form '{title}'",
    )

    if questions_changed and reset_responses:
        message = (
            f"Questions changed: {reset_responses} prior response(s) were reset. "
            f"Form saved with {saved} question(s)."
        )
    elif purged_shells:
        message = (
            f"Feedback form saved with {saved} question(s). "
            f"Cleaned {purged_shells} empty response(s) so those officers can answer again."
        )
    else:
        message = f"Feedback form saved with {saved} question(s)."
    return JsonResponse({
        "ok": True,
        "form_id": form.form_id_PK,
        "created": created,
        "questions_changed": questions_changed,
        "reset_responses": reset_responses,
        "message": message,
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
    """Superadmin-only export of a form's responses as CSV, XLSX, PDF or TXT."""
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
    if fmt not in ("csv", "pdf", "txt", "xlsx"):
        return JsonResponse({"ok": False, "error": "Unsupported export format."}, status=400)

    questions, responses, header, rows = _export_matrix(form)

    # Full question text (with Likert scale) so a bare "4" is unambiguous,
    # plus the uniform coverage + per-question totals shared by every format:
    # COVER (meta + response rate) -> SUMMARY PER QUESTION (dual percentages)
    # -> QUESTIONS -> RESPONSES. Expected audience comes from show_on_roles.
    legend = [_question_full_title(q, i) for i, q in enumerate(questions, 1)]
    coverage = _form_coverage(form, responses)
    summaries = _build_question_summaries(questions, responses, coverage["expected"])
    overall_interpretation = _overall_interpretation(form, coverage, summaries)
    generated = timezone.localtime().strftime("%Y-%m-%d %H:%M")
    try:
        kind_label = form.get_kind_display()
    except Exception:
        kind_label = form.kind or "normal"
    status_bits = []
    status_bits.append("active" if form.is_active else "hidden")
    status_bits.append("open" if form.is_open else "closed")
    if form.is_archived:
        status_bits.append("archived")
    status_label = "/".join(status_bits)
    target_label = ", ".join(coverage["roles"]) if coverage["roles"] else "(no target roles)"
    cover_title = form.title or "Feedback responses"
    cover_lines = [
        f"Survey type: {kind_label}",
        f"Status: {status_label}",
        f"Target roles (Show on dashboards for): {target_label}",
        f"Expected respondents: {coverage['expected']}",
        f"Actual responses: {coverage['responded']}",
        f"Response rate: {coverage['rate']}% ({coverage['responded']}/{coverage['expected']})",
        f"Outstanding: {coverage['remaining']}",
    ]
    role_lines = [
        f"  {r['role']}: {r['responded']}/{r['expected']} ({r['rate']}%), outstanding {r['remaining']}"
        for r in coverage["role_rows"]
    ]

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (form.title or "feedback"))[:60]

    if fmt == "csv":
        buffer = io.StringIO()
        # QUOTE_ALL plus _csv_safe guards spreadsheet formula injection on
        # every cell, including officer-supplied free text.
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
        writer.writerow([_csv_safe(cover_title)])
        writer.writerow([_csv_safe(f"Generated {generated}")])
        writer.writerow([])
        writer.writerow([_csv_safe("COVER (response rate)")])
        for line in cover_lines:
            writer.writerow([_csv_safe(line)])
        writer.writerow([_csv_safe("Coverage by role (responded/expected, rate, outstanding)")])
        for line in role_lines or ["  (no target roles)"]:
            writer.writerow([_csv_safe(line)])
        writer.writerow([])
        writer.writerow([_csv_safe("OVERALL INTERPRETATION")])
        writer.writerow([_csv_safe(overall_interpretation or "(no responses yet)")])
        writer.writerow([])
        writer.writerow([_csv_safe("SUMMARY PER QUESTION (share of answered + coverage of expected)")])
        if summaries:
            for s in summaries:
                writer.writerow([_csv_safe(f"{s['full_title']} -- {s['headline']}")])
                for b in s["breakdown"]:
                    writer.writerow([_csv_safe(f"  {b['line']}")])
                if not s["breakdown"]:
                    writer.writerow([_csv_safe("  (free-text responses listed under RESPONSES)")])
                writer.writerow([_csv_safe(f"  Interpretation: {s['interpretation']}")])
        else:
            writer.writerow([_csv_safe("(none)")])
        writer.writerow([])
        writer.writerow([_csv_safe("QUESTIONS")])
        for line in legend or ["(none)"]:
            writer.writerow([_csv_safe(line)])
        writer.writerow([])
        writer.writerow([_csv_safe("RESPONSES")])
        writer.writerow([_csv_safe(h) for h in header])
        for row in rows:
            writer.writerow([_csv_safe(c) for c in row])

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_responses.csv"'

    elif fmt == "txt":
        lines = [
            cover_title,
            f"Generated {generated}",
            "",
            "COVER (response rate)",
        ]
        lines += [f"  {line}" for line in cover_lines]
        lines += ["", "  Coverage by role (responded/expected, rate, outstanding)"]
        lines += [f"  {line}" for line in role_lines] or ["    (no target roles)"]
        lines += ["", "OVERALL INTERPRETATION", ""]
        lines.append(f"  {overall_interpretation or '(no responses yet)'}")
        lines += ["", "SUMMARY PER QUESTION (share of answered + coverage of expected)", ""]
        if summaries:
            for s in summaries:
                lines.append(f"  {s['full_title']}")
                lines.append(f"    {s['headline']}")
                for b in s["breakdown"]:
                    lines.append(f"      {b['line']}")
                if not s["breakdown"]:
                    lines.append("      (free-text responses listed under RESPONSES)")
                lines.append(f"    Interpretation: {s['interpretation']}")
                lines.append("")
        else:
            lines.append("  (none)")
            lines.append("")
        lines += ["QUESTIONS", ""]
        lines += [f"  {line}" for line in legend] or ["  (none)"]
        lines += ["", "RESPONSES", ""]
        if not rows:
            lines.append("  (no responses yet)")
        for row in rows:
            lines.append("-" * 60)
            lines.append(f"  {row[0]}  ({row[1]})  -  {row[2]}")
            for i, (value, q) in enumerate(zip(row[3:], questions), 1):
                lines.append(f"    {_question_full_title(q, i)}: {value if value else '(no answer)'}")

        response = HttpResponse("\n".join(lines), content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_responses.txt"'

    elif fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Responses"
        generated = timezone.localtime().strftime("%Y-%m-%d %H:%M")

        title_font = Font(bold=True, size=14, color="2D5016")
        meta_font = Font(size=9, color="555555")
        head_font = Font(bold=True, size=10, color="FFFFFF")
        head_fill = PatternFill(start_color="2D5016", end_color="2D5016", fill_type="solid")
        even_fill = PatternFill(start_color="F4F7F2", end_color="F4F7F2", fill_type="solid")
        wrap = Alignment(vertical="top", wrap_text=True)
        center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)

        ws.merge_cells("A1:E1")
        ws["A1"] = cover_title
        ws["A1"].font = title_font
        ws.merge_cells("A2:E2")
        ws["A2"] = (
            f"Generated {generated}  -  {coverage['responded']}/{coverage['expected']} "
            f"responded ({coverage['rate']}%) | {kind_label} | Target: {target_label}"
        )
        ws["A2"].font = meta_font
        ws.merge_cells("A3:E3")
        ws["A3"] = "  |  ".join(cover_lines[3:])
        ws["A3"].font = meta_font

        header_row = 5
        for ci, h in enumerate(header, 1):
            cell = ws.cell(row=header_row, column=ci, value=_csv_safe(h))
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = center_wrap

        for ri, row in enumerate(rows, header_row + 1):
            for ci, value in enumerate(row, 1):
                cell = ws.cell(row=ri, column=ci, value=_csv_safe(value))
                cell.alignment = wrap
                if ri % 2 == 0:
                    cell.fill = even_fill

        if rows:
            ws.freeze_panes = ws.cell(row=header_row + 1, column=1).coordinate
            ws.auto_filter.ref = ws.dimensions
        else:
            ws.cell(row=header_row + 1, column=1, value="No responses have been submitted yet.").font = meta_font

        # Legend + totals below the table so the question text travels with the file.
        legend_start = header_row + len(rows) + 2
        ws.cell(row=legend_start, column=1, value="Questions (full text + scale)").font = Font(bold=True, size=11, color="2D5016")
        if legend:
            for i, line in enumerate(legend, 1):
                ws.cell(row=legend_start + i, column=1, value=_csv_safe(line)).alignment = wrap
        else:
            ws.cell(row=legend_start + 1, column=1, value="(none)").font = meta_font

        summary_start = legend_start + len(legend) + 2
        ws.cell(row=summary_start, column=1, value="Summary per question (share of answered + coverage of expected)").font = Font(bold=True, size=11, color="2D5016")
        cur = summary_start + 1
        if summaries:
            for s in summaries:
                ws.cell(row=cur, column=1, value=_csv_safe(f"{s['full_title']} -- {s['headline']}")).font = Font(bold=True, size=10)
                cur += 1
                for b in s["breakdown"]:
                    ws.cell(row=cur, column=1, value=_csv_safe(f"  {b['line']}")).alignment = wrap
                    cur += 1
                ws.cell(row=cur, column=1, value=_csv_safe(f"  Interpretation: {s['interpretation']}")).alignment = wrap
                cur += 2
        else:
            ws.cell(row=cur, column=1, value="(none)").font = meta_font

        widths = [28, 14, 18] + [32] * len(questions)
        for ci, w in enumerate(widths, 1):
            try:
                from openpyxl.utils import get_column_letter
                ws.column_dimensions[get_column_letter(ci)].width = w
            except Exception:
                pass

        # Full question definitions on their own sheet.
        qws = wb.create_sheet("Questions")
        for ci, h in enumerate(["Code", "Question (with scale)", "Type / Scale", "Required", "Answered", "Summary"], 1):
            cell = qws.cell(row=1, column=ci, value=h)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = center_wrap
        summary_by_code = {s["code"]: s for s in summaries}
        for i, q in enumerate(questions, 1):
            code = f"Q{i}"
            s = summary_by_code.get(code, {})
            qws.cell(row=i + 1, column=1, value=code).alignment = wrap
            qws.cell(row=i + 1, column=2, value=_csv_safe(_question_full_title(q, i))).alignment = wrap
            qws.cell(row=i + 1, column=3, value=_csv_safe(f"{q.qtype} / {_question_scale_text(q)}")).alignment = wrap
            qws.cell(row=i + 1, column=4, value="Yes" if q.is_required else "No").alignment = wrap
            qws.cell(row=i + 1, column=5, value=_csv_safe(s.get("headline", ""))).alignment = wrap
            breakdown_text = "\n".join(b["line"] for b in s.get("breakdown", []))
            qws.cell(row=i + 1, column=6, value=_csv_safe(breakdown_text)).alignment = wrap
        try:
            from openpyxl.utils import get_column_letter as _gcl
            for ci, w in enumerate([10, 70, 18, 12, 45, 40], 1):
                qws.column_dimensions[_gcl(ci)].width = w
        except Exception:
            pass

        # Cover sheet: uniform meta + coverage + per-role table (same as CSV/TXT/PDF).
        cover = wb.create_sheet("Cover", 0)
        cover["A1"] = _csv_safe(cover_title)
        cover["A1"].font = title_font
        cover["A2"] = _csv_safe(f"Generated {generated}")
        cover["A2"].font = meta_font
        cover["A4"] = "COVER (response rate)"
        cover["A4"].font = Font(bold=True, size=11, color="2D5016")
        cr = 5
        for line in cover_lines:
            cover.cell(row=cr, column=1, value=_csv_safe(line)).alignment = wrap
            cr += 1
        cr += 1
        cover.cell(row=cr, column=1, value="Coverage by role").font = Font(bold=True, size=11, color="2D5016")
        cr += 1
        for ci, h in enumerate(["Role", "Responded", "Expected", "Rate %", "Outstanding"], 1):
            cell = cover.cell(row=cr, column=ci, value=h)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = center_wrap
        cr += 1
        if coverage["role_rows"]:
            for rr in coverage["role_rows"]:
                cover.cell(row=cr, column=1, value=_csv_safe(rr["role"])).alignment = wrap
                cover.cell(row=cr, column=2, value=rr["responded"]).alignment = center_wrap
                cover.cell(row=cr, column=3, value=rr["expected"]).alignment = center_wrap
                cover.cell(row=cr, column=4, value=rr["rate"]).alignment = center_wrap
                cover.cell(row=cr, column=5, value=rr["remaining"]).alignment = center_wrap
                cr += 1
        else:
            cover.cell(row=cr, column=1, value="(no target roles)").font = meta_font
            cr += 1
        cr += 1
        cover.cell(row=cr, column=1, value="Overall interpretation").font = Font(bold=True, size=11, color="2D5016")
        cr += 1
        cover.cell(row=cr, column=1, value=_csv_safe(overall_interpretation or "(no responses yet)")).alignment = wrap
        cr += 1
        try:
            from openpyxl.utils import get_column_letter as _gcl0
            for ci, w in enumerate([28, 14, 14, 12, 14], 1):
                cover.column_dimensions[_gcl0(ci)].width = w
        except Exception:
            pass

        # Dedicated Summary sheet: coverage block on top, then one block per
        # question with its dual-percentage breakdown.
        sws = wb.create_sheet("Summary")
        sws["A1"] = _csv_safe(f"{cover_title} - Summary per question")
        sws["A1"].font = title_font
        sws["A2"] = _csv_safe(
            f"Generated {generated}  -  {coverage['responded']}/{coverage['expected']} "
            f"responded ({coverage['rate']}%) | Outstanding {coverage['remaining']}"
        )
        sws["A2"].font = meta_font
        sws["A3"] = _csv_safe(f"Target roles: {target_label} | {kind_label} | {status_label}")
        sws["A3"].font = meta_font
        hdr = 5
        for ci, h in enumerate(["Question", "Totals (answered of respondents | of expected)", "Breakdown (choice: count, % of answered, count/expected = % of expected)", "Interpretation"], 1):
            cell = sws.cell(row=hdr, column=ci, value=h)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = center_wrap
        r = hdr + 1
        if summaries:
            for s in summaries:
                sws.cell(row=r, column=1, value=_csv_safe(s["full_title"])).alignment = wrap
                sws.cell(row=r, column=2, value=_csv_safe(s["headline"])).alignment = wrap
                detail = "\n".join(b["line"] for b in s["breakdown"]) or "(free-text responses listed under Responses)"
                sws.cell(row=r, column=3, value=_csv_safe(detail)).alignment = wrap
                sws.cell(row=r, column=4, value=_csv_safe(s["interpretation"])).alignment = wrap
                r += 1
        else:
            sws.cell(row=r, column=1, value="(no questions)").font = meta_font
        try:
            from openpyxl.utils import get_column_letter as _gcl2
            for ci, w in enumerate([60, 45, 70, 60], 1):
                sws.column_dimensions[_gcl2(ci)].width = w
        except Exception:
            pass

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{safe_name}_responses.xlsx"'
        wb.save(response)

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
            Paragraph(xml_escape(cover_title), heading),
            Paragraph(xml_escape(f"Generated {generated}"), sub),
            Paragraph(
                xml_escape(
                    f"{kind_label} &middot; {status_label} &middot; Target: {target_label}"
                ),
                sub,
            ),
            Spacer(1, 3 * mm),
        ]

        story.append(Paragraph("Cover (response rate)", head_cell))
        story.append(Spacer(1, 2 * mm))
        for line in cover_lines:
            story.append(Paragraph(xml_escape(line), sub))
        story.append(Spacer(1, 2 * mm))
        role_data = [
            [Paragraph(xml_escape(h), head_cell) for h in
             ["Role", "Responded", "Expected", "Rate", "Outstanding"]]
        ]
        if coverage["role_rows"]:
            for rr in coverage["role_rows"]:
                role_data.append([
                    Paragraph(xml_escape(rr["role"]), cell),
                    Paragraph(xml_escape(str(rr["responded"])), cell),
                    Paragraph(xml_escape(str(rr["expected"])), cell),
                    Paragraph(xml_escape(f"{rr['rate']}%"), cell),
                    Paragraph(xml_escape(str(rr["remaining"])), cell),
                ])
        else:
            role_data.append([Paragraph(xml_escape("(no target roles)"), cell)])
        role_table = Table(role_data, repeatRows=1, hAlign="LEFT")
        role_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d5016")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(role_table)
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Overall interpretation", head_cell))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "<i>" + xml_escape(overall_interpretation or "(no responses yet)") + "</i>", sub
        ))
        story.append(Spacer(1, 5 * mm))

        if summaries:
            story.append(Paragraph("Summary per question (share of answered + coverage of expected)", head_cell))
            story.append(Spacer(1, 2 * mm))
            for s in summaries:
                story.append(Paragraph(
                    xml_escape(f"{s['full_title']} -- {s['headline']}"), sub
                ))
                for b in s["breakdown"]:
                    story.append(Paragraph(xml_escape(f"  {b['line']}"), sub))
                if not s["breakdown"]:
                    story.append(Paragraph(xml_escape("  (free-text responses listed under Responses)"), sub))
                story.append(Paragraph(
                    "<i>" + xml_escape(f"Interpretation: {s['interpretation']}") + "</i>", sub
                ))
                story.append(Spacer(1, 2 * mm))
            story.append(Spacer(1, 3 * mm))

        if legend:
            story.append(Paragraph("Questions (full text + scale)", head_cell))
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
