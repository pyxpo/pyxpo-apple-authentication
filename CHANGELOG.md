# Changelog

## Unreleased

## 0.1.0a2

- `AppleAuthenticationButton`: the native `ASAuthorizationAppleIDButton` with button type, style and corner radius.
- `refresh_async`, `sign_out_async` and `requested_operation` on `sign_in_async` (`AppleAuthenticationOperation`).
- `add_revoke_listener` on `credentialRevokedNotification`; returns a `Subscription`.
- `format_full_name_async` with `AppleAuthenticationFullNameFormatStyle` (`PersonNameComponentsFormatter` on iOS).
- Module contract 2 (native view).

## 0.1.0a1

- First release: `is_available_async`, `sign_in_async`, `get_credential_state_async`, the scope, credential state
  and user detection enums, and `AppleAuthenticationError` codes. iOS on AuthenticationServices.
- Config plugin `pyxpo_apple_authentication.plugin` adds the `com.apple.developer.applesignin` entitlement.
