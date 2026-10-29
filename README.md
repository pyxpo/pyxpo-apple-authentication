# pyxpo-apple-authentication

[![CI](https://github.com/pyxpo/pyxpo-apple-authentication/actions/workflows/ci.yml/badge.svg)](https://github.com/pyxpo/pyxpo-apple-authentication/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/pyxpo-apple-authentication)](https://pypi.org/project/pyxpo-apple-authentication/) [![Python](https://img.shields.io/pypi/pyversions/pyxpo-apple-authentication)](https://pypi.org/project/pyxpo-apple-authentication/) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Sign in with Apple for [pyxpo](https://github.com/pyxpo/pyxpo) apps written in Python. The API follows
[expo-apple-authentication](https://docs.expo.dev/versions/latest/sdk/apple-authentication/). It runs on iOS with
AuthenticationServices. You get an **identity token** (a JWT signed by Apple) to verify on your server.

```python
import pyxpo_apple_authentication as AppleAuthentication
from pyxpo_apple_authentication import AppleAuthenticationScope, AppleAuthenticationError

if await AppleAuthentication.is_available_async():
    try:
        cred = await AppleAuthentication.sign_in_async(
            requested_scopes=[AppleAuthenticationScope.FULL_NAME, AppleAuthenticationScope.EMAIL])
        await api.post("/auth/apple", {"identityToken": cred["identityToken"]})
    except AppleAuthenticationError as e:
        if e.code != "ERR_REQUEST_CANCELED":
            raise
```

## Features

- **Apple's own sheet**, with Face ID and the Hide My Email relay.
- **Clear errors:** `AppleAuthenticationError.code` is `ERR_REQUEST_CANCELED` when the user closes the sheet.
- **Credential state** checks, so you can sign out a user who revoked the app in Settings.
- **Config plugin** for the `com.apple.developer.applesignin` entitlement, so you never edit the entitlements file.
- **Safe on every platform:** `is_available_async()` is `False` on Android, the web and the desktop.
- **camelCase too:** `signInAsync(requestedScopes=...)`.

## Contents

| If you are... | Start here |
| --- | --- |
| Setting up | [Install](#install) · [Apple Developer setup](#apple-developer-setup) |
| Signing users in | [Quick start](#quick-start) |
| Exact names | [API reference](#api-reference) · [Errors](#errors) |
| Stuck | [Testing](#testing) · [Troubleshooting](#troubleshooting) |

## Install

```bash
pip install pyxpo-apple-authentication
```

Add the module and its config plugin to your app's `pyproject.toml`:

```toml
[tool.pyxpo]
modules = ["apple-authentication"]
plugins = ["pyxpo_apple_authentication.plugin"]
```

Then rebuild the iOS app (`pyxpo run ios`). The plugin adds `com.apple.developer.applesignin = ["Default"]` to the
app entitlements.

| Platform | Engine | Minimum |
| --- | --- | --- |
| iOS | AuthenticationServices | iOS 13 |
| Android, web, desktop | not supported (`is_available_async()` is `False`) | |

## Apple Developer setup

1. In Certificates, Identifiers & Profiles, open your App ID and turn on **Sign in with Apple**.
2. Make a new provisioning profile for that App ID, or let Xcode signing make it.
3. On your server, verify `identityToken` against Apple's keys at `https://appleid.apple.com/auth/keys`. Check
   that `aud` is your bundle ID and `iss` is `https://appleid.apple.com`.

The simulator needs an Apple ID signed in under Settings.

## Quick start

Apple sends `fullName` and `email` **only on the first sign-in** of a user for your app. Send them to your server
then, with the token:

```python
cred = await AppleAuthentication.sign_in_async(
    requested_scopes=[AppleAuthenticationScope.FULL_NAME, AppleAuthenticationScope.EMAIL])
name = cred["fullName"] or {}
full = " ".join(p for p in (name.get("givenName"), name.get("familyName")) if p) or None
await api.post("/auth/apple", {"identityToken": cred["identityToken"], "fullName": full})
```

Check later that the user still allows your app:

```python
from pyxpo_apple_authentication import AppleAuthenticationCredentialState as State

if await AppleAuthentication.get_credential_state_async(saved_user) is State.REVOKED:
    await sign_out()
```

Draw your own button that follows Apple's
[Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/sign-in-with-apple)
(black or white, the Apple logo, "Sign in with Apple" or "Continue with Apple").

## API reference

| Name | Returns | Notes |
| --- | --- | --- |
| `is_available_async()` | `bool` | `True` on iOS with the module linked. |
| `sign_in_async(requested_scopes=None, state=None, nonce=None)` | credential `dict` | Shows Apple's sheet. |
| `get_credential_state_async(user)` | `AppleAuthenticationCredentialState` | `user` is `credential["user"]`. |
| `AppleAuthenticationScope` | `FULL_NAME`, `EMAIL` | |
| `AppleAuthenticationCredentialState` | `REVOKED`, `AUTHORIZED`, `NOT_FOUND`, `TRANSFERRED` | |
| `AppleAuthenticationUserDetectionStatus` | `UNSUPPORTED`, `UNKNOWN`, `LIKELY_REAL` | `credential["realUserStatus"]` |

The credential has `user`, `state`, `fullName` (`namePrefix`, `givenName`, `middleName`, `familyName`,
`nameSuffix`, `nickname`, or `None`), `email`, `realUserStatus`, `identityToken` and `authorizationCode`.

## Errors

`AppleAuthenticationError` has `code`:

| Code | Meaning |
| --- | --- |
| `ERR_REQUEST_CANCELED` | The user closed the sheet. |
| `ERR_REQUEST_FAILED` | The request failed, for example with no Apple ID on the device. |
| `ERR_INVALID_RESPONSE` | Apple sent an answer without a user. |
| `ERR_REQUEST_NOT_HANDLED` | No provider handled the request. |
| `ERR_REQUEST_NOT_INTERACTIVE` | The request needed UI that the app cannot show now. |
| `ERR_IN_PROGRESS` | A sign-in is already open. |
| `ERR_REQUEST_UNKNOWN` | Anything else. |

On other platforms `sign_in_async` raises `pyxpo.module_api.NotSupportedError`.

## Testing

Use `FakeBridge` from pyxpo to run your sign-in logic on the desktop:

```python
from pyxpo.module_testing import FakeBridge
import pyxpo_apple_authentication as A

def test_sign_in():
    with FakeBridge("ios") as fb:
        fb.on("AppleAuthentication", "signIn", lambda o: {"user": "001.a", "identityToken": "t"})
        assert asyncio.run(A.sign_in_async())["identityToken"] == "t"
```

## Troubleshooting

- **`ERR_REQUEST_UNKNOWN` with error 1000.** The entitlement is missing. Add the plugin and rebuild, and turn on
  Sign in with Apple for the App ID.
- **`fullName` is `None`.** It comes only on the first sign-in. Remove the app under Settings > Apple ID > Sign in
  with Apple to test it again.
- **Simulator: nothing happens.** Sign in to an Apple ID in the simulator's Settings.

## License

MIT
