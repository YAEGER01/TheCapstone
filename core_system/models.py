from django.db import models
from django.core.validators import FileExtensionValidator
import hashlib
import hmac
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.text import slugify
from decimal import Decimal
from django.db.models.signals import pre_save
from django.dispatch import receiver

from core_system.fields import EncryptedCharField, EncryptedTextField

SECURE_UPLOAD_ALLOWED_EXTENSIONS = [
    "jpg", "jpeg", "png", "webp", "gif",
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt",
]
SECURE_UPLOAD_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif"]

class OfficerUser(models.Model):
    user_id_PK = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255)
    username = models.CharField(max_length=150, unique=True)
    password_hash = models.CharField(max_length=255)
    role = models.CharField(max_length=50)
    department_id_FK = models.ForeignKey(
        "Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="department_id_FK",
        related_name="officers",
    )
    account_status = models.CharField(max_length=50)
    term_start = models.DateField(null=True, blank=True)
    term_end = models.DateField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    # TOTP seed: Fernet ciphertext at rest (never filtered on — attribute-only).
    mfa_secret = EncryptedCharField(max_length=500, null=True, blank=True)
    # Authenticator-app fallback (RFC 6238 base32 secret for offline TOTP).
    # Enrolled separately from the email OTP above so existing secrets keep
    # working; set only after the officer confirms a code from their app.
    authenticator_secret = EncryptedCharField(max_length=500, null=True, blank=True)
    authenticator_enabled = models.BooleanField(default=False)
    authenticator_enrolled_at = models.DateTimeField(null=True, blank=True)
    # Last time backup codes were issued (authenticator enrollment, first
    # member login, or standalone issuance). Drives the fallback nudge and
    # the one-time first-login reveal; hashes only are ever stored.
    backup_codes_issued_at = models.DateTimeField(null=True, blank=True)
    last_mfa_email_sent_at = models.DateTimeField(null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    must_change_password = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "officer_user"


class Department(models.Model):
    department_id_PK = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    head_officer_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="head_officer_id_FK",
        related_name="headed_departments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "department"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Member(models.Model):
    member_id_PK = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255)
    employee_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    officer_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="officer_user_id_FK",
        related_name="linked_member_profiles",
    )
    department = models.CharField(max_length=100, null=True, blank=True)
    department_id_FK = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="department_id_FK",
        related_name="members",
    )
    position = models.CharField(max_length=100, null=True, blank=True)
    # PII at rest: Fernet ciphertext (never filtered on — attribute-only).
    contact_number = EncryptedCharField(max_length=255, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    employment_status = models.CharField(max_length=50)
    membership_status = models.CharField(max_length=50)
    member_type = models.CharField(max_length=50, blank=True)
    date_joined = models.DateField()
    profile_picture = models.ImageField(upload_to="profile_pics/", null=True, blank=True)
    pin_code = models.CharField(max_length=255, null=True, blank=True)
    qr_code = models.ImageField(upload_to="qr_codes/", null=True, blank=True)
    qr_data = models.CharField(max_length=255, null=True, blank=True)
    emergency_contact = models.CharField(max_length=255, null=True, blank=True)
    # PII at rest: Fernet ciphertext (never filtered on — attribute-only).
    emergency_number = EncryptedCharField(max_length=255, null=True, blank=True)
    setup_complete = models.BooleanField(default=False)
    # Distinguishes members created via the Treasurer's "Create Member" flow
    # (no login account, email-only notifications) from regular members with
    # a dashboard account. Values: "dashboard" | "no dashboard".
    dashboard_access = models.CharField(max_length=20, default="dashboard")
    # Payment-eligibility class (By-Laws): Teaching members pay the full
    # monthly deduction (dues + aid funds); Retired members pay nothing and
    # are excluded from monthly assessments entirely. Non-teaching staff are
    # not part of this association (they are covered by NASA), so the
    # classification was removed outright.
    CLASSIFICATION_TEACHING = "Teaching"
    CLASSIFICATION_RETIRED = "Retired"
    MEMBER_CLASSIFICATION_CHOICES = [
        (CLASSIFICATION_TEACHING, "Teaching"),
        (CLASSIFICATION_RETIRED, "Retired"),
    ]
    member_classification = models.CharField(
        max_length=20,
        choices=MEMBER_CLASSIFICATION_CHOICES,
        default=CLASSIFICATION_TEACHING,
        db_column="member_classification",
    )
    # MANDATORY push: every member email also force-pushes to all subscribed
    # devices. The dashboard auto-subscribes on login, so this defaults True
    # for new accounts; the flag is display-only (delivery ignores it).
    push_enabled = models.BooleanField(default=True, db_column="push_enabled")
    # Mid-year enrollment: True when the member joined after January so the
    # Treasurer can generate catch-up dues (Jan .. date_joined.month) into
    # the MonthlyAssessment workflow. Cleared after a successful generation.
    dues_backfill_pending = models.BooleanField(default=False)

    # Personal information — self-service editable from the member dashboard
    # (profile page); read-only in the Treasurer's Member Directory view.
    CIVIL_STATUS_SINGLE = "Single"
    CIVIL_STATUS_MARRIED = "Married"
    CIVIL_STATUS_WIDOWED = "Widowed"
    CIVIL_STATUS_SEPARATED = "Separated"
    CIVIL_STATUS_ANNULLED = "Annulled"
    CIVIL_STATUS_CHOICES = [
        (CIVIL_STATUS_SINGLE, "Single"),
        (CIVIL_STATUS_MARRIED, "Married"),
        (CIVIL_STATUS_WIDOWED, "Widowed"),
        (CIVIL_STATUS_SEPARATED, "Separated"),
        (CIVIL_STATUS_ANNULLED, "Annulled"),
    ]
    SEX_MALE = "Male"
    SEX_FEMALE = "Female"
    SEX_CHOICES = [
        (SEX_MALE, "Male"),
        (SEX_FEMALE, "Female"),
    ]
    address = models.TextField(null=True, blank=True)
    civil_status = models.CharField(
        max_length=20,
        choices=CIVIL_STATUS_CHOICES,
        null=True,
        blank=True,
        db_column="civil_status",
    )
    sex = models.CharField(max_length=10, choices=SEX_CHOICES, null=True, blank=True, db_column="sex")
    date_of_birth = models.DateField(null=True, blank=True, db_column="date_of_birth")

    @property
    def age(self):
        """Age in whole years, derived from date_of_birth — never stored, so
        it can never go stale."""
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    class Meta:
        db_table = "member"


# Standard contribution amounts from the ISUCauFA By-Laws
# These are authoritative constants used by aid workflows and automated calculations.
DEATH_AID_CONTRIBUTION_MAPPING = {
    # normalized relationship -> contribution amount
    "member": Decimal("500.00"),
    "husband": Decimal("300.00"),
    "wife": Decimal("300.00"),
    "spouse": Decimal("300.00"),
    "parent": Decimal("250.00"),
    "child": Decimal("250.00"),
    "son": Decimal("250.00"),
    "daughter": Decimal("250.00"),
    "brother": Decimal("100.00"),
    "sister": Decimal("100.00"),
    "sibling": Decimal("100.00"),
    "full-blood brother": Decimal("100.00"),
    "full-blood sister": Decimal("100.00"),
}

# Fixed medical aid contribution expected from each eligible member
MEDICAL_AID_CONTRIBUTION_AMOUNT = Decimal("100.00")


class Attendance(models.Model):
    attendance_id_PK = models.AutoField(primary_key=True)
    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        db_column="member_id_FK",
        related_name="attendance_records",
    )
    event_id_FK = models.ForeignKey(
        'Event',
        on_delete=models.CASCADE,
        db_column="event_id_FK",
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    date = models.DateField()
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='Present')  # Present, Late, Absent
    check_in_method = models.CharField(max_length=20, default='PIN')  # PIN, QR, Manual

    class Meta:
        db_table = "attendance"
        unique_together = [['member_id_FK', 'date']]


class MemberRegistrationRequest(models.Model):
    request_id_PK = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255)
    employee_id = models.CharField(max_length=50)
    email = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    position = models.CharField(max_length=100, null=True, blank=True)
    membership_category = models.CharField(max_length=50, default="Permanent")
    contact_number = models.CharField(max_length=50, null=True, blank=True)
    payment_method = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    receipt_number = models.CharField(max_length=100)
    reference_number = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    password_hash = models.CharField(max_length=255, null=True, blank=True)
    account_creation_requested = models.BooleanField(default=True)
    status = models.CharField(max_length=50, default="Pending Treasurer Review")
    returned_reason = models.TextField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_by_ip = models.GenericIPAddressField(protocol="both", unpack_ipv4=False, null=True, blank=True)
    submitted_by_user_agent = models.CharField(max_length=255, null=True, blank=True)
    processed_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="processed_by_user_id_FK",
        related_name="processed_registration_requests",
    )
    treasurer_verified_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="treasurer_verified_by_user_id_FK",
        related_name="treasurer_verified_registrations",
    )
    auditor_verified_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="auditor_verified_by_user_id_FK",
        related_name="auditor_verified_registrations",
    )
    president_approved_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="president_approved_by_user_id_FK",
        related_name="president_approved_registrations",
    )

    class Meta:
        db_table = "member_registration_request"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.full_name} ({self.employee_id}) - {self.status}"


class LoginAttemptLog(models.Model):
    attempt_id_PK = models.AutoField(primary_key=True)

    user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="user_id_FK",
    )
    username_used = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(protocol="both", unpack_ipv4=False)
    device_info = models.CharField(max_length=255, null=True, blank=True)
    result = models.CharField(max_length=50)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "login_attempt_log"


class AccessSession(models.Model):
    session_id_PK = models.AutoField(primary_key=True)

    user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.CASCADE,
        db_column="user_id_FK",
    )
    token_id = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField(protocol="both", unpack_ipv4=False)
    device_info = models.CharField(max_length=255, null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    session_status = models.CharField(max_length=50)
    last_activity_at = models.DateTimeField(null=True, blank=True)

    trusted_device = models.BooleanField(default=False)
    last_verified_location = models.JSONField(null=True, blank=True)
    session_policy = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "access_session"


class Notification(models.Model):
    notification_id_PK = models.AutoField(primary_key=True)

    recipient_type = models.CharField(max_length=50)
    recipient_id = models.IntegerField()
    recipient_name = models.CharField(max_length=255)
    recipient_contact = models.CharField(max_length=255, null=True, blank=True)
    notification_type = models.CharField(max_length=50)
    message = models.TextField()
    delivery_status = models.CharField(max_length=50)
    sent_at = models.DateTimeField(auto_now_add=True)

    sender_name = models.CharField(max_length=255, null=True, blank=True)
    sender_role = models.CharField(max_length=50, null=True, blank=True)
    receipt_number = models.CharField(max_length=255, null=True, blank=True)

    category = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="dues, contribution, or general",
    )
    related_post_id_FK = models.ForeignKey(
        "AidTrackingPost",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="related_post_id_FK",
        related_name="notifications",
    )
    overdue_bucket = models.CharField(
        max_length=10, null=True, blank=True,
        help_text="1d, 3d, 5d, 7d, 15d+",
    )
    channel = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="email, sms, push",
    )
    scheduled_date = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    is_read = models.BooleanField(default=False, db_column="is_read")

    class Meta:
        db_table = "notification"
        indexes = [
            models.Index(fields=["recipient_type", "recipient_id", "sent_at", "notification_id_PK"]),
            models.Index(fields=["recipient_type", "recipient_id", "is_read"]),
        ]


class MfaBackupCode(models.Model):
    """Single-use recovery codes for officers with authenticator fallback.

    Only the sha256 hash is stored; plaintext is shown once at enrollment
    and never persisted. A code burns on first successful use.
    """
    code_id_PK = models.AutoField(primary_key=True)
    officer_id_FK = models.ForeignKey(
        "OfficerUser",
        on_delete=models.CASCADE,
        db_column="officer_id_FK",
        related_name="mfa_backup_codes",
    )
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mfa_backup_code"


class PushSubscription(models.Model):
    subscription_id_PK = models.AutoField(primary_key=True)

    officer_id_FK = models.ForeignKey(
        "OfficerUser",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        db_column="officer_id_FK",
        related_name="push_subscriptions",
    )
    member_id_FK = models.ForeignKey(
        "Member",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        db_column="member_id_FK",
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500)
    p256dh_key = models.CharField(max_length=256)
    auth_key = models.CharField(max_length=128)
    user_agent = models.CharField(max_length=500, null=True, blank=True)
    origin = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "push_subscription"
        unique_together = (("member_id_FK", "endpoint"), ("officer_id_FK", "endpoint"))


class MonthlyDues(models.Model):
    dues_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
    )
    month_covered = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    payment_status = models.CharField(max_length=50)

    # Approval workflow fields
    treasurer_status = models.CharField(max_length=50, default="Pending Treasurer Review", db_column="treasurer_status")
    treasurer_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="treasurer_id_FK",
        related_name="monthly_dues_treasurer_approved",
    )
    treasurer_remarks = models.TextField(null=True, blank=True)
    treasurer_approved_at = models.DateTimeField(null=True, blank=True)

    auditor_status = models.CharField(max_length=50, default="Pending Auditor Review", db_column="auditor_status")
    auditor_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="auditor_id_FK",
        related_name="monthly_dues_auditor_approved",
    )
    auditor_remarks = models.TextField(null=True, blank=True)
    auditor_approved_at = models.DateTimeField(null=True, blank=True)

    president_status = models.CharField(max_length=50, default="Pending President Approval", db_column="president_status")
    president_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="president_id_FK",
        related_name="monthly_dues_president_approved",
    )
    president_remarks = models.TextField(null=True, blank=True)
    president_approved_at = models.DateTimeField(null=True, blank=True)

    # Added to support treasurer_dashboard.html OTC form field: otc_date
    payment_date = models.DateField(null=True, blank=True)

    receipt_number = models.CharField(max_length=100, null=True, blank=True)
    deduction_batch_reference = models.CharField(max_length=100, null=True, blank=True)
    remittance_reference = models.CharField(max_length=100, null=True, blank=True)

    is_advance = models.BooleanField(
        default=False,
        db_column="is_advance",
        help_text="True when the covered month is in the future (early/advance payment).",
    )

    recorded_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.RESTRICT,
        db_column="recorded_by_user_id_FK",
    )


    class Meta:
        db_table = "monthly_dues"


class MemberLedger(models.Model):
    ledger_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
        related_name="ledger_entries",
    )

    transaction_type = models.CharField(
        max_length=50,
        help_text="membership_fee, monthly_dues, contribution, medical_aid, death_aid, refund, adjustment",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    direction = models.CharField(
        max_length=10,
        help_text="credit or debit",
    )
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)

    reference_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="FK to the source record (MonthlyDues, MembershipFee, etc.)",
    )
    reference_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="The model name of the reference",
    )

    description = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    recorded_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.RESTRICT,
        db_column="recorded_by_user_id_FK",
        related_name="ledger_entries_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "member_ledger"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["member_id_FK"]),
            models.Index(fields=["transaction_type"]),
            models.Index(fields=["recorded_at"]),
            models.Index(fields=["member_id_FK", "recorded_at", "ledger_id_PK"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]


class MembershipFee(models.Model):
    fee_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    payment_status = models.CharField(max_length=50)
    payment_date = models.DateField()
    receipt_number = models.CharField(max_length=100, null=True, blank=True)
    deposit_reference = models.CharField(max_length=100, null=True, blank=True)

    recorded_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.RESTRICT,
        db_column="recorded_by_user_id_FK",
    )

    class Meta:
        db_table = "membership_fee"
        unique_together = (('member_id_FK', 'receipt_number'),)


class FinancialDocumentArchive(models.Model):
    document_id_PK = models.AutoField(primary_key=True)

    related_module = models.CharField(max_length=100)
    related_record_id = models.IntegerField()
    document_type = models.CharField(max_length=100)

    file_path = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_hash = models.CharField(max_length=255)
    verification_status = models.CharField(max_length=50)

    uploaded_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.RESTRICT,
        db_column="uploaded_by_user_id_FK",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "financial_document_archive"


class BylawsFile(models.Model):
    BYLAWS_DOCUMENT_TYPE_CONSTITUTION = "Constitution"
    BYLAWS_DOCUMENT_TYPE_BYLAWS = "By-Laws"
    BYLAWS_DOCUMENT_TYPE_PUBLIC = "Public Documents"
    BYLAWS_DOCUMENT_TYPE_OTHER = "Other"

    BYLAWS_DOCUMENT_TYPE_CHOICES = [
        (BYLAWS_DOCUMENT_TYPE_CONSTITUTION, "Constitution"),
        (BYLAWS_DOCUMENT_TYPE_BYLAWS, "By-Laws"),
        (BYLAWS_DOCUMENT_TYPE_PUBLIC, "Public Documents"),
        (BYLAWS_DOCUMENT_TYPE_OTHER, "Other"),
    ]

    bylaws_file_id = models.AutoField(primary_key=True)

    document_type = models.CharField(
        max_length=50,
        choices=BYLAWS_DOCUMENT_TYPE_CHOICES,
        default=BYLAWS_DOCUMENT_TYPE_BYLAWS,
    )
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=100)
    file_data = models.BinaryField()
    file_size = models.IntegerField()
    file_hash = models.CharField(max_length=255)

    verification_status = models.CharField(max_length=50, default="Active")
    is_public_visible = models.BooleanField(default=False)

    uploaded_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.RESTRICT,
        db_column="uploaded_by_user_id_FK",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bylaws_files"


class SupportingProof(models.Model):
    proof_id_PK = models.AutoField(primary_key=True)

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_column="content_type_id",
    )
    object_id = models.PositiveIntegerField(db_column="object_id")
    content_object = GenericForeignKey("content_type", "object_id")

    file = models.FileField(
        upload_to="secure_uploads/supporting_proofs/%Y/%m/%d/",
        max_length=500,
        db_column="file_path",
        validators=[FileExtensionValidator(allowed_extensions=SECURE_UPLOAD_ALLOWED_EXTENSIONS)],
    )
    file_name = models.CharField(max_length=255, db_column="file_name")
    file_type = models.CharField(max_length=100, db_column="file_type")

    document_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        db_column="document_type",
        help_text=(
            "Category for aid claim documents: 'request_letter', 'hospital_bill', "
            "or 'other'. Empty for legacy/uncategorized uploads."
        ),
    )

    file_sha256 = models.CharField(max_length=64, db_column="file_sha256")
    row_signature = models.CharField(max_length=64, db_column="row_signature")

    uploaded_at = models.DateTimeField(auto_now_add=True, db_column="uploaded_at")
    uploaded_by = models.ForeignKey(
        "OfficerUser",
        on_delete=models.SET_NULL,
        null=True,
        db_column="uploaded_by_user_id_FK",
        related_name="supporting_proofs",
    )

    class Meta:
        db_table = "supporting_proof"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["uploaded_at"]),
        ]

    def compute_file_hash(self):
        sha = hashlib.sha256()
        for chunk in self.file.open("rb").chunks():
            sha.update(chunk)
        self.file.open("rb").close()
        return sha.hexdigest()

    def compute_row_signature(self, file_digest, object_id):
        from django.conf import settings

        message = f"{file_digest}:{object_id}:{settings.SECRET_KEY}".encode()
        return hmac.new(
            settings.SECRET_KEY.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()





class AuditFindingsReport(models.Model):
    audit_report_id_PK = models.AutoField(primary_key=True)

    report_title = models.CharField(max_length=255)
    report_period = models.CharField(max_length=100)
    findings_summary = models.TextField()
    report_status = models.CharField(max_length=50)

    prepared_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.RESTRICT,
        db_column="prepared_by_user_id_FK",
        related_name="audit_findings_reports_prepared",
    )

    prepared_date = models.DateField()

    board_submission_date = models.DateField(null=True, blank=True)
    board_meeting_reference = models.CharField(max_length=255, null=True, blank=True)

    presentation_status = models.CharField(max_length=50)
    certification_status = models.CharField(max_length=50)

    certified_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="certified_by_user_id_FK",
        related_name="audit_reports_certified",
    )

    class Meta:
        db_table = "audit_findings_report"


class OrganizationFundReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]
    REPORT_STATUS_CHOICES = [
        ("Draft", "Draft"),
        ("Submitted", "Submitted"),
        ("Auditor Verified", "Auditor Verified"),
        ("Returned for Revision", "Returned for Revision"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    report_id_PK = models.AutoField(primary_key=True)

    report_period = models.CharField(max_length=20)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    report_status = models.CharField(max_length=50, choices=REPORT_STATUS_CHOICES, default="Draft")
    file_path = models.CharField(max_length=500, blank=True)

    # Optional custom report content (from Reports Management). When present,
    # the workflow (Auditor verification / President approval / PDF / downloads)
    # shows THIS generated report instead of the organization-wide summary.
    report_title = models.CharField(max_length=200, blank=True, default="")
    report_filters = models.CharField(max_length=300, blank=True, default="")
    report_rows = models.TextField(blank=True, default="")

    prepared_by_user_id_FK = models.ForeignKey(
        "OfficerUser",
        on_delete=models.RESTRICT,
        db_column="prepared_by_user_id_FK",
        related_name="fund_reports_prepared",
    )
    approved_by_user_id_FK = models.ForeignKey(
        "OfficerUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="approved_by_user_id_FK",
        related_name="fund_reports_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    auditor_verified_by_user_id_FK = models.ForeignKey(
        "OfficerUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="auditor_verified_by_user_id_FK",
        related_name="fund_reports_verified",
    )
    auditor_verified_at = models.DateTimeField(null=True, blank=True)
    return_reason = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_fund_report"
        ordering = ["-created_at"]


class MedicalAid(models.Model):
    medical_aid_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
    )

    request_date = models.DateField()
    requested_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hospital_name = models.CharField(max_length=255, blank=True)
    hospital_date = models.CharField(max_length=50, null=True, blank=True)
    hospital_address = models.CharField(max_length=500, null=True, blank=True)
    admission_date = models.DateField(null=True, blank=True)
    discharge_date = models.DateField(null=True, blank=True)
    # Health data at rest: Fernet ciphertext (never filtered on — display-only).
    reason_for_request = EncryptedTextField(null=True, blank=True)
    hospital_bill_amount = models.DecimalField(max_digits=10, decimal_places=2)
    claim_year = models.IntegerField()

    document_status = models.CharField(max_length=50)
    policy_record_status = models.CharField(max_length=50)

    validated_aid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50)

    treasurer_validated_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="treasurer_validated_by_user_id_FK",
        related_name="death_aid_treasurer_validated",
    )

    auditor_verified_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="auditor_verified_by_user_id_FK",
        related_name="medical_aid_auditor_verified",
    )

    president_decided_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="president_decided_by_user_id_FK",
        related_name="death_aid_president_decided",
    )

    president_decision = models.CharField(max_length=50, null=True, blank=True)

    disbursement_source = models.CharField(
        max_length=20, null=True, blank=True,
        choices=[("fund", "Fund — paid from org fund"), ("direct", "Direct — payroll deduction, no fund impact")],
        help_text="How was this aid funded?",
    )

    released_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="released_by_user_id_FK",
        related_name="death_aid_released",
        db_constraint=False,
    )

    release_reference = models.CharField(max_length=100, null=True, blank=True)
    acknowledgement_reference = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "medical_aid"


class Claimant(models.Model):
    claimant_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        db_column="member_id_FK",
    )
    full_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=50, null=True, blank=True)
    relationship_to_member = models.CharField(max_length=100)
    relationship_group = models.CharField(max_length=20, blank=True)
    authorization_status = models.CharField(max_length=50)

    class Meta:
        db_table = "claimant"


class DeathAid(models.Model):
    death_aid_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
    )

    claimant_id_FK = models.ForeignKey(
        Claimant,
        on_delete=models.RESTRICT,
        db_column="claimant_id_FK",
    )

    claim_date = models.DateField()
    claim_type = models.CharField(max_length=50)
    date_of_death = models.DateField(null=True, blank=True)

    deceased_name = models.CharField(max_length=255)
    relationship_to_member = models.CharField(max_length=100)
    relationship_group = models.CharField(max_length=20, blank=True)

    funeral_location = models.CharField(max_length=255, blank=True)
    interment_date = models.DateField(null=True, blank=True)

    benefit_amount = models.DecimalField(max_digits=10, decimal_places=2)
    bill_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    document_status = models.CharField(max_length=50)
    status = models.CharField(max_length=50)

    treasurer_validated_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="treasurer_validated_by_user_id_FK",
    )
    auditor_verified_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="auditor_verified_by_user_id_FK",
        related_name="death_aid_auditor_verified",
    )

    president_decided_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="president_decided_by_user_id_FK",
        related_name="medical_aid_president_decided",
    )

    president_decision = models.CharField(max_length=50, null=True, blank=True)

    disbursement_source = models.CharField(
        max_length=20, null=True, blank=True,
        choices=[("fund", "Fund — paid from org fund"), ("direct", "Direct — payroll deduction, no fund impact")],
        help_text="How was this aid funded?",
    )

    released_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="released_by_user_id_FK",
        related_name="medical_aid_released",
        db_constraint=False,
    )

    release_reference = models.CharField(max_length=100, null=True, blank=True)
    acknowledgement_reference = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "death_aid"


@receiver(pre_save, sender=DeathAid)
def set_death_aid_benefit(sender, instance, **kwargs):
    """Auto-set standard benefit amount and relationship_group from relationship_to_member.

    Uses `DEATH_AID_CONTRIBUTION_MAPPING` to canonicalize common relationship text.
    """
    try:
        from decimal import Decimal as _D
    except Exception:
        _D = Decimal

    rel_raw = (instance.relationship_to_member or "").strip().lower()
    if not rel_raw:
        return

    # Determine canonical amount
    amount = None
    if rel_raw in DEATH_AID_CONTRIBUTION_MAPPING:
        amount = DEATH_AID_CONTRIBUTION_MAPPING[rel_raw]
    else:
        # Keyword-based fallback
        if any(k in rel_raw for k in ("husband", "wife", "spouse")):
            amount = DEATH_AID_CONTRIBUTION_MAPPING.get("spouse")
        elif any(k in rel_raw for k in ("parent", "mother", "father")):
            amount = DEATH_AID_CONTRIBUTION_MAPPING.get("parent")
        elif any(k in rel_raw for k in ("child", "son", "daughter")):
            amount = DEATH_AID_CONTRIBUTION_MAPPING.get("child")
        elif any(k in rel_raw for k in ("brother", "sister", "sibling")):
            amount = DEATH_AID_CONTRIBUTION_MAPPING.get("sibling")
        elif "member" in rel_raw:
            amount = DEATH_AID_CONTRIBUTION_MAPPING.get("member")

    if amount is not None and (not instance.benefit_amount or instance.benefit_amount == _D("0")):
        instance.benefit_amount = amount

    # Ensure bill_amount is not automatically set to benefit_amount
    # Only set bill_amount if explicitly provided
    if not hasattr(instance, '_skip_bill_amount_auto_set'):
        # Don't auto-set bill_amount - it should remain None unless explicitly set
        pass

    # Set relationship_group for reporting/UI: member, spouse, parent_child, sibling, other
    if "member" in rel_raw:
        instance.relationship_group = "member"
    elif any(k in rel_raw for k in ("husband", "wife", "spouse")):
        instance.relationship_group = "spouse"
    elif any(k in rel_raw for k in ("parent", "mother", "father", "child", "son", "daughter")):
        instance.relationship_group = "parent_child"
    elif any(k in rel_raw for k in ("brother", "sister", "sibling")):
        instance.relationship_group = "sibling"
    else:
        instance.relationship_group = "other"


class PositionRank(models.Model):
    position_rank_id_PK = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100, default="Other")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by_user_id_FK",
    )

    class Meta:
        db_table = "position_rank"
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class PositionCategory(models.Model):
    """Treasurer-managed categories for academic ranks (replaces hardcoded choices)."""

    category_id_PK = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="created_by_user_id_FK",
    )

    class Meta:
        db_table = "position_category"
        ordering = ["name"]

    def __str__(self):
        return self.name


class RevisionLog(models.Model):
    log_id = models.AutoField(primary_key=True)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_column="content_type_id",
    )
    object_id = models.PositiveIntegerField(db_column="object_id")
    content_object = GenericForeignKey("content_type", "object_id")

    rejection_reason = models.TextField()
    snapshot_data = models.JSONField()
    auditor_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.SET_NULL,
        null=True,
        db_column="auditor_id_FK",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "revision_log"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["created_at"]),
        ]



class TransactionVerification(models.Model):
    verification_id = models.AutoField(primary_key=True)
    table_name = models.CharField(max_length=50)
    record_id = models.IntegerField()

    target_category = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="'payment' or 'aid' — replaces AuditorPaymentVerification/AuditorAidVerification",
    )

    verification_status = models.CharField(
        max_length=50,
        default="Pending Verification"
    )

    auditor_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="auditor_id_FK",
        related_name="transaction_verifications_audited",
    )
    auditor_remarks = models.TextField(null=True, blank=True)
    evidence_file_path = models.CharField(max_length=500, null=True, blank=True)
    evidence_file_hash = models.CharField(max_length=255, null=True, blank=True)

    returned_by_auditor_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="returned_by_auditor_id_FK",
        related_name="transaction_verifications_returned",
    )
    returned_reason = models.TextField(null=True, blank=True)
    return_count = models.IntegerField(default=0)
    deposit_slip_reference = models.CharField(max_length=255, null=True, blank=True)

    president_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="president_id_FK",
        related_name="transaction_verifications_approved",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "transaction_verification"


class TransactionArchive(models.Model):
    archive_id_PK = models.AutoField(primary_key=True)

    transaction_type = models.CharField(max_length=50)
    record_id = models.IntegerField()

    member_id_FK = models.ForeignKey(
        Member,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="member_id_FK",
    )

    member_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    validated_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    fiscal_term = models.CharField(max_length=50, null=True, blank=True)

    release_reference = models.CharField(max_length=100, null=True, blank=True)
    released_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="released_by_user_id_FK",
        related_name="archived_releases",
    )

    verified_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(auto_now_add=True)
    archived_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="archived_by_user_id_FK",
        related_name="archived_by",
    )

    class Meta:
        db_table = "transaction_archive"


class SalaryDeductionExemption(models.Model):
    exemption_id_PK = models.AutoField(primary_key=True)

    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        db_column="member_id_FK",
        related_name="salary_deduction_exemptions",
    )

    month_covered = models.CharField(max_length=50)
    reason = models.TextField(null=True, blank=True)
    
    status = models.CharField(
        max_length=50,
        default="Pending",
        help_text="Pending, Approved, Rejected"
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    requested_by_member = models.BooleanField(default=True)

    reviewed_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="reviewed_by_user_id_FK",
        related_name="reviewed_exemptions",
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_remarks = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "salary_deduction_exemption"
        unique_together = (('member_id_FK', 'month_covered'),)


class AidTrackingPost(models.Model):
    STATUS_CHOICES = [
        ("tracking", "Tracking — members are being charged"),
        ("closed", "Closed — all tracked"),
    ]

    post_id_PK = models.AutoField(primary_key=True)

    archive_id_FK = models.ForeignKey(
        TransactionArchive,
        on_delete=models.CASCADE,
        db_column="archive_id_FK",
        related_name="aid_tracking_posts",
    )
    aid_type = models.CharField(max_length=50)
    target_month = models.CharField(max_length=7)
    total_expected = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_collected = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="tracking")
    notes = models.TextField(blank=True)

    source_type = models.CharField(max_length=50, null=True, blank=True,
        help_text="'death_aid', 'medical_aid' or 'external_aid' — the aid that triggered this tracking post")
    source_id = models.IntegerField(null=True, blank=True,
        help_text="PK of the DeathAid/MedicalAid record, or the AssessmentItem for external aid")
    # External-aid linkage: which monthly-deduction item this post collects
    # for, plus a frozen display copy so the queue stays readable even if the
    # assessment is later revised. Internal (member) posts leave these null.
    assessment_item_id_FK = models.ForeignKey(
        "AssessmentItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="assessment_item_id_FK",
        related_name="external_aid_posts",
    )
    external_campus = models.CharField(max_length=120, null=True, blank=True)
    external_beneficiary = models.CharField(max_length=255, null=True, blank=True)

    @property
    def is_external_aid(self) -> bool:
        return (self.source_type or "") == "external_aid"

    @property
    def external_display(self) -> str:
        campus = (self.external_campus or "").strip()
        beneficiary = (self.external_beneficiary or "").strip()
        if campus and beneficiary:
            return f"{campus} — {beneficiary}"
        if self.archive_id_FK and self.archive_id_FK.member_name:
            return self.archive_id_FK.member_name
        return campus or beneficiary or ""

    created_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.SET_NULL,
        null=True,
        db_column="created_by_user_id_FK",
        related_name="aid_posts_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    finish_status = models.CharField(
        max_length=20, blank=True, default="",
        help_text="'' = no request, 'pending_approval' = awaiting President, 'rejected' = rejected, 'pending_release' = awaiting Treasurer fund release, 'pending_auditor' = awaiting Auditor verification, 'pending_president' = awaiting President, 'repayment' = fund released, members still owe"
    )
    finish_skip_remaining = models.BooleanField(
        default=False,
        help_text="Whether to auto-skip unpaid contributions when President approves"
    )
    finish_paid_with_funds = models.BooleanField(
        default=False,
        help_text="True when the post was paid using organizational funds instead of member contributions"
    )
    finish_cycle = models.PositiveSmallIntegerField(
        default=0,
        help_text="0 = initial collection, 1 = first cycle (paid with funds), 2 = repayment close cycle"
    )
    collection_started = models.BooleanField(
        default=False,
        help_text="Whether the treasurer has started collecting contributions for this post"
    )
    deduction_sheet = models.FileField(
        upload_to="deduction_sheets/", null=True, blank=True,
        help_text="Uploaded salary deduction accounting sheet"
    )
    deduction_batch_reference = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Reference or batch number from the salary deduction sheet"
    )
    deduction_payroll_period = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Payroll period covered (e.g. 2026-07)"
    )
    deduction_sheet_uploaded_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the deduction sheet was uploaded"
    )
    deduction_remitted_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Amount deposited from salary deduction remittance"
    )
    deduction_remittance_reference = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Bank reference or deposit slip number for the remittance"
    )
    deduction_remitted_date = models.DateField(
        null=True, blank=True,
        help_text="Date the remittance was deposited"
    )
    deduction_remitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the remittance was recorded in the system"
    )

    class Meta:
        db_table = "aid_tracking_post"
        ordering = ["-created_at"]


class Contribution(models.Model):
    STATUS_NOT_PAID = "NOT_PAID"
    STATUS_RECORDED = "RECORDED"
    STATUS_PENDING_VERIFICATION = "PENDING_VERIFICATION"
    STATUS_PAID = "PAID"
    STATUS_SKIPPED = "SKIPPED"
    STATUS_EXCLUDED_REQUESTER = "EXCLUDED_REQUESTER"

    STATUS_CHOICES = [
        (STATUS_NOT_PAID, "Not Paid"),
        (STATUS_RECORDED, "Recorded"),
        (STATUS_PENDING_VERIFICATION, "Pending Verification"),
        (STATUS_PAID, "Paid"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_EXCLUDED_REQUESTER, "Not Included (Requester)"),
    ]

    contribution_id_PK = models.AutoField(primary_key=True)

    aid_tracking_post_id_FK = models.ForeignKey(
        AidTrackingPost,
        on_delete=models.CASCADE,
        db_column="aid_tracking_post_id_FK",
        related_name="contributions",
    )
    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
    )
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_PAID)
    is_manually_overridden = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    updated_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="updated_by_user_id_FK",
        related_name="contribution_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contribution"
        unique_together = (("aid_tracking_post_id_FK", "member_id_FK"),)


class GlobalAuditTrail(models.Model):
    trail_id = models.AutoField(primary_key=True)

    table_name = models.CharField(max_length=100)
    record_id = models.IntegerField()
    action = models.CharField(max_length=50)
    result = models.CharField(max_length=20, default="Success", blank=True)

    document_archive_id_FK = models.ForeignKey(
        FinancialDocumentArchive,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="document_archive_id_FK",
        related_name="audit_trails",
    )
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)

    actor_type = models.CharField(max_length=50)
    actor_id = models.IntegerField(null=True, blank=True)
    actor_name = models.CharField(max_length=255)

    ip_address = models.GenericIPAddressField(protocol="both", unpack_ipv4=False, null=True, blank=True)
    device_info = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    # default (not auto_now_add) so bulk writes can assign distinct,
    # hash-matching timestamps per entry.
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)

    previous_hash = models.CharField(max_length=64, null=False, blank=False, default="0" * 64)
    entry_hash = models.CharField(max_length=64, null=False, blank=False, default="")
    hmac_signature = models.CharField(max_length=64, null=False, blank=False, default="")

    class Meta:
        db_table = "global_audit_trail"
        indexes = [
            models.Index(fields=["table_name", "record_id", "timestamp"]),
        ]



class SystemSetting(models.Model):
    setting_id_PK = models.AutoField(primary_key=True)
    setting_key = models.CharField(max_length=100, unique=True)
    setting_value = models.TextField()
    updated_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="updated_by_id_FK",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "system_setting"

    def __str__(self):
        return f"{self.setting_key} = {self.setting_value}"


class SensitiveReadLog(models.Model):
    read_id = models.AutoField(primary_key=True, db_column="read_id_PK")

    table_name = models.CharField(max_length=100, db_column="module")
    record_id = models.IntegerField(null=True, blank=True)

    reader_type = models.CharField(max_length=50, db_column="purpose", default="")
    reader_id = models.IntegerField(null=True, blank=True, db_column="user_id_FK")

    device_info = models.CharField(max_length=255, null=True, blank=True)

    read_at = models.DateTimeField(auto_now_add=True, db_column="timestamp")

    class Meta:
        db_table = "sensitive_read_log"
        indexes = [
            models.Index(fields=["table_name", "record_id"]),
            models.Index(fields=["read_at"]),
        ]


class FundTransaction(models.Model):
    SOURCE_TYPES = [
        ("payroll_batch", "Payroll Batch"),
        ("death_aid", "Death Aid Disbursement"),
        ("medical_aid", "Medical Aid Disbursement"),
        ("membership_fee", "Membership Fee"),
        ("monthly_dues", "Monthly Dues"),
        ("aid_setaside_medical", "Medical Aid Set-Aside"),
        ("aid_setaside_death", "Death Aid Set-Aside"),
        ("contribution", "Contribution"),
        ("manual_adjustment", "Manual Adjustment"),
        ("aid_post_payment", "Aid Post Fund Payment"),
        ("salary_deduction_remittance", "Salary Deduction Remittance"),
        ("other_transaction", "Other Transaction"),
    ]
    DIRECTION_CHOICES = [("inflow", "Inflow"), ("outflow", "Outflow")]

    transaction_id_PK = models.AutoField(primary_key=True)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPES)
    source_id = models.IntegerField(help_text="FK to the source record")
    description = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=100, null=True, blank=True, help_text="Official reference / OR number")

    recorded_by_user_id_FK = models.ForeignKey(
        "OfficerUser",
        on_delete=models.RESTRICT,
        db_column="recorded_by_user_id_FK",
        related_name="fund_transactions",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fund_transaction"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["direction"]),
            models.Index(fields=["source_type", "source_id"]),
            # Hot path: newest-first scans/slices (movements, ledger,
            # trends) and recorded_at range filters (summaries).
            models.Index(fields=["-recorded_at"]),
        ]

    @staticmethod
    def get_balance():
        from django.db.models import Sum, Q
        totals = FundTransaction.objects.aggregate(
            total_in=Sum("amount", filter=Q(direction="inflow")),
            total_out=Sum("amount", filter=Q(direction="outflow")),
        )
        return (totals["total_in"] or 0) - (totals["total_out"] or 0)


class BudgetLine(models.Model):
    """Annual budget per category, set by officers for budget-vs-actual reporting."""

    CATEGORY_CHOICES = [
        ("monthly_dues", "Monthly Dues Collections"),
        ("membership_fee", "Membership Fees"),
        ("contributions", "Contributions"),
        ("aid_medical", "Medical Aid Payouts"),
        ("aid_death", "Death Aid Payouts"),
        ("operations", "Operations & Other Outflows"),
    ]

    budget_line_id_PK = models.AutoField(primary_key=True)
    fiscal_year = models.IntegerField(help_text="YYYY")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "budget_line"
        ordering = ["fiscal_year", "category"]
        constraints = [
            models.UniqueConstraint(fields=["fiscal_year", "category"], name="uniq_budget_year_category"),
        ]


class PayrollBatch(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Auditor Verified", "Auditor Verified"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
        ("Returned for Revision", "Returned for Revision"),
    ]

    batch_id_PK = models.AutoField(primary_key=True)
    payroll_period = models.CharField(max_length=7, help_text="YYYY-MM")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    member_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    hardcopy_reference = models.CharField(max_length=100, null=True, blank=True)

    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="Pending")
    recorded_by_user_id_FK = models.ForeignKey(
        "OfficerUser",
        on_delete=models.RESTRICT,
        db_column="recorded_by_user_id_FK",
        related_name="payroll_batches_recorded",
    )

    auditor_verified_by_user_id_FK = models.ForeignKey(
        "OfficerUser", null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="auditor_verified_by_user_id_FK",
        related_name="payroll_batches_verified",
    )
    auditor_verified_at = models.DateTimeField(null=True, blank=True)
    auditor_remarks = models.TextField(null=True, blank=True)
    returned_by_user_id_FK = models.ForeignKey(
        "OfficerUser", null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="returned_by_user_id_FK",
        related_name="payroll_batches_returned",
    )
    returned_reason = models.TextField(null=True, blank=True)

    president_approved_by_user_id_FK = models.ForeignKey(
        "OfficerUser", null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="president_approved_by_user_id_FK",
        related_name="payroll_batches_approved",
    )
    president_approved_at = models.DateTimeField(null=True, blank=True)
    president_remarks = models.TextField(null=True, blank=True)

    archive_id_FK = models.ForeignKey(
        "TransactionArchive", null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="archive_id_FK",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payroll_batch"
        ordering = ["-created_at"]


class PayrollDeduction(models.Model):
    CATEGORY_CHOICES = [
        ("monthly_dues", "Monthly Dues"),
        ("membership_fee", "Membership Fee"),
        ("aid_contribution", "Aid Contribution"),
    ]
    FUND_IMPACT_CHOICES = [
        ("inflow", "Inflow — replenishes the fund"),
        ("none", "No fund impact — direct pass-through deduction"),
    ]

    deduction_id_PK = models.AutoField(primary_key=True)
    batch_id_FK = models.ForeignKey(
        PayrollBatch,
        on_delete=models.CASCADE,
        db_column="batch_id_FK",
        related_name="deductions",
    )
    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    fund_impact = models.CharField(
        max_length=10, choices=FUND_IMPACT_CHOICES, default="inflow",
        help_text="'inflow' if replenishes fund, 'none' if direct pass-through",
    )

    month_covered = models.CharField(max_length=7, null=True, blank=True, help_text="YYYY-MM for monthly_dues")
    aid_tracking_post_id_FK = models.ForeignKey(
        "AidTrackingPost", null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column="aid_tracking_post_id_FK",
        help_text="Links to the aid disbursement this contribution repays",
    )

    notes = models.TextField(blank=True)

    class Meta:
        db_table = "payroll_deduction"
        indexes = [
            models.Index(fields=["batch_id_FK", "category"]),
            models.Index(fields=["member_id_FK"]),
        ]


class BackupJob(models.Model):
    STATUS_PENDING = "Pending"
    STATUS_COMPLETED = "Completed"
    STATUS_FAILED = "Failed"

    TYPE_DB = "db"
    TYPE_MEDIA = "media"
    TYPE_CONFIG = "config"
    TYPE_SYSTEM = "system"

    job_id = models.AutoField(primary_key=True)

    backup_type = models.CharField(max_length=20, choices=[
        (TYPE_DB, "Database"),
        (TYPE_MEDIA, "Media"),
        (TYPE_CONFIG, "Config"),
        (TYPE_SYSTEM, "System Codebase"),
    ])

    backup_status = models.CharField(max_length=20, choices=[
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ], default=STATUS_PENDING)

    created_at = models.DateTimeField(auto_now_add=True)

    db_dump_path = models.CharField(max_length=500, null=True, blank=True)
    media_archive_path = models.CharField(max_length=500, null=True, blank=True)
    system_archive_path = models.CharField(max_length=500, null=True, blank=True)

    metadata_json = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "backup_job"
        ordering = ["-created_at"]


class OutgoingEmail(models.Model):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (SENT, "Sent"),
        (FAILED, "Failed"),
    ]

    outgoing_email_id = models.AutoField(primary_key=True)
    recipient_list = models.JSONField(default=list)
    subject = models.CharField(max_length=255)
    html_template = models.CharField(max_length=255)
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    retry_count = models.IntegerField(default=0)

    class Meta:
        db_table = "outgoing_email"
        ordering = ["created_at"]


class Event(models.Model):
    STATUS_UPCOMING = "Upcoming"
    STATUS_ONGOING = "Ongoing"
    STATUS_COMPLETED = "Completed"
    STATUS_CANCELLED = "Cancelled"

    STATUS_CHOICES = [
        (STATUS_UPCOMING, "Upcoming"),
        (STATUS_ONGOING, "Ongoing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    event_id_PK = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=255)
    event_date = models.DateField()
    event_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    event_type = models.CharField(max_length=100)  # General Assembly, Monthly Meeting, Seminar, etc.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPCOMING)
    attendance_open = models.BooleanField(default=False)
    attendance_closed = models.BooleanField(default=False)
    quorum_required = models.IntegerField(default=60)  # Percentage
    quorum_reached = models.BooleanField(default=False)
    # Certificate-related fields
    given_place = models.CharField(max_length=255, blank=True, help_text="Place where certificate is given")
    certificate_issue_date = models.DateField(null=True, blank=True, help_text="Date certificate is issued")
    auto_generate_certificates = models.BooleanField(default=False, help_text="Automatically generate certificates on event completion")
    certificate_prefix = models.CharField(max_length=20, blank=True, default="ISUCauFA-ATT", help_text="Prefix for certificate numbers")
    created_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="created_by_user_id_FK",
        related_name="created_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "event"
        ordering = ["-event_date", "-event_time"]


class Document(models.Model):
    DOCUMENT_TYPE_CONSTITUTION = "Constitution"
    DOCUMENT_TYPE_BYLAWS = "By-Laws"
    DOCUMENT_TYPE_MINUTES = "Minutes of Meeting"
    DOCUMENT_TYPE_MEMORANDUM = "Memorandum"
    DOCUMENT_TYPE_OFFICE_ORDER = "Office Order"
    DOCUMENT_TYPE_RESOLUTION = "Resolution"
    DOCUMENT_TYPE_CIRCULAR = "Circular"
    DOCUMENT_TYPE_ACTIVITY_REPORT = "Activity Report"
    DOCUMENT_TYPE_FINANCIAL = "Financial Document"
    DOCUMENT_TYPE_CERTIFICATE = "Certificate"
    DOCUMENT_TYPE_OTHER = "Other"

    DOCUMENT_TYPE_CHOICES = [
        (DOCUMENT_TYPE_CONSTITUTION, "Constitution"),
        (DOCUMENT_TYPE_BYLAWS, "By-Laws"),
        (DOCUMENT_TYPE_MINUTES, "Minutes of Meeting"),
        (DOCUMENT_TYPE_MEMORANDUM, "Memorandum"),
        (DOCUMENT_TYPE_OFFICE_ORDER, "Office Order"),
        (DOCUMENT_TYPE_RESOLUTION, "Resolution"),
        (DOCUMENT_TYPE_CIRCULAR, "Circular"),
        (DOCUMENT_TYPE_ACTIVITY_REPORT, "Activity Report"),
        (DOCUMENT_TYPE_FINANCIAL, "Financial Document"),
        (DOCUMENT_TYPE_CERTIFICATE, "Certificate"),
        (DOCUMENT_TYPE_OTHER, "Other"),
    ]

    document_id_PK = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES)
    category = models.CharField(max_length=100, blank=True)
    keywords = models.CharField(max_length=500, blank=True)
    tags = models.CharField(max_length=500, blank=True)
    file_path = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=50, blank=True)
    # Raw sha256 of stored bytes ("imgnorm:<hex>" for normalized image
    # duplicates). Used by secure_upload.find_duplicate_upload so the same
    # image cannot be archived twice under a different name/metadata.
    content_sha256 = models.CharField(max_length=80, null=True, blank=True, db_index=True)
    version = models.CharField(max_length=20, default="1.0")
    uploaded_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="uploaded_by_user_id_FK",
        related_name="uploaded_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    retention_period = models.DateField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    is_public_visible = models.BooleanField(default=False)

    class Meta:
        db_table = "document"
        ordering = ["-uploaded_at"]


class Category(models.Model):
    category_id_PK = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    role = models.CharField(max_length=50, default='Secretary')  # Track which role created this category
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = "category"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AnnouncementCategory(models.Model):
    category_id_PK = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = "announcement_category"
        ordering = ["name"]

    def __str__(self):
        return self.name


class EventType(models.Model):
    event_type_id_PK = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = "event_type"
        ordering = ["name"]

    def __str__(self):
        return self.name


class DocumentPin(models.Model):
    document_id_FK = models.ForeignKey(Document, on_delete=models.CASCADE, db_column="document_id_FK", related_name="pins")
    officer_id_FK = models.ForeignKey(OfficerUser, on_delete=models.CASCADE, db_column="officer_id_FK", related_name="document_pins")
    pinned_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = "document_pin"
        unique_together = [["document_id_FK", "officer_id_FK"]]


class DocumentActivity(models.Model):
    activity_id = models.AutoField(primary_key=True)
    document_id_FK = models.ForeignKey(Document, on_delete=models.CASCADE, null=True, blank=True, db_column="document_id_FK", related_name="activities")
    action = models.CharField(max_length=50)
    officer_id_FK = models.ForeignKey(OfficerUser, on_delete=models.SET_NULL, null=True, blank=True, db_column="officer_id_FK")
    officer_name = models.CharField(max_length=255, blank=True)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = "document_activity"
        ordering = ["-timestamp"]


class Minutes(models.Model):
    STATUS_DRAFT = "Draft"
    STATUS_PENDING = "Pending"
    STATUS_FINALIZED = "Finalized"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending"),
        (STATUS_FINALIZED, "Finalized"),
    ]

    minutes_id_PK = models.AutoField(primary_key=True)
    meeting_title = models.CharField(max_length=255)
    meeting_date = models.DateField()
    venue = models.CharField(max_length=255)
    attendees = models.TextField(blank=True)
    agenda = models.TextField(blank=True)
    minutes_content = models.TextField()
    prepared_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="prepared_by_user_id_FK",
        related_name="prepared_minutes",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    event_id_FK = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="event_id_FK",
        related_name="meeting_minutes",
    )
    document_id_FK = models.ForeignKey(
        Document,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="document_id_FK",
        related_name="related_minutes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "minutes"
        ordering = ["-meeting_date"]


class Announcement(models.Model):
    CATEGORY_MEETING = "Meeting Notice"
    CATEGORY_EVENT = "Event Announcement"
    CATEGORY_GENERAL = "General Announcement"
    CATEGORY_UPDATE = "Organization Update"

    CATEGORY_CHOICES = [
        (CATEGORY_MEETING, "Meeting Notice"),
        (CATEGORY_EVENT, "Event Announcement"),
        (CATEGORY_GENERAL, "General Announcement"),
        (CATEGORY_UPDATE, "Organization Update"),
    ]

    announcement_id_PK = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField()
    attachment_path = models.CharField(max_length=500, blank=True)
    attachment_name = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="announcements/%Y/%m/", null=True, blank=True)
    published_by_user_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="published_by_user_id_FK",
        related_name="published_announcements",
    )
    is_active = models.BooleanField(default=True)
    published_at = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "announcement"
        ordering = ["-published_at"]


class CertificateSettings(models.Model):
    """Stores signature and certificate configuration for automatic generation"""
    settings_id_PK = models.AutoField(primary_key=True)
    president_name = models.CharField(max_length=255, help_text="Name of ISUCauFA President")
    president_position = models.CharField(max_length=255, default="ISUCauFA President")
    president_signature = models.ImageField(upload_to='signatures/', null=True, blank=True, help_text="Upload PNG with transparent background")
    secretary_name = models.CharField(max_length=255, help_text="Name of ISUCauFA Secretary")
    secretary_position = models.CharField(max_length=255, default="ISUCauFA, Inc. Secretary")
    secretary_signature = models.ImageField(upload_to='signatures/', null=True, blank=True, help_text="Upload PNG with transparent background")
    faculty_regent_name = models.CharField(max_length=255, blank=True, help_text="Name of Faculty Regent or Authorized Official")
    faculty_regent_position = models.CharField(max_length=255, default="Faculty Regent")
    faculty_regent_signature = models.ImageField(upload_to='signatures/', null=True, blank=True, help_text="Upload PNG with transparent background")
    organization_logo = models.ImageField(upload_to='logos/', null=True, blank=True, help_text="Organization logo for certificate")
    header_text = models.CharField(max_length=255, default="Republic of the Philippines")
    footer_text = models.TextField(blank=True, help_text="Optional footer text for certificate")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "certificate_settings"
        verbose_name_plural = "Certificate Settings"


class Certificate(models.Model):
    """Tracks generated certificates for events"""
    STATUS_PENDING = "Pending"
    STATUS_SENT = "Sent"
    STATUS_FAILED = "Failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    certificate_id_PK = models.AutoField(primary_key=True)
    certificate_number = models.CharField(max_length=50, unique=True)
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        db_column="member_id_FK",
        related_name="certificates"
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        db_column="event_id_FK",
        related_name="certificates"
    )
    pdf_file = models.FileField(upload_to='certificates/', null=True, blank=True)
    email_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "certificate"
        ordering = ["-generated_at"]
        unique_together = [['member', 'event']]


class Album(models.Model):
    album_id_PK = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover_photo = models.ForeignKey(
        "Photo", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    event = models.ForeignKey(
        "Event", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="albums",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        OfficerUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_albums",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "album"
        ordering = ["-created_at"]


class Photo(models.Model):
    photo_id_PK = models.AutoField(primary_key=True)
    album = models.ForeignKey(
        Album, on_delete=models.CASCADE, related_name="photos",
    )
    image = models.ImageField(upload_to="gallery/%Y/%m/")
    caption = models.CharField(max_length=255, blank=True)
    is_featured = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        OfficerUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="uploaded_photos",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "photo"
        ordering = ["-uploaded_at"]


class OfficerProfile(models.Model):
    """PIO-owned officer directory entry shown on the public Officers page.

    Independent from OfficerUser (dashboard login accounts managed by the
    President). The PIO manages these profiles directly.
    """

    officer_profile_id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255)
    position = models.CharField(max_length=100)
    category = models.CharField(
        max_length=50,
        choices=[
            ("Executive Officer", "Executive Officer"),
            ("Board of Directors", "Board of Directors"),
            ("Adviser", "Adviser"),
        ],
        default="Executive Officer",
    )
    department = models.CharField(max_length=255, null=True, blank=True)
    school_year = models.CharField(max_length=50, null=True, blank=True)
    term_start = models.DateField(null=True, blank=True)
    term_end = models.DateField(null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    facebook = models.URLField(null=True, blank=True)
    biography = models.TextField(null=True, blank=True)
    photo = models.ImageField(upload_to="officer_profiles/", null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("Active", "Active"), ("Inactive", "Inactive")],
        default="Active",
    )
    created_by = models.ForeignKey(
        OfficerUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_officer_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "officer_profile"
        ordering = ["category", "position", "full_name"]


class NewsCategory(models.Model):
    """Categories for organizing News & Highlights content."""
    
    category_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "news_category"
        ordering = ["order", "name"]
        verbose_name_plural = "News Categories"

    def __str__(self):
        return self.name


class NewsArticle(models.Model):
    """News & Highlights articles with full content, galleries, and videos."""
    
    news_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    category = models.ForeignKey(
        NewsCategory, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="articles",
    )
    summary = models.TextField(max_length=500, help_text="Brief summary for article cards")
    content = models.TextField(help_text="Full article content (supports HTML)")
    featured_image = models.ImageField(upload_to="news/%Y/%m/", null=True, blank=True)
    
    # Event information (optional)
    event_date = models.DateField(null=True, blank=True)
    event_time = models.TimeField(null=True, blank=True)
    venue = models.CharField(max_length=255, blank=True)
    
    # Media
    video_url = models.URLField(blank=True, help_text="YouTube or other video platform URL")
    video_thumbnail = models.ImageField(upload_to="news/%Y/%m/", null=True, blank=True)
    
    # Publication settings
    is_featured = models.BooleanField(default=False, help_text="Show in featured news section")
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    
    # Author tracking
    author = models.ForeignKey(
        OfficerUser, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="authored_news",
    )
    
    # Metadata
    view_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "news_article"
        ordering = ["-published_at", "-created_at"]
        verbose_name = "News Article"
        verbose_name_plural = "News Articles"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or f"news-{self.news_id}"
            self.slug = base
            exists = NewsArticle.objects.filter(slug=self.slug).exists()
            suffix = 2
            while exists:
                self.slug = f"{base}-{suffix}"
                suffix += 1
                exists = NewsArticle.objects.filter(slug=self.slug).exists()
        super().save(*args, **kwargs)


class NewsGallery(models.Model):
    """Photo galleries associated with news articles."""
    
    gallery_id = models.AutoField(primary_key=True)
    article = models.ForeignKey(
        NewsArticle, on_delete=models.CASCADE, related_name="galleries",
    )
    caption = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to="news/%Y/%m/")
    is_featured = models.BooleanField(default=False, help_text="Featured image in article gallery")
    order = models.IntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "news_gallery"
        ordering = ["order", "-uploaded_at"]
        verbose_name_plural = "News Galleries"

    def __str__(self):
        return f"{self.article.title} - {self.caption or 'Untitled'}"


class HeroSlide(models.Model):
    """Standalone homepage hero carousel slides managed by the PIO."""

    hero_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    subtitle = models.TextField(max_length=500, blank=True, help_text="Short text shown on the slide")
    image = models.ImageField(upload_to="hero/%Y/%m/", null=True, blank=True)
    button_text = models.CharField(max_length=50, default="Read More")
    button_url = models.CharField(max_length=500, blank=True, help_text="Internal or external link for the slide button")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, help_text="Show on the homepage hero carousel")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hero_slide"
        ordering = ["sort_order", "-created_at"]
        verbose_name = "Hero Slide"
        verbose_name_plural = "Hero Slides"

    def __str__(self):
        return self.title

    def __str__(self):
        return self.full_name



# ============================================================================
# MONTHLY DEDUCTION ASSESSMENT WORKFLOW (additive module)
#
# President defines a monthly assessment with a per-purpose breakdown,
# Treasurer records each member's actual deduction, the system auto-allocates
# the deduction across the breakdown items by priority, the Auditor verifies,
# and the President gives final approval which triggers member email notices.
# ============================================================================


class MonthlyAssessment(models.Model):
    """President-defined monthly deduction assessment for all members."""

    STATUS_DRAFT = "draft"
    STATUS_PENDING_TREASURER = "pending_treasurer"
    STATUS_PENDING_DEPOSIT = "pending_deposit"
    STATUS_PENDING_AUDIT = "pending_audit"
    STATUS_PENDING_FINAL = "pending_final"
    STATUS_FINAL_APPROVED = "final_approved"
    STATUS_REJECTED = "rejected"
    STATUS_RETURNED = "returned"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING_TREASURER, "Pending Treasurer Review"),
        (STATUS_PENDING_DEPOSIT, "Pending Deposit"),
        (STATUS_PENDING_AUDIT, "Pending Auditor Verification"),
        (STATUS_PENDING_FINAL, "Pending President Approval"),
        (STATUS_FINAL_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected by Auditor"),
        (STATUS_RETURNED, "Returned by President"),
    ]

    assessment_id_PK = models.AutoField(primary_key=True)
    month = models.DateField(
        unique=True,
        help_text="First day of the covered month (e.g. 2026-09-01 for September 2026).",
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    # Treasurer's deposit of the recorded collection: reference-only evidence
    # (the fund is NOT booked here — FundTransaction rows are written only on
    # final approval). Cleared (fields nulled, slips kept) when the Auditor
    # rejects or the President returns the month.
    deposit_reference = models.CharField(max_length=100, null=True, blank=True)
    deposited_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deposited_at = models.DateTimeField(null=True, blank=True)
    deposited_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="deposited_by_id_FK",
        related_name="monthly_assessments_deposited",
    )

    created_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="created_by_id_FK",
        related_name="monthly_assessments_created",
    )

    treasurer_remarks = models.TextField(null=True, blank=True)
    auditor_remarks = models.TextField(null=True, blank=True)
    president_remarks = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "monthly_assessments"
        ordering = ["-month"]
        indexes = [
            models.Index(fields=["status", "month"]),
        ]

    def __str__(self):
        return f"Monthly Assessment {self.month.strftime('%B %Y')} ({self.total_amount})"

    @property
    def month_label(self) -> str:
        return self.month.strftime("%B %Y")


def assessment_document_upload_path(instance, filename):
    return f"assessment_documents/{instance.kind}/{filename}"


class MonthlyAssessmentDocument(models.Model):
    """One scanned image attached to a monthly assessment.

    The President attaches the signed ISUCauFA request letter and the source
    deducted-amount sheet as images — several per kind, since a multi-page
    scan is common. The Treasurer and Auditor view them read-only.
    """

    KIND_REQUEST_LETTER = "request_letter"
    KIND_DEDUCTION_SHEET = "deduction_sheet"
    KIND_DEPOSIT_SLIP = "deposit_slip"
    KIND_CHOICES = [
        (KIND_REQUEST_LETTER, "Request Letter"),
        (KIND_DEDUCTION_SHEET, "Deducted Amount Sheet"),
        (KIND_DEPOSIT_SLIP, "Deposit Slip"),
    ]

    document_id_PK = models.AutoField(primary_key=True)
    assessment_id_FK = models.ForeignKey(
        MonthlyAssessment,
        on_delete=models.CASCADE,
        db_column="assessment_id_FK",
        related_name="documents",
    )
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    image = models.FileField(
        upload_to=assessment_document_upload_path,
        max_length=500,
        validators=[FileExtensionValidator(
            allowed_extensions=["jpg", "jpeg", "png", "webp", "gif", "pdf"]
        )],
    )
    # Raw sha256 of the stored bytes + metadata-insensitive image fingerprint
    # (see core_system.secure_upload). The upload endpoints reject a file
    # whose hashes already exist on the same assessment, so one scan cannot
    # be attached twice (or as both the letter and the sheet).
    content_sha256 = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    norm_sha256 = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    uploaded_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="uploaded_by_id_FK",
        related_name="assessment_documents_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "monthly_assessment_documents"
        ordering = ["uploaded_at", "document_id_PK"]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.document_id_PK} for assessment {self.assessment_id_FK_id}"


class AssessmentItem(models.Model):
    """One breakdown line of a monthly assessment (e.g. monthly due, aid fund)."""

    PURPOSE_MONTHLY_DUE = "monthly_due"
    PURPOSE_MEDICAL_AID = "medical_aid_fund"
    PURPOSE_DEATH_AID = "death_aid_fund"
    # Retired purpose. The President can no longer add a Token Incentive line;
    # the constant and the label below only keep rows saved before the change
    # readable (and their assessments' totals intact).
    PURPOSE_TOKEN_INCENTIVE = "token_incentive"
    PURPOSE_OTHER = "other"

    PURPOSE_CHOICES = [
        (PURPOSE_MONTHLY_DUE, "Monthly Due"),
        (PURPOSE_MEDICAL_AID, "Medical Aid Fund"),
        (PURPOSE_DEATH_AID, "Death Aid Fund"),
        (PURPOSE_OTHER, "Other"),
    ]

    # Purposes that were removed from PURPOSE_CHOICES but still exist on
    # historical rows — get_purpose_display() would echo the raw key instead.
    LEGACY_PURPOSE_LABELS = {
        PURPOSE_TOKEN_INCENTIVE: "Token Incentive",
    }

    item_id_PK = models.AutoField(primary_key=True)
    assessment_id_FK = models.ForeignKey(
        MonthlyAssessment,
        on_delete=models.CASCADE,
        db_column="assessment_id_FK",
        related_name="items",
    )
    purpose = models.CharField(max_length=100, choices=PURPOSE_CHOICES)
    custom_label = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text=(
            "Required when purpose is 'other'. For standard purposes, an "
            "optional specifier such as the covered period — e.g. two "
            "'Monthly Due' lines distinguished as 'July 2026' and 'August 2026'."
        ),
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    recipient = models.CharField(max_length=255, null=True, blank=True)
    # Cross-campus aid declaration (President, from the very start):
    # internal items point at a local member via `recipient`; external items
    # collect from Cauayan members but turn over to another campus. The money
    # flow is identical — only the linkage and the release path differ, so the
    # release queue can never mistake external cash for a member's claim.
    RECIPIENT_MEMBER = "member"
    RECIPIENT_EXTERNAL = "external"
    RECIPIENT_TYPE_CHOICES = [
        (RECIPIENT_MEMBER, "Member (internal)"),
        (RECIPIENT_EXTERNAL, "Other Campus (external)"),
    ]
    recipient_type = models.CharField(
        max_length=20, choices=RECIPIENT_TYPE_CHOICES, default=RECIPIENT_MEMBER
    )
    external_campus = models.CharField(max_length=120, null=True, blank=True)
    external_beneficiary = models.CharField(max_length=255, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    priority_order = models.IntegerField(
        default=1,
        help_text="Lower numbers are funded first when a member's deduction is partial.",
    )

    class Meta:
        db_table = "assessment_items"
        ordering = ["priority_order", "item_id_PK"]

    def __str__(self):
        return f"{self.label} - {self.amount}"

    @property
    def is_external_aid(self) -> bool:
        return self.recipient_type == self.RECIPIENT_EXTERNAL

    @property
    def external_display(self) -> str:
        if not self.is_external_aid:
            return self.recipient or ""
        campus = (self.external_campus or "").strip()
        beneficiary = (self.external_beneficiary or "").strip()
        if campus and beneficiary:
            return f"{campus} — {beneficiary}"
        return self.recipient or campus or beneficiary or ""

    @property
    def label(self) -> str:
        """Display name: base purpose plus the specific name/period when given."""
        base = self.custom_label or self.purpose_display()
        if self.purpose == self.PURPOSE_OTHER and self.custom_label:
            return self.custom_label
        if self.custom_label and self.purpose != self.PURPOSE_OTHER:
            return f"{self.purpose_display()} ({self.custom_label})"
        return base

    def purpose_display(self) -> str:
        """Human label, including retired purposes kept for historical rows."""
        return self.LEGACY_PURPOSE_LABELS.get(self.purpose) or self.get_purpose_display()


class MemberAssessment(models.Model):
    """Treasurer-recorded actual deduction for one member under one assessment."""

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_APPROVED = "approved"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Verification"),
        (STATUS_VERIFIED, "Verified by Auditor"),
        (STATUS_APPROVED, "Approved"),
    ]

    member_assessment_id_PK = models.AutoField(primary_key=True)
    assessment_id_FK = models.ForeignKey(
        MonthlyAssessment,
        on_delete=models.CASCADE,
        db_column="assessment_id_FK",
        related_name="member_assessments",
    )
    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.RESTRICT,
        db_column="member_id_FK",
        related_name="monthly_assessment_deductions",
    )
    standard_assessment = models.DecimalField(max_digits=10, decimal_places=2)
    actual_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # Carry-over snapshot: the unpaid balance from the member's previous
    # approved month that was still collectible when this record was made.
    prior_outstanding = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    prior_outstanding_collected = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    prior_month = models.CharField(max_length=50, null=True, blank=True)

    # Month context of the pooled carry-over, frozen at recording time so the
    # balance keeps its "which months" identity as it rolls forward:
    #   prior_months          — the unpaid months this row's prior_outstanding
    #                           is made of, oldest first
    #                           ([{key, label, amount}]; sums to prior_outstanding).
    #   prior_collected_months — how prior_outstanding_collected was applied
    #                           across those months ([{key, label, amount}];
    #                           sums to prior_outstanding_collected). Rows
    #                           recorded before this existed have no breakdown
    #                           and fall back to oldest-first FIFO attribution.
    prior_months = models.JSONField(null=True, blank=True)
    prior_collected_months = models.JSONField(null=True, blank=True)

    # "Change": money actually deducted from the member's salary beyond what
    # was applied to breakdown items and prior balance. It is booked to the
    # ISUCauFA funds with the month's inflow (never double-booked) and shown
    # for reporting; it does not reduce other months' balances.
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # True when the Treasurer left this member out of the collection batch
    # ("Exclude from Batch"): nothing was deducted, but the member still owes
    # the month, so the row carries the full expected balance forward and
    # stays visible to the Auditor and President as unpaid.
    is_excluded = models.BooleanField(default=False)

    recorded_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="recorded_by_id_FK",
        related_name="member_assessments_recorded",
    )
    verified_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="verified_by_id_FK",
        related_name="member_assessments_verified",
    )
    approved_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="approved_by_id_FK",
        related_name="member_assessments_approved",
    )

    recorded_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "member_assessments"
        ordering = ["member_id_FK__full_name"]
        unique_together = [("assessment_id_FK", "member_id_FK")]
        indexes = [
            models.Index(fields=["member_id_FK", "status", "assessment_id_FK"]),
        ]

    def __str__(self):
        return f"{self.member_id_FK.full_name} - {self.assessment_id_FK.month_label}: {self.actual_deduction}"


class MemberCatchupDue(models.Model):
    """A past monthly-due obligation created for a member after a month closed.

    Closed assessments must remain immutable: adding a newly enrolled member to
    one would make its original deposit and approval totals disagree.  This
    record preserves the month and amount owed, then lets the Treasurer settle
    it as part of a later open assessment.
    """

    catchup_due_id_PK = models.AutoField(primary_key=True)
    member_id_FK = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        db_column="member_id_FK",
        related_name="catchup_dues",
    )
    month = models.DateField(
        help_text="First day of the historical month covered by this catch-up due.",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="created_by_id_FK",
        related_name="member_catchup_dues_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "member_catchup_dues"
        ordering = ["month", "catchup_due_id_PK"]
        unique_together = [("member_id_FK", "month")]
        indexes = [models.Index(fields=["member_id_FK", "month"])]

    def __str__(self):
        return f"{self.member_id_FK.full_name} - catch-up {self.month:%B %Y}: {self.amount}"


class MemberAssessmentAllocation(models.Model):
    """Auto-calculated split of a member's deduction across assessment items."""

    allocation_id_PK = models.AutoField(primary_key=True)
    member_assessment_id_FK = models.ForeignKey(
        MemberAssessment,
        on_delete=models.CASCADE,
        db_column="member_assessment_id_FK",
        related_name="allocations",
    )
    assessment_item_id_FK = models.ForeignKey(
        AssessmentItem,
        on_delete=models.RESTRICT,
        db_column="assessment_item_id_FK",
        related_name="allocations",
    )
    amount_applied = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    amount_remaining = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "member_assessment_allocations"
        ordering = ["assessment_item_id_FK__priority_order", "allocation_id_PK"]
        unique_together = [("member_assessment_id_FK", "assessment_item_id_FK")]

    def __str__(self):
        return f"Allocation {self.allocation_id_PK}: applied {self.amount_applied} / remaining {self.amount_remaining}"


class AidSetAside(models.Model):
    """Earmarked medical/death-aid portion of one member's approved deduction.

    Created alongside the FundTransaction inflow rows the President books at
    final approval: the month's cash is split so the dues portion reads as
    ``monthly_dues`` and each aid-purpose portion reads as its own inflow
    (``aid_setaside_medical`` / ``aid_setaside_death``). Cash still lands in
    the bank as one deposit — these rows only separate *what the money is for*.

    One row per aid AssessmentItem the member actually funded, so the earmark
    keeps the item's recipient and can be pointed at that recipient's claim
    (``aid_tracking_post_id_FK``). The Release Queue sums the linked rows to
    show how much is set aside against a pending claim, and a release draws
    them down oldest-first (``amount_released``), falling back to the general
    fund for anything the set-aside does not cover.
    """

    AID_TYPE_CHOICES = [
        ("medical_aid", "Medical Aid"),
        ("death_aid", "Death Aid"),
    ]

    setaside_id_PK = models.AutoField(primary_key=True)
    member_assessment_id_FK = models.ForeignKey(
        MemberAssessment,
        on_delete=models.CASCADE,
        db_column="member_assessment_id_FK",
        related_name="aid_set_asides",
    )
    assessment_item_id_FK = models.ForeignKey(
        AssessmentItem,
        on_delete=models.RESTRICT,
        db_column="assessment_item_id_FK",
        related_name="set_asides",
    )
    fund_transaction_id_FK = models.ForeignKey(
        FundTransaction,
        on_delete=models.CASCADE,
        db_column="fund_transaction_id_FK",
        related_name="aid_set_asides",
    )
    # The claim this earmark feeds. Null while no claim exists yet for the
    # recipient — it is back-linked when the President approves the claim.
    aid_tracking_post_id_FK = models.ForeignKey(
        AidTrackingPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="aid_tracking_post_id_FK",
        related_name="aid_set_asides",
    )
    aid_type = models.CharField(max_length=20, choices=AID_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    amount_released = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "aid_set_asides"
        ordering = ["setaside_id_PK"]
        unique_together = [("member_assessment_id_FK", "assessment_item_id_FK")]
        indexes = [
            models.Index(fields=["aid_type", "aid_tracking_post_id_FK"]),
        ]

    @property
    def amount_available(self) -> Decimal:
        return self.amount - self.amount_released

    @property
    def is_fully_released(self) -> bool:
        return self.amount_released >= self.amount

    def __str__(self):
        return (
            f"Set-aside {self.setaside_id_PK}: {self.aid_type} "
            f"{self.amount} (released {self.amount_released})"
        )


class AssessmentWorkflowLog(models.Model):
    """Audit trail of who did what in the monthly deduction workflow."""

    assessment_id_FK = models.ForeignKey(
        MonthlyAssessment,
        on_delete=models.CASCADE,
        db_column="assessment_id_FK",
        related_name="workflow_logs",
    )
    action = models.CharField(max_length=50)
    performed_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="performed_by_id_FK",
        related_name="assessment_workflow_actions",
    )
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "workflow_logs"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.assessment_id_FK.month_label}: {self.action}"


# ---------------------------------------------------------------------------
# Officer feedback forms (Superadmin-authored, shown on officer dashboards)
# ---------------------------------------------------------------------------

FEEDBACK_QUESTION_TYPES = (
    ("mc", "Multiple choice"),
    ("likert", "Likert scale"),
    ("text", "Freeform text"),
)

# Roles that can ever be shown a feedback form. Members are deliberately
# excluded: this is an officer-facing instrument.
FEEDBACK_ROLES = (
    "President",
    "Treasurer",
    "Auditor",
    "Secretary",
    "Public Information Officer",
    "Superadmin",
    "System",
)

# Hard cap on a single freeform answer. Keeps one verbose response from
# blowing out a report page or a PDF.
FEEDBACK_TEXT_MAX = 2000

FEEDBACK_TEXT_MIN = 1


class FeedbackForm(models.Model):
    """A feedback instrument authored by the Superadmin."""

    form_id_PK = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200)
    # Card header shown on the dashboards; editable independently of the title.
    section_title = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_open = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    show_on_roles = models.JSONField(default=list, blank=True)
    created_by_id_FK = models.ForeignKey(
        OfficerUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="created_by_id_FK",
        related_name="feedback_forms_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "feedback_form"
        ordering = ["-is_active", "-created_at"]

    def __str__(self):
        return self.title

    def applies_to(self, role: str) -> bool:
        """True when this form should render for an officer holding `role`."""
        if not self.is_active or self.is_archived or not self.is_open:
            return False
        roles = self.show_on_roles or []
        if not roles:
            return False
        needle = (role or "").strip().lower()
        return any((r or "").strip().lower() == needle for r in roles)

    @property
    def question_count(self) -> int:
        return self.questions.count()

    @property
    def response_count(self) -> int:
        return self.responses.count()


class FeedbackQuestion(models.Model):
    """One prompt on a feedback form."""

    question_id_PK = models.AutoField(primary_key=True)
    form_id_FK = models.ForeignKey(
        FeedbackForm,
        on_delete=models.CASCADE,
        db_column="form_id_FK",
        related_name="questions",
    )
    prompt = models.CharField(max_length=400)
    qtype = models.CharField(max_length=10, choices=FEEDBACK_QUESTION_TYPES, default="mc")
    # Option labels for multiple choice; anchor labels for likert.
    options = models.JSONField(default=list, blank=True)
    scale_min = models.PositiveSmallIntegerField(default=1)
    scale_max = models.PositiveSmallIntegerField(default=5)
    min_choices = models.PositiveSmallIntegerField(default=1)
    max_choices = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    help_text = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        db_table = "feedback_question"
        ordering = ["display_order", "question_id_PK"]

    def __str__(self):
        return f"{self.form_id_PK.title}: {self.prompt[:40]}"

    def option_labels(self) -> list:
        return [str(o) for o in (self.options or [])]

    def likert_labels(self) -> dict:
        """Map scale value -> label, e.g. {1: "Strongly Disagree", ...}."""
        labels = self.option_labels()
        span = self.scale_max - self.scale_min + 1
        if len(labels) != span:
            return {value: str(value) for value in range(self.scale_min, self.scale_max + 1)}
        return {self.scale_min + i: labels[i] for i in range(span)}


class FeedbackResponse(models.Model):
    """One officer's submission of a form. Unique per (form, officer)."""

    response_id_PK = models.AutoField(primary_key=True)
    form_id_FK = models.ForeignKey(
        FeedbackForm,
        on_delete=models.CASCADE,
        db_column="form_id_FK",
        related_name="responses",
    )
    officer_id_FK = models.ForeignKey(
        OfficerUser,
        on_delete=models.CASCADE,
        db_column="officer_id_FK",
        related_name="feedback_responses",
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ip_address = models.GenericIPAddressField(protocol="both", null=True, blank=True)
    device_info = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "feedback_response"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["form_id_FK", "officer_id_FK"],
                name="uniq_feedback_response_per_officer",
            )
        ]

    def __str__(self):
        return f"{self.officer_id_FK} -> {self.form_id_PK.title}"

    def answer_map(self) -> dict:
        answers = sorted(
            self.answers.select_related("question_id_FK"),
            key=lambda a: (a.question_id_FK.display_order, a.answer_id_PK),
        )
        return {a.question_id_PK: a for a in answers}


class FeedbackAnswer(models.Model):
    """A single answer. Exactly one of the value columns is populated."""

    answer_id_PK = models.AutoField(primary_key=True)
    response_id_FK = models.ForeignKey(
        FeedbackResponse,
        on_delete=models.CASCADE,
        db_column="response_id_FK",
        related_name="answers",
    )
    question_id_FK = models.ForeignKey(
        FeedbackQuestion,
        on_delete=models.CASCADE,
        db_column="question_id_FK",
        related_name="answers",
    )
    value_text = models.TextField(blank=True, default="")
    value_int = models.IntegerField(null=True, blank=True)
    value_list = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "feedback_answer"
        # Ordered by display_order in Python (see FeedbackResponse.answer_map);
        # a FK-spanning Meta.ordering would add a join on every answer read.
        ordering = ["answer_id_PK"]

    def __str__(self):
        return f"Answer {self.answer_id_PK}"

    def display_value(self) -> str:
        if self.question_id_FK.qtype == "likert":
            if self.value_int is None:
                return ""
            labels = self.question_id_FK.likert_labels()
            label = labels.get(self.value_int, "")
            return f"{self.value_int} - {label}" if label else str(self.value_int)
        if self.question_id_FK.qtype == "mc":
            return ", ".join(str(v) for v in (self.value_list or []))
        return self.value_text or ""
