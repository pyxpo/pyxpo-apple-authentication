"""Sign in with Apple: the expo-apple-authentication API.

    import pyxpo_apple_authentication as AppleAuthentication
    from pyxpo_apple_authentication import AppleAuthenticationScope, AppleAuthenticationError

    try:
        cred = await AppleAuthentication.sign_in_async(
            requested_scopes=[AppleAuthenticationScope.FULL_NAME, AppleAuthenticationScope.EMAIL])
        cred["identityToken"]          # send to your server, verify there
    except AppleAuthenticationError as e:
        if e.code == "ERR_REQUEST_CANCELED":
            ...                        # the user closed the sheet

iOS only (AuthenticationServices). On Android and the desktop `is_available_async()` is False and the other calls
raise NotSupportedError. Apple sends the name and the email only on the first sign-in of a user: keep them then.
"""
from __future__ import annotations

import re
from enum import IntEnum
from typing import Any, Dict, Iterable, Optional

from pyxpo.module_api import NotSupportedError, call, platform, require_linked

__version__ = "0.1.0a1"

NATIVE = "AppleAuthentication"
Credential = Dict[str, Any]


class AppleAuthenticationScope(IntEnum):
    FULL_NAME = 0
    EMAIL = 1


class AppleAuthenticationCredentialState(IntEnum):
    REVOKED = 0
    AUTHORIZED = 1
    NOT_FOUND = 2
    TRANSFERRED = 3


class AppleAuthenticationUserDetectionStatus(IntEnum):
    UNSUPPORTED = 0
    UNKNOWN = 1
    LIKELY_REAL = 2


ERR_REQUEST_CANCELED = "ERR_REQUEST_CANCELED"
ERR_REQUEST_FAILED = "ERR_REQUEST_FAILED"
ERR_INVALID_RESPONSE = "ERR_INVALID_RESPONSE"
ERR_REQUEST_NOT_HANDLED = "ERR_REQUEST_NOT_HANDLED"
ERR_REQUEST_NOT_INTERACTIVE = "ERR_REQUEST_NOT_INTERACTIVE"
ERR_REQUEST_UNKNOWN = "ERR_REQUEST_UNKNOWN"
ERR_IN_PROGRESS = "ERR_IN_PROGRESS"


class AppleAuthenticationError(Exception):
    """A failed request. `code` is one of the `ERR_*` names; `ERR_REQUEST_CANCELED` when the user closed it."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


_CODE_RE = re.compile(r"^(ERR_[A-Z_]+):\s*(.*)$", re.S)
_busy = False


def _error(e: BaseException) -> AppleAuthenticationError:
    m = _CODE_RE.match(str(e))
    if m:
        return AppleAuthenticationError(m.group(1), m.group(2))
    return AppleAuthenticationError(ERR_REQUEST_UNKNOWN, str(e))


def _ios(feature: str) -> None:
    if platform() != "ios":
        raise NotSupportedError("Sign in with Apple (%s) works on iOS only" % feature)
    require_linked(NATIVE, "apple-authentication", package="pyxpo-apple-authentication")


async def _native(method: str, *args: Any) -> Any:
    try:
        return await call(NATIVE, method, *args, reply=True)
    except Exception as e:  # native replies "ERR_CODE: message"
        raise _error(e) from None


async def is_available_async() -> bool:
    """True on iOS 13 and later with the module linked; False elsewhere."""
    if platform() != "ios":
        return False
    try:
        require_linked(NATIVE, "apple-authentication", package="pyxpo-apple-authentication")
    except Exception:
        return False
    return bool(await _native("isAvailable"))


def _scopes(scopes: Optional[Iterable[Any]]) -> list:
    return sorted({int(AppleAuthenticationScope(s)) for s in (scopes or [])})


def _credential(raw: Dict[str, Any]) -> Credential:
    name = raw.get("fullName")
    if isinstance(name, dict):
        name = {k: name.get(k) for k in ("namePrefix", "givenName", "middleName", "familyName", "nameSuffix",
                                         "nickname")}
        if not any(name.values()):
            name = None
    else:
        name = None
    return {
        "user": raw.get("user"), "state": raw.get("state"), "fullName": name, "email": raw.get("email"),
        "realUserStatus": int(raw.get("realUserStatus") or 0), "identityToken": raw.get("identityToken"),
        "authorizationCode": raw.get("authorizationCode"),
    }


async def sign_in_async(requested_scopes: Optional[Iterable[Any]] = None, state: Optional[str] = None,
                        nonce: Optional[str] = None, **camel: Any) -> Credential:
    """Shows Apple's sign-in sheet. Returns `{"user", "state", "fullName", "email", "realUserStatus",
    "identityToken", "authorizationCode"}`. `fullName` and `email` come only on a user's first sign-in.
    Raises `AppleAuthenticationError` (`ERR_REQUEST_CANCELED` when the user closes the sheet)."""
    global _busy
    requested_scopes = camel.pop("requestedScopes", requested_scopes)
    if camel:
        raise TypeError("sign_in_async() got unknown options %s" % sorted(camel))
    _ios("sign_in_async")
    if _busy:
        raise AppleAuthenticationError(ERR_IN_PROGRESS, "a sign-in is already in progress")
    _busy = True
    try:
        raw = await _native("signIn", {"scopes": _scopes(requested_scopes), "state": state or "",
                                       "nonce": nonce or ""})
    finally:
        _busy = False
    if not isinstance(raw, dict) or not raw.get("user"):
        raise AppleAuthenticationError(ERR_INVALID_RESPONSE, "Apple returned no user")
    return _credential(raw)


async def get_credential_state_async(user: str) -> AppleAuthenticationCredentialState:
    """Whether the Apple ID `user` (from a credential) still authorizes this app."""
    if not user:
        raise ValueError("user must be the `user` of an earlier credential")
    _ios("get_credential_state_async")
    return AppleAuthenticationCredentialState(int(await _native("credentialState", user)))


isAvailableAsync = is_available_async
signInAsync = sign_in_async
getCredentialStateAsync = get_credential_state_async

__all__ = ["is_available_async", "sign_in_async", "get_credential_state_async", "AppleAuthenticationScope",
           "AppleAuthenticationCredentialState", "AppleAuthenticationUserDetectionStatus", "AppleAuthenticationError",
           "ERR_REQUEST_CANCELED", "ERR_REQUEST_FAILED", "ERR_INVALID_RESPONSE", "ERR_REQUEST_NOT_HANDLED",
           "ERR_REQUEST_NOT_INTERACTIVE", "ERR_REQUEST_UNKNOWN", "ERR_IN_PROGRESS", "isAvailableAsync",
           "signInAsync", "getCredentialStateAsync"]
