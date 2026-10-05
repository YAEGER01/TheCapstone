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


def make_form(roles=("President",), title="Officer Pulse Check"):
    return FeedbackForm.objects.create(
        title=title,
        section_title="Term-End Evaluation",
        description="Please answer honestly.",
        is_active=True,
        is_open=True,
        show_on_roles=list(roles),
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
