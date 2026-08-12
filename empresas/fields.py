from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


_PREFIX = 'fernet:'


def _get_fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY.encode('utf-8'))


def encrypt_secret(value: str | None) -> str:
    if value in (None, ''):
        return ''
    if isinstance(value, str) and value.startswith(_PREFIX):
        return value
    token = _get_fernet().encrypt(str(value).encode('utf-8')).decode('utf-8')
    return f'{_PREFIX}{token}'


def decrypt_secret(value: str | None) -> str:
    if value in (None, ''):
        return ''
    if not isinstance(value, str):
        return str(value)
    if not value.startswith(_PREFIX):
        return value
    token = value[len(_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return value


class EncryptedTextField(models.TextField):
    def from_db_value(self, value, expression, connection):
        return decrypt_secret(value)

    def to_python(self, value):
        if value is None:
            return value
        return decrypt_secret(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return encrypt_secret(value)
