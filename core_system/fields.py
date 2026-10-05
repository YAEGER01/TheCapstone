"""Transparent Fernet field encryption (data-at-rest, step 3).

Only for fields the codebase NEVER filters/orders on: Fernet ciphertext is
randomized per write, so ``filter(field="x")`` can never match. Chosen fields
are attribute-only (contact numbers, MFA secret, health reason).

Envelope: ``enc1:<base64-token>``. Reads decrypt transparently
(``to_python``/``from_db_value``); writes encrypt in ``get_prep_value``.
Empty strings and NULL pass through unencrypted so ``if not field`` checks
keep working. Legacy plaintext rows (no prefix) read as-is, so the data
migration can encrypt in place and rollback can decrypt.
"""
from __future__ import annotations

import base64
import hashlib

from django.conf import settings
from django.db import models

ENC_PREFIX = "enc1:"


def _get_data_fernet():
    from cryptography.fernet import Fernet

    raw = (getattr(settings, "DATA_ENCRYPTION_KEY", "") or "").strip()
    if raw:
        return Fernet(raw.encode())
    digest = hashlib.sha256(
        f"data-field-v1:{settings.SECRET_KEY}".encode()
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_str(plaintext: str) -> str:
    if not plaintext:
        return plaintext
    if plaintext.startswith(ENC_PREFIX):
        return plaintext  # already ciphertext — never double-wrap
    token = _get_data_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return ENC_PREFIX + token


def decrypt_str(value: str) -> str:
    from cryptography.fernet import InvalidToken

    if not value or not value.startswith(ENC_PREFIX):
        return value  # NULL / empty / legacy plaintext
    try:
        return _get_data_fernet().decrypt(value[len(ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return value  # wrong key rotation state — surface raw, don't crash reads


class _EncryptedMixin:
    def to_python(self, value):
        value = super().to_python(value)
        return decrypt_str(value) if isinstance(value, str) else value

    def from_db_value(self, value, *args, **kwargs):
        return decrypt_str(value) if isinstance(value, str) else value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_str(value) if isinstance(value, str) else value


class EncryptedCharField(_EncryptedMixin, models.CharField):
    """CharField stored as ``enc1:`` Fernet ciphertext. Needs a wider
    max_length than the plaintext (token overhead ~120 chars)."""


class EncryptedTextField(_EncryptedMixin, models.TextField):
    """TextField stored as ``enc1:`` Fernet ciphertext."""
