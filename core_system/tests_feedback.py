"""Officer feedback forms: server-side validation, the one-shot prompt, and
Superadmin-only authoring/export.

Covers the regression where ``response.answers.all()`` was touched before the
``FeedbackResponse`` row had a primary key, which made every first submission
raise ``ValueError`` and 500.
"""
from django.test import TestCase
from django.urls import reverse

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    FeedbackAnswer,
    FeedbackForm,
    FeedbackQuestion,
    FeedbackResponse,
    OfficerUser,
)
from core_system.services.mfa_service import generate_mfa_secret

PASSWORD = "Str0ng!Passw0rd"

CARD_URL = "/api/feedback/card/"
SUBMIT_URL = "/api/feedback/submit/"
ADMIN_URL = "/superadmin/feedback/"


def make_officer(role, username):
    return OfficerUser.objects.create(
        full_name=f"{role} Officer",
        username=username,
        password_hash=hash_password(PASSWORD),
        role=role,
        account_status="Active",
        mfa_enabled=False,
        mfa_secret=generate_mfa_secret(),
        email=f"{username}@isu.edu.ph",
    )


def make_form(roles=("President",), title="Officer Pulse Check",
               kind="normal", paired_pre=None):
    return FeedbackForm.objects.create(
        title=title,
        section_title="Term-End Evaluation",
        description="Please answer honestly.",
        is_active=True,
        is_open=True,
        show_on_roles=list(roles),
        kind=kind,
        paired_pre_FK=paired_pre,
    )


def add_mc(form, prompt, options, order, required=True, min_c=1, max_c=1):
    return FeedbackQuestion.objects.create(
        form_id_FK=form, prompt=prompt, qtype="mc", options=list(options),
        display_order=order, is_required=required,
        min_choices=min_c, max_choices=max_c,
    )


class FeedbackTestBase(TestCase):
    def setUp(self):
        self._seq = 0

    def login(self, role, username=None):
        self._seq += 1
        username = username or f"{role.lower()}_{self._seq}"
        officer = make_officer(role, username)
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()

        client_session = self.client.session
        client_session["access_token"] = token
        client_session["officer_id"] = officer.user_id_PK
        client_session["role"] = officer.role
        client_session.save()
        return officer


class FeedbackCardTests(FeedbackTestBase):
    def test_card_renders_for_matching_role(self):
        self.login("President")
        form = make_form(roles=["President"])
        add_mc(form, "How was the term?", ["Good", "Fair"], order=1)

        resp = self.client.get(CARD_URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Care to give a feedback??", body)
        self.assertIn("Yeah, Sure", body)
        self.assertIn("fb-modal", body)
        self.assertIn("How was the term?", body)

    def test_modal_starts_closed_and_opens_only_from_the_prompt(self):
        """The toast is the entry point; the modal must not self-open."""
        self.login("President")
        form = make_form(roles=["President"])
        add_mc(form, "How was the term?", ["Good", "Fair"], order=1)

        body = self.client.get(CARD_URL).content.decode()
        self.assertIn("data-fb-overlay hidden", body)
        self.assertIn("data-fb-open", body)
        self.assertNotIn("AUTO_OPEN_MS", body)

    def test_modal_is_mounted_outside_the_dashboard_scroll_container(self):
        """The overlay must not be nested in the dashboard's overflow:hidden
        shell, otherwise a tall modal cannot scroll and the page looks frozen."""
        self.login("President")
        form = make_form(roles=["President"])
        add_mc(form, "How was the term?", ["Good", "Fair"], order=1)

        body = self.client.get(CARD_URL).content.decode()
        # Everything is a sibling mount under <body>; the include itself is
        # only a fetch trigger plus the stylesheet/script tags.
        self.assertIn("data-fb-shell", body)
        self.assertNotIn("fb-shell", self.client.get("/president/").content.decode())

    def test_prompt_and_thanks_toasts_share_one_stack(self):
        self.login("President")
        form = make_form(roles=["President"])
        add_mc(form, "How was the term?", ["Good", "Fair"], order=1)

        body = self.client.get(CARD_URL).content.decode()
        # One stack container, toasts are appended into it (FIFO, max 3).
        self.assertEqual(body.count("data-fb-toast"), 1)
        self.assertIn("fb-toast-btn", body)

    def test_card_hidden_for_other_roles(self):
        self.login("Auditor")
        make_form(roles=["President"])

        resp = self.client.get(CARD_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode().strip(), "")

    def test_card_hidden_when_form_closed(self):
        self.login("President")
        form = make_form(roles=["President"])
        add_mc(form, "Rate us", ["Good"], order=1)
        form.is_open = False
        form.save()

        self.assertEqual(self.client.get(CARD_URL).content.decode().strip(), "")

    def test_card_hidden_once_officer_responded(self):
        officer = self.login("President")
        form = make_form(roles=["President"])
        question = add_mc(form, "Rate us", ["Good", "Fair"], order=1)

        self.assertNotEqual(self.client.get(CARD_URL).content.decode().strip(), "")

        response = FeedbackResponse.objects.create(
            form_id_FK=form, officer_id_FK=officer
        )
        FeedbackAnswer.objects.create(
            response_id_FK=response, question_id_FK=question, value_list=["Good"]
        )

        # One-shot: the prompt must not come back for the same form.
        self.assertEqual(self.client.get(CARD_URL).content.decode().strip(), "")


class FeedbackSubmitTests(FeedbackTestBase):
    def setUp(self):
        super().setUp()
        self.officer = self.login("President")
        self.form = make_form(roles=["President"])
        self.mc = add_mc(self.form, "Which worked?", ["A", "B", "C"], order=1)
        self.likert = FeedbackQuestion.objects.create(
            form_id_FK=self.form, prompt="Rate our support", qtype="likert",
            options=["Poor", "Fair", "Good"], scale_min=1, scale_max=3,
            display_order=2, is_required=True,
        )
        self.text = FeedbackQuestion.objects.create(
            form_id_FK=self.form, prompt="Any suggestions?", qtype="text",
            display_order=3, is_required=False,
        )

    def post(self, answers, form_id=None):
        payload = {"form_id": str(form_id or self.form.form_id_PK)}
        payload.update(answers)
        return self.client.post(SUBMIT_URL, payload)

    def test_first_submission_succeeds_and_stores_typed_answers(self):
        """Regression: this used to 500 on a brand-new response."""
        resp = self.post({
            f"q_{self.mc.question_id_PK}": "B",
            f"q_{self.likert.question_id_PK}": "3",
            f"q_{self.text.question_id_PK}": "Keep the monthly reports.",
        })

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["created"])
        # full_name is "<Role> Officer", so the first name is the role.
        self.assertEqual(data["first_name"], "President")
        self.assertEqual(
            data["message"], "Thanks President for submitting your feedback"
        )

        response = FeedbackResponse.objects.get(
            form_id_FK=self.form, officer_id_FK=self.officer
        )
        self.assertEqual(response.answers.count(), 3)

        mc_answer = response.answers.get(question_id_FK=self.mc)
        self.assertEqual(mc_answer.value_list, ["B"])

        likert_answer = response.answers.get(question_id_FK=self.likert)
        self.assertEqual(likert_answer.value_int, 3)

        text_answer = response.answers.get(question_id_FK=self.text)
        self.assertEqual(text_answer.value_text, "Keep the monthly reports.")

    def test_second_submission_updates_in_place(self):
        first = self.post({
            f"q_{self.mc.question_id_PK}": "A",
            f"q_{self.likert.question_id_PK}": "1",
        })
        self.assertTrue(first.json()["created"])

        second = self.post({
            f"q_{self.mc.question_id_PK}": "C",
            f"q_{self.likert.question_id_PK}": "2",
        })
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])

        self.assertEqual(FeedbackResponse.objects.count(), 1)
        response = FeedbackResponse.objects.get(
            form_id_FK=self.form, officer_id_FK=self.officer
        )
        # Re-submitting replaces the previous answer set rather than stacking.
        self.assertEqual(response.answers.count(), 2)
        self.assertEqual(
            response.answers.get(question_id_FK=self.mc).value_list, ["C"]
        )

    def test_required_question_must_be_answered(self):
        resp = self.post({f"q_{self.mc.question_id_PK}": "A"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Rate our support", resp.json()["error"])
        self.assertFalse(FeedbackResponse.objects.exists())

    def test_optional_question_may_be_skipped(self):
        resp = self.post({
            f"q_{self.mc.question_id_PK}": "A",
            f"q_{self.likert.question_id_PK}": "2",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_option_outside_authored_choices_is_rejected(self):
        resp = self.post({
            f"q_{self.mc.question_id_PK}": "Z",
            f"q_{self.likert.question_id_PK}": "2",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("invalid selection", resp.json()["error"])

    def test_likert_outside_scale_is_rejected(self):
        resp = self.post({
            f"q_{self.mc.question_id_PK}": "A",
            f"q_{self.likert.question_id_PK}": "9",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("between 1 and 3", resp.json()["error"])

    def test_question_from_another_form_cannot_be_answered(self):
        other = make_form(roles=["President"], title="Other form")
        foreign = add_mc(other, "Foreign question", ["X", "Y"], order=1)

        resp = self.post({
            f"q_{self.mc.question_id_PK}": "A",
            f"q_{self.likert.question_id_PK}": "2",
            f"q_{foreign.question_id_PK}": "X",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not part of this form", resp.json()["error"])

    def test_form_not_shown_to_role_is_forbidden(self):
        self.form.show_on_roles = ["Auditor"]
        self.form.save()

        resp = self.post({f"q_{self.likert.question_id_PK}": "2"})
        self.assertEqual(resp.status_code, 403)

    def test_unknown_form_is_404(self):
        resp = self.post({}, form_id=999999)
        self.assertEqual(resp.status_code, 404)

    def test_non_officer_role_cannot_submit(self):
        self.login("PIO", username="pio_one")
        resp = self.post({f"q_{self.likert.question_id_PK}": "2"})
        self.assertIn(resp.status_code, (302, 403))
        self.assertFalse(FeedbackResponse.objects.exists())


class FeedbackAdminAuthTests(FeedbackTestBase):
    def test_officer_cannot_reach_builder(self):
        self.login("President")
        resp = self.client.get(ADMIN_URL)
        self.assertIn(resp.status_code, (302, 403))

    def test_anonymous_cannot_reach_builder(self):
        self.assertIn(self.client.get(ADMIN_URL).status_code, (302, 403))

    def test_superadmin_reaches_builder_and_save_endpoints_exist(self):
        self.login("Superadmin")
        resp = self.client.get(ADMIN_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Feedback", resp.content.decode())

        for name in ("feedback_admin", "feedback_admin_save",
                     "feedback_admin_toggle", "feedback_admin_delete"):
            self.assertTrue(reverse(name).startswith("/superadmin/feedback"))


    def test_form_list_counts_are_not_multiplied_by_joins(self):
        # Regression: annotating questions + responses in one query multiplied
        # the rows, so 2 questions × 2 responses read as "4 questions".
        self.login("Superadmin")
        form = make_form(roles=["President"], title="Count Check")
        q1 = add_mc(form, "Pick?", ["A", "B"], order=0)
        q2 = add_mc(form, "Pick2?", ["C", "D"], order=1)
        for username in ("cnt_a", "cnt_b"):
            officer = make_officer("President", username)
            response = FeedbackResponse.objects.create(form_id_FK=form, officer_id_FK=officer)
            FeedbackAnswer.objects.create(
                response_id_FK=response, question_id_FK=q1, value_list=["A"])
            FeedbackAnswer.objects.create(
                response_id_FK=response, question_id_FK=q2, value_list=["C"])

        body = self.client.get(f"{ADMIN_URL}?form={form.form_id_PK}").content.decode()
        self.assertIn("2 questions", body)
        self.assertIn("2 responses", body)
        self.assertNotIn("4 questions", body)
        self.assertNotIn("4 responses", body)


class FeedbackSurveyKindTests(FeedbackTestBase):
    """Pre/Post survey kinds: pinned toast, ordered pairing, save validation."""

    def test_pre_card_is_persistent_with_answer_now(self):
        self.login("President")
        form = make_form(roles=["President"], kind="pre")
        add_mc(form, "How was the term?", ["Good", "Fair"], order=1)

        body = self.client.get(CARD_URL).content.decode()
        self.assertIn("PRE-SURVEY", body)
        self.assertIn("Answer Now", body)
        self.assertIn('data-fb-persistent="1"', body)
        self.assertIn('data-fb-kind="pre"', body)
        # No dismiss control on a persistent survey.
        self.assertNotIn("data-fb-dismiss-toast", body)

    def test_post_card_label(self):
        self.login("President")
        pre = make_form(roles=["President"], kind="pre", title="Pre Form")
        pre_q = add_mc(pre, "Before?", ["A", "B"], order=1)
        post = make_form(roles=["President"], kind="post", title="Post Form",
                         paired_pre=pre)
        add_mc(post, "After?", ["A", "B"], order=1)

        # Complete the Pre-Survey first.
        resp = self.client.post(SUBMIT_URL, {
            "form_id": str(pre.form_id_PK),
            f"q_{pre_q.question_id_PK}": "A",
        })
        self.assertEqual(resp.status_code, 200)

        body = self.client.get(CARD_URL).content.decode()
        self.assertIn("POST-SURVEY", body)
        self.assertIn("Answer Now", body)
        self.assertIn('data-fb-persistent="1"', body)

    def test_normal_card_unchanged(self):
        self.login("President")
        form = make_form(roles=["President"], kind="normal")
        add_mc(form, "How was the term?", ["Good", "Fair"], order=1)

        body = self.client.get(CARD_URL).content.decode()
        self.assertIn("Care to give a feedback??", body)
        self.assertIn("Yeah, Sure", body)
        self.assertNotIn("data-fb-persistent", body)
        self.assertIn("data-fb-dismiss-toast", body)

    def test_post_hidden_until_pre_completed(self):
        self.login("President")
        pre = make_form(roles=["President"], kind="pre", title="Pre First")
        pre_q = add_mc(pre, "Before?", ["A", "B"], order=1)
        post = make_form(roles=["President"], kind="post", title="Post Second",
                         paired_pre=pre)
        post_q = add_mc(post, "After?", ["A", "B"], order=1)

        # Pairing unmet: only the Pre-Survey is offered.
        first = self.client.get(CARD_URL).content.decode()
        self.assertIn("PRE-SURVEY", first)
        self.assertNotIn("POST-SURVEY", first)

        self.client.post(SUBMIT_URL, {
            "form_id": str(pre.form_id_PK),
            f"q_{pre_q.question_id_PK}": "A",
        })
        second = self.client.get(CARD_URL).content.decode()
        self.assertIn("POST-SURVEY", second)

        # Completing the Post-Survey quiets the card entirely.
        self.client.post(SUBMIT_URL, {
            "form_id": str(post.form_id_PK),
            f"q_{post_q.question_id_PK}": "B",
        })
        self.assertEqual(self.client.get(CARD_URL).content.decode().strip(), "")

    def _save(self, payload):
        import json as _json
        return self.client.post(
            reverse("feedback_admin_save"),
            data=_json.dumps(payload),
            content_type="application/json",
        )

    def _base_payload(self, **overrides):
        payload = {
            "title": "Kind Test Form",
            "section_title": "Hi",
            "description": "",
            "kind": "normal",
            "paired_pre_id": "",
            "is_active": "1",
            "is_open": "1",
            "show_on_roles": ["President"],
            "questions": [{"prompt": "Q?", "qtype": "text"}],
        }
        payload.update(overrides)
        return payload

    def test_save_post_requires_pairing(self):
        self.login("Superadmin")
        resp = self._save(self._base_payload(kind="post", paired_pre_id=""))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("paired", resp.json()["error"].lower())

    def test_save_post_rejects_non_pre_pairing(self):
        self.login("Superadmin")
        normal = make_form(roles=["President"], title="Not a pre")
        resp = self._save(self._base_payload(kind="post", paired_pre_id=str(normal.form_id_PK)))
        self.assertEqual(resp.status_code, 400)

    def test_save_post_with_pre_pairing(self):
        self.login("Superadmin")
        pre = make_form(roles=["President"], kind="pre", title="Pair Pre")
        resp = self._save(self._base_payload(kind="post", paired_pre_id=str(pre.form_id_PK)))
        self.assertEqual(resp.status_code, 200)
        form = FeedbackForm.objects.get(form_id_PK=resp.json()["form_id"])
        self.assertEqual(form.kind, "post")
        self.assertEqual(form.paired_pre_FK_id, pre.form_id_PK)

    def test_save_unknown_kind_rejected(self):
        self.login("Superadmin")
        resp = self._save(self._base_payload(kind="mega"))
        self.assertEqual(resp.status_code, 400)


class FeedbackSavePreservationTests(FeedbackTestBase):
    """Editing a form must not silently orphan its responses.

    Regression: the old wholesale question replace wiped every answer on ANY
    save (even title-only), while the empty response rows kept counting as
    "responded" and blocked re-answering. Now unchanged sets (and pure
    reorders) preserve everything; only a real question change resets.
    """

    def _save(self, payload):
        import json as _json
        return self.client.post(
            reverse("feedback_admin_save"),
            data=_json.dumps(payload),
            content_type="application/json",
        )

    def _payload(self, form, questions, **overrides):
        payload = {
            "form_id": str(form.form_id_PK),
            "title": form.title,
            "section_title": "",
            "description": "",
            "kind": "normal",
            "paired_pre_id": "",
            "is_active": "1",
            "is_open": "1",
            "show_on_roles": list(form.show_on_roles),
            "questions": questions,
        }
        payload.update(overrides)
        return payload

    def _mc(self, prompt, options):
        return {"prompt": prompt, "qtype": "mc", "options": list(options)}

    def _answered_form(self):
        officer = make_officer("President", f"pres_ans_{self._seq}")
        form = make_form(roles=["President", "Auditor"], title="Keep Me")
        q = add_mc(form, "Which worked?", ["A", "B"], order=0)
        response = FeedbackResponse.objects.create(form_id_FK=form, officer_id_FK=officer)
        FeedbackAnswer.objects.create(
            response_id_FK=response, question_id_FK=q, value_list=["A"]
        )
        return officer, form, q, response

    def test_title_only_save_preserves_questions_and_answers(self):
        self.login("Superadmin")
        _, form, q, response = self._answered_form()
        resp = self._save(self._payload(form, [self._mc("Which worked?", ["A", "B"])],
                                       title="Renamed"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["questions_changed"])
        self.assertEqual(data["reset_responses"], 0)
        # Same question row, same answer, same response.
        self.assertTrue(
            FeedbackQuestion.objects.filter(question_id_PK=q.question_id_PK).exists()
        )
        self.assertTrue(
            FeedbackResponse.objects.filter(response_id_PK=response.response_id_PK).exists()
        )
        answer = FeedbackAnswer.objects.get(response_id_FK=response)
        self.assertEqual(answer.value_list, ["A"])
        self.assertEqual(FeedbackForm.objects.get(form_id_PK=form.form_id_PK).title, "Renamed")

    def test_scope_only_save_preserves_responses(self):
        self.login("Superadmin")
        _, form, q, response = self._answered_form()
        resp = self._save(self._payload(
            form, [self._mc("Which worked?", ["A", "B"])],
            show_on_roles=["President"],
        ))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["questions_changed"])
        self.assertTrue(
            FeedbackResponse.objects.filter(response_id_PK=response.response_id_PK).exists()
        )
        self.assertEqual(
            FeedbackAnswer.objects.get(response_id_FK=response).value_list, ["A"]
        )

    def test_reorder_preserves_responses_and_updates_order(self):
        self.login("Superadmin")
        _, form, _, response = self._answered_form()
        q2 = add_mc(form, "Second?", ["X", "Y"], order=1)
        q1_id = form.questions.get(prompt="Which worked?").question_id_PK
        resp = self._save(self._payload(form, [
            self._mc("Second?", ["X", "Y"]),
            self._mc("Which worked?", ["A", "B"]),
        ]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["questions_changed"])
        self.assertTrue(
            FeedbackResponse.objects.filter(response_id_PK=response.response_id_PK).exists()
        )
        self.assertEqual(
            FeedbackQuestion.objects.get(question_id_PK=q2.question_id_PK).display_order, 0
        )
        self.assertEqual(
            FeedbackQuestion.objects.get(question_id_PK=q1_id).display_order, 1
        )

    def test_changed_questions_reset_responses(self):
        self.login("Superadmin")
        _, form, q, _ = self._answered_form()
        old_qid = q.question_id_PK
        resp = self._save(self._payload(form, [self._mc("Which worked v2?", ["A", "B"])]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["questions_changed"])
        self.assertEqual(data["reset_responses"], 1)
        self.assertEqual(
            FeedbackResponse.objects.filter(form_id_FK=form).count(), 0
        )
        self.assertEqual(FeedbackAnswer.objects.count(), 0)
        self.assertFalse(
            FeedbackQuestion.objects.filter(question_id_PK=old_qid).exists()
        )

    def test_unchanged_save_purges_legacy_answerless_shell(self):
        self.login("Superadmin")
        _, form, _, _ = self._answered_form()
        # Simulate the legacy orphan: a response row with zero answers.
        stray_officer = make_officer("Auditor", f"aud_stray_{self._seq}")
        shell = FeedbackResponse.objects.create(form_id_FK=form, officer_id_FK=stray_officer)
        resp = self._save(self._payload(form, [self._mc("Which worked?", ["A", "B"])]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            FeedbackResponse.objects.filter(response_id_PK=shell.response_id_PK).exists()
        )
        # The genuine answered response survives the shell purge.
        self.assertEqual(FeedbackResponse.objects.filter(form_id_FK=form).count(), 1)


class FeedbackInterpretationTests(FeedbackTestBase):
    """Interpretations must match the question type and never crown an
    arbitrary winner on tied counts."""

    def _summaries(self, form):
        from core_system.feedback_views import _build_question_summaries, _form_coverage
        resps = list(
            form.responses.select_related("officer_id_FK").prefetch_related("answers__question_id_FK")
        )
        cov = _form_coverage(form, resps)
        return _build_question_summaries(
            list(form.questions.all().order_by("display_order")), resps, cov["expected"]
        ), cov

    def _respond(self, form, question, officer, **answer):
        response = FeedbackResponse.objects.create(form_id_FK=form, officer_id_FK=officer)
        FeedbackAnswer.objects.create(
            response_id_FK=response, question_id_FK=question, **answer
        )

    def test_mc_tie_names_both_options(self):
        form = make_form(roles=["President"], title="Tie MC")
        q = add_mc(form, "Pick?", ["Red", "Blue"], order=0)
        self._respond(form, q, make_officer("President", "tie_mc_a"), value_list=["Red"])
        self._respond(form, q, make_officer("President", "tie_mc_b"), value_list=["Blue"])
        (summary,) = self._summaries(form)[0]
        text = summary["interpretation"]
        self.assertIn("Red", text)
        self.assertIn("Blue", text)
        self.assertNotIn("edges out", text)
        self.assertNotIn("most common", text)

    def test_likert_tie_names_both_values(self):
        form = make_form(roles=["President"], title="Tie Likert")
        q = FeedbackQuestion.objects.create(
            form_id_FK=form, prompt="Rate?", qtype="likert",
            options=["Poor", "Fair", "Good"], scale_min=1, scale_max=3,
            display_order=0, is_required=True,
        )
        self._respond(form, q, make_officer("President", "tie_lk_a"), value_int=2)
        self._respond(form, q, make_officer("President", "tie_lk_b"), value_int=3)
        (summary,) = self._summaries(form)[0]
        text = summary["interpretation"]
        self.assertIn("2", text)
        self.assertIn("3", text)
        self.assertNotIn("most common pick", text)

    def test_sole_leader_names_runner_up(self):
        form = make_form(roles=["President"], title="Leader MC")
        q = add_mc(form, "Pick?", ["Red", "Blue", "Green"], order=0)
        self._respond(form, q, make_officer("President", "lead_a"), value_list=["Red"])
        self._respond(form, q, make_officer("President", "lead_b"), value_list=["Red"])
        self._respond(form, q, make_officer("President", "lead_c"), value_list=["Blue"])
        (summary,) = self._summaries(form)[0]
        text = summary["interpretation"]
        self.assertIn("Red", text)
        self.assertTrue("Blue" in text and ("trails" in text or "next at" in text))

    def test_overall_names_joint_best_questions(self):
        from core_system.feedback_views import _overall_interpretation
        form = make_form(roles=["President"], title="Joint Best")
        q1 = add_mc(form, "First?", ["Yes", "No"], order=0)
        q2 = add_mc(form, "Second?", ["Up", "Down"], order=1)
        self._respond(form, q1, make_officer("President", "joint_a"), value_list=["Yes"])
        self._respond(form, q1, make_officer("President", "joint_b"), value_list=["No"])
        self._respond(form, q2, make_officer("President", "joint_c"), value_list=["Up"])
        self._respond(form, q2, make_officer("President", "joint_d"), value_list=["Down"])
        summaries, cov = self._summaries(form)
        overall = _overall_interpretation(form, cov, summaries)
        self.assertIn("Q1", overall)
        self.assertIn("Q2", overall)
