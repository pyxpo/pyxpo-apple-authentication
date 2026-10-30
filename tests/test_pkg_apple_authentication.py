"""pyxpo-apple-authentication: availability, the credential, error codes and the entitlement plugin."""
import asyncio

import pytest

from pyxpo.app_config import ConfigError
from pyxpo.config_plugins import Mods, PluginConfig
from pyxpo.module_api import NotSupportedError
from pyxpo.module_testing import FakeBridge

import pyxpo_apple_authentication as A
from pyxpo_apple_authentication import AppleAuthenticationError, AppleAuthenticationScope as Scope
from pyxpo_apple_authentication.plugin import ENTITLEMENT, plugin

RAW = {"user": "001.abc", "state": "s1", "email": "a@privaterelay.appleid.com", "realUserStatus": 2,
       "identityToken": "eyJ.a.b", "authorizationCode": "c0de",
       "fullName": {"givenName": "Ada", "familyName": "Lovelace"}}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fresh():
    A._busy = False
    A._observing[0] = False
    yield
    A._busy = False


def test_available_only_on_ios():
    with FakeBridge("android"):
        assert run(A.is_available_async()) is False
        with pytest.raises(NotSupportedError):
            run(A.sign_in_async())
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "isAvailable", lambda: True)
        assert run(A.isAvailableAsync()) is True


def test_sign_in_sends_scopes_and_shapes_credential():
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "signIn", lambda o: RAW)
        cred = run(A.sign_in_async(requested_scopes=[Scope.EMAIL, Scope.FULL_NAME, Scope.EMAIL], state="s1"))
        assert fb.calls[-1][2][0] == {"operation": 1, "scopes": [0, 1], "user": "", "state": "s1", "nonce": ""}
    assert cred["user"] == "001.abc" and cred["identityToken"] == "eyJ.a.b"
    assert cred["fullName"]["givenName"] == "Ada" and cred["fullName"]["nickname"] is None
    assert cred["realUserStatus"] == 2


def test_camel_options_and_empty_name():
    raw = dict(RAW, fullName={"givenName": None}, email=None)
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "signIn", lambda o: raw)
        cred = run(A.signInAsync(requestedScopes=[Scope.FULL_NAME]))
        assert fb.calls[-1][2][0]["scopes"] == [0]
        with pytest.raises(TypeError):
            run(A.sign_in_async(bogus=1))
    assert cred["fullName"] is None and cred["email"] is None


def test_native_error_codes():
    def cancel(o):
        raise RuntimeError("ERR_REQUEST_CANCELED: The operation couldn't be completed.")

    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "signIn", cancel)
        with pytest.raises(AppleAuthenticationError) as e:
            run(A.sign_in_async())
        assert e.value.code == A.ERR_REQUEST_CANCELED
        fb.on("AppleAuthentication", "signIn", lambda o: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(AppleAuthenticationError) as e:
            run(A.sign_in_async())
        assert e.value.code == A.ERR_REQUEST_UNKNOWN and str(e.value) == "boom"
        fb.on("AppleAuthentication", "signIn", lambda o: {})
        with pytest.raises(AppleAuthenticationError) as e:
            run(A.sign_in_async())
        assert e.value.code == A.ERR_INVALID_RESPONSE
    assert A._busy is False


def test_in_progress_guard():
    A._busy = True
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "signIn", lambda o: RAW)
        with pytest.raises(AppleAuthenticationError) as e:
            run(A.sign_in_async())
        assert not fb.calls
    assert e.value.code == A.ERR_IN_PROGRESS


def test_credential_state():
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "credentialState", lambda u: 1)
        assert run(A.get_credential_state_async("001.abc")) is A.AppleAuthenticationCredentialState.AUTHORIZED
        with pytest.raises(ValueError):
            run(A.get_credential_state_async(""))


def test_refresh_and_sign_out_operations():
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "signIn", lambda o: RAW)
        run(A.refresh_async("001.abc", requested_scopes=[Scope.EMAIL], state="r"))
        assert fb.calls[-1][2][0] == {"operation": 2, "scopes": [1], "user": "001.abc", "state": "r", "nonce": ""}
        run(A.signOutAsync("001.abc"))
        assert fb.calls[-1][2][0]["operation"] == 3 and fb.calls[-1][2][0]["user"] == "001.abc"
        run(A.sign_in_async(requestedOperation=A.AppleAuthenticationOperation.IMPLICIT))
        assert fb.calls[-1][2][0]["operation"] == 0
        with pytest.raises(ValueError):
            run(A.refresh_async(""))
        with pytest.raises(ValueError):
            run(A.sign_in_async(requested_operation=9))
    with FakeBridge("android"):
        with pytest.raises(NotSupportedError):
            run(A.sign_out_async("001.abc"))


def test_revoke_listener():
    from pyxpo.modules import dispatch
    hits = []
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "observeRevocations", lambda: True)
        sub = A.add_revoke_listener(lambda: hits.append(1))
        A.addRevokeListener(lambda: hits.append(2)).remove()
        assert [c[1] for c in fb.calls] == ["observeRevocations"]
    dispatch({"name": A.REVOKED_EVENT, "data": {}})
    sub.remove()
    sub.remove()
    dispatch({"name": A.REVOKED_EVENT, "data": {}})
    assert hits == [1]
    with pytest.raises(TypeError):
        A.add_revoke_listener(None)


def test_format_full_name():
    name = {"namePrefix": "Dr.", "givenName": "Ada", "middleName": "K", "familyName": "Lovelace"}
    S = A.AppleAuthenticationFullNameFormatStyle
    with FakeBridge("android"):
        assert run(A.format_full_name_async(name)) == "Ada K Lovelace"
        assert run(A.format_full_name_async(name, S.MEDIUM)) == "Ada Lovelace"
        assert run(A.format_full_name_async(name, S.LONG)) == "Dr. Ada K Lovelace"
        assert run(A.format_full_name_async(name, S.SHORT)) == "Ada"
        assert run(A.format_full_name_async(name, S.ABBREVIATED)) == "AL"
        assert run(A.format_full_name_async(None)) == ""
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "formatFullName", lambda n, s: "Lovelace Ada")
        assert run(A.formatFullNameAsync(name, S.LONG)) == "Lovelace Ada"
        assert fb.calls[-1][2][1] == 3 and "nickname" not in fb.calls[-1][2][0]


def test_button_props():
    pressed = []
    el = A.AppleAuthenticationButton(button_type=A.AppleAuthenticationButtonType.CONTINUE, cornerRadius=6,
                                     buttonStyle=A.AppleAuthenticationButtonStyle.WHITE_OUTLINE,
                                     on_press=pressed.append, style={"width": 200})
    p = el.props
    assert p["button_type"] == 1 and p["button_style"] == 1 and p["corner_radius"] == 6.0
    assert p["style"] == {"height": 44, "width": 200} and p["on_press"] == pressed.append
    assert "corner_radius" not in A.AppleAuthenticationButton().props
    with pytest.raises(ValueError):
        A.AppleAuthenticationButton(corner_radius=-1)
    with pytest.raises(ValueError):
        A.AppleAuthenticationButton(button_type=7)


def test_plugin_adds_entitlement(tmp_path):
    mods = Mods()
    plugin(PluginConfig({}, tmp_path, mods), {})
    assert mods.apply_entitlements({})[ENTITLEMENT] == ["Default"]
    with pytest.raises(ConfigError):
        plugin(PluginConfig({}, tmp_path, Mods()), {"x": 1})
