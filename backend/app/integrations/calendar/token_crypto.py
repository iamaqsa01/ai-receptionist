"""Authenticated encryption for OAuth tokens stored in Integration.config."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings, settings as default_settings


_PREFIX = "enc:v1:"


class TokenDecryptionError(ValueError):
    pass


def _fernet(cfg: Settings) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(cfg.secret_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(value: str, cfg: Settings | None = None) -> str:
    if not value:
        return ""
    token = _fernet(cfg or default_settings).encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_token(value: str, cfg: Settings | None = None) -> str:
    if not value or not value.startswith(_PREFIX):
        raise TokenDecryptionError("OAuth token is missing or is not encrypted")
    try:
        return _fernet(cfg or default_settings).decrypt(value[len(_PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise TokenDecryptionError("OAuth token could not be decrypted") from exc
