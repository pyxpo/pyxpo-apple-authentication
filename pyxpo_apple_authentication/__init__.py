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

    AppleAuthentication.AppleAuthenticationButton(
        button_type=AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN,
        button_style=AppleAuthentication.AppleAuthenticationButtonStyle.BLACK,
        corner_radius=8, style={"width": 260, "height": 48}, on_press=lambda _: spawn(sign_in()))

iOS only (AuthenticationServices). On Android and the desktop `is_available_async()` is False, the button renders
an empty view and the other calls raise NotSupportedError. Apple sends the name and the email only on the first
sign-in of a user: keep them then.
"""
from __future__ import annotations

import re
from enum import IntEnum
from typing import Any, Callable, Dict, Iterable, List, Optional

from pyxpo.module_api import NotSupportedError, call, native_view, on_event, platform, require_linked

__version__ = "0.1.0a2"

NATIVE = "AppleAuthentication"
REVOKED_EVENT = "AppleAuthentication.revoked"
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


class AppleAuthenticationOperation(IntEnum):
    IMPLICIT = 0
    LOGIN = 1
    REFRESH = 2
    LOGOUT = 3


class AppleAuthenticationButtonType(IntEnum):
    SIGN_IN = 0
    CONTINUE = 1
    SIGN_UP = 2


class AppleAuthenticationButtonStyle(IntEnum):
    WHITE = 0
    WHITE_OUTLINE = 1
    BLACK = 2


class AppleAuthenticationFullNameFormatStyle(IntEnum):
    DEFAULT = 0
    SHORT = 1
    MEDIUM = 2
    LONG = 3
    ABBREVIATED = 4


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


async def _request(feature: str, operation: int, scopes: Optional[Iterable[Any]], user: Optional[str],
                   state: Optional[str], nonce: Optional[str]) -> Credential:
    global _busy
    _ios(feature)
    if _busy:
        raise AppleAuthenticationError(ERR_IN_PROGRESS, "a sign-in is already in progress")
    _busy = True
    try:
        raw = await _native("signIn", {"operation": operation, "scopes": _scopes(scopes), "user": user or "",
                                       "state": state or "", "nonce": nonce or ""})
    finally:
        _busy = False
    if not isinstance(raw, dict) or not raw.get("user"):
        raise AppleAuthenticationError(ERR_INVALID_RESPONSE, "Apple returned no user")
    return _credential(raw)


def _options(name: str, camel: Dict[str, Any], **known: Any) -> Dict[str, Any]:
    if "requestedScopes" in camel:
        known["requested_scopes"] = camel.pop("requestedScopes")
    if "requestedOperation" in camel and "requested_operation" in known:
        known["requested_operation"] = camel.pop("requestedOperation")
    if camel:
        raise TypeError("%s() got unknown options %s" % (name, sorted(camel)))
    return known


async def sign_in_async(requested_scopes: Optional[Iterable[Any]] = None, state: Optional[str] = None,
                        nonce: Optional[str] = None,
                        requested_operation: Any = AppleAuthenticationOperation.LOGIN, **camel: Any) -> Credential:
    """Shows Apple's sign-in sheet. Returns `{"user", "state", "fullName", "email", "realUserStatus",
    "identityToken", "authorizationCode"}`. `fullName` and `email` come only on a user's first sign-in.
    Raises `AppleAuthenticationError` (`ERR_REQUEST_CANCELED` when the user closes the sheet)."""
    o = _options("sign_in_async", camel, requested_scopes=requested_scopes, requested_operation=requested_operation)
    return await _request("sign_in_async", int(AppleAuthenticationOperation(o["requested_operation"])),
                          o["requested_scopes"], None, state, nonce)


async def refresh_async(user: str, requested_scopes: Optional[Iterable[Any]] = None, state: Optional[str] = None,
                        **camel: Any) -> Credential:
    """Asks Apple for a fresh credential (new identityToken and authorizationCode) of an earlier `user`."""
    o = _options("refresh_async", camel, requested_scopes=requested_scopes)
    if not user:
        raise ValueError("user must be the `user` of an earlier credential")
    return await _request("refresh_async", int(AppleAuthenticationOperation.REFRESH), o["requested_scopes"], user,
                          state, None)


async def sign_out_async(user: str, state: Optional[str] = None) -> Credential:
    """Runs Apple's logout operation for `user`. It does not end the user's session on your server: do that
    there too."""
    if not user:
        raise ValueError("user must be the `user` of an earlier credential")
    return await _request("sign_out_async", int(AppleAuthenticationOperation.LOGOUT), None, user, state, None)


async def get_credential_state_async(user: str) -> AppleAuthenticationCredentialState:
    """Whether the Apple ID `user` (from a credential) still authorizes this app."""
    if not user:
        raise ValueError("user must be the `user` of an earlier credential")
    _ios("get_credential_state_async")
    return AppleAuthenticationCredentialState(int(await _native("credentialState", user)))


class Subscription:
    """What `add_revoke_listener` returns; `remove()` stops the calls."""

    def __init__(self, off: Callable[[], None]) -> None:
        self._off: Optional[Callable[[], None]] = off

    def remove(self) -> None:
        if self._off is not None:
            self._off()
            self._off = None


_observing = [False]


def add_revoke_listener(listener: Callable[[], Any]) -> Subscription:
    """Calls `listener()` when the user stops using Apple ID with this app (Settings > Apple ID > Sign in with
    Apple). Sign the user out then. On other platforms the listener is never called."""
    if not callable(listener):
        raise TypeError("listener must be callable")
    off = on_event(REVOKED_EVENT, lambda _data: listener())
    if platform() == "ios" and not _observing[0]:
        try:
            require_linked(NATIVE, "apple-authentication", package="pyxpo-apple-authentication")
        except Exception:
            return Subscription(off)
        _observing[0] = True
        call(NATIVE, "observeRevocations")
    return Subscription(off)


_NAME_KEYS = ("namePrefix", "givenName", "middleName", "familyName", "nameSuffix", "nickname")


def _join_name(name: Dict[str, Any], style: int) -> str:
    if style == AppleAuthenticationFullNameFormatStyle.SHORT:
        return str(name.get("nickname") or name.get("givenName") or name.get("familyName") or "")
    if style == AppleAuthenticationFullNameFormatStyle.ABBREVIATED:
        return "".join(str(name[k])[0] for k in ("givenName", "familyName") if name.get(k))
    keys: List[str] = ["givenName", "middleName", "familyName"]
    if style == AppleAuthenticationFullNameFormatStyle.LONG:
        keys = ["namePrefix"] + keys + ["nameSuffix"]
    elif style == AppleAuthenticationFullNameFormatStyle.MEDIUM:
        keys = ["givenName", "familyName"]
    return " ".join(str(name[k]) for k in keys if name.get(k))


async def format_full_name_async(full_name: Optional[Dict[str, Any]],
                                 format_style: Any = AppleAuthenticationFullNameFormatStyle.DEFAULT) -> str:
    """The `fullName` of a credential as one string, in the order and form of the user's locale on iOS
    (PersonNameComponentsFormatter). Elsewhere a simple given-middle-family join. "" when there is no name."""
    style = int(AppleAuthenticationFullNameFormatStyle(format_style))
    name = {k: (full_name or {}).get(k) for k in _NAME_KEYS}
    if not any(name.values()):
        return ""
    if platform() == "ios":
        try:
            require_linked(NATIVE, "apple-authentication", package="pyxpo-apple-authentication")
        except Exception:
            return _join_name(name, style)
        return str(await _native("formatFullName", {k: v for k, v in name.items() if v}, style) or "")
    return _join_name(name, style)


_Button = native_view("PxAppleAuthenticationButton")


def AppleAuthenticationButton(button_type: Any = AppleAuthenticationButtonType.SIGN_IN,
                              button_style: Any = AppleAuthenticationButtonStyle.BLACK,
                              corner_radius: Optional[float] = None, on_press: Optional[Callable[[Any], Any]] = None,
                              style: Any = None, **props: Any) -> Any:
    """Apple's own Sign in with Apple button (App Store review asks for it). Give it a size in `style`
    (default height 44). `on_press` gets called on a tap: start `sign_in_async` there. iOS only; elsewhere it
    renders an empty view, so check `is_available_async()` and show another button."""
    for camel, snake in (("buttonType", "button_type"), ("buttonStyle", "button_style"),
                         ("cornerRadius", "corner_radius"), ("onPress", "on_press")):
        if camel in props:
            v = props.pop(camel)
            if snake == "button_type":
                button_type = v
            elif snake == "button_style":
                button_style = v
            elif snake == "corner_radius":
                corner_radius = v
            else:
                on_press = v
    wire: Dict[str, Any] = {"button_type": int(AppleAuthenticationButtonType(button_type)),
                            "button_style": int(AppleAuthenticationButtonStyle(button_style))}
    if corner_radius is not None:
        if isinstance(corner_radius, bool) or not isinstance(corner_radius, (int, float)) or corner_radius < 0:
            raise ValueError("corner_radius must be a number >= 0")
        wire["corner_radius"] = float(corner_radius)
    if on_press is not None:
        wire["on_press"] = on_press
    box: Dict[str, Any] = {"height": 44}
    if isinstance(style, dict):
        box.update(style)
    return _Button(style=box, **wire, **props)


isAvailableAsync = is_available_async
signInAsync = sign_in_async
getCredentialStateAsync = get_credential_state_async
refreshAsync = refresh_async
signOutAsync = sign_out_async
addRevokeListener = add_revoke_listener
formatFullNameAsync = format_full_name_async

__all__ = ["is_available_async", "sign_in_async", "refresh_async", "sign_out_async", "get_credential_state_async",
           "add_revoke_listener", "format_full_name_async", "AppleAuthenticationButton", "Subscription",
           "AppleAuthenticationOperation", "AppleAuthenticationButtonType", "AppleAuthenticationButtonStyle",
           "AppleAuthenticationFullNameFormatStyle", "AppleAuthenticationScope",
           "AppleAuthenticationCredentialState", "AppleAuthenticationUserDetectionStatus", "AppleAuthenticationError",
           "ERR_REQUEST_CANCELED", "ERR_REQUEST_FAILED", "ERR_INVALID_RESPONSE", "ERR_REQUEST_NOT_HANDLED",
           "ERR_REQUEST_NOT_INTERACTIVE", "ERR_REQUEST_UNKNOWN", "ERR_IN_PROGRESS", "isAvailableAsync",
           "signInAsync", "getCredentialStateAsync", "refreshAsync", "signOutAsync", "addRevokeListener",
           "formatFullNameAsync"]
