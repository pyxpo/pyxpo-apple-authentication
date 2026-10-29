"""Config plugin for Sign in with Apple: the `com.apple.developer.applesignin` entitlement on iOS.

    [tool.pyxpo]
    modules = ["apple-authentication"]
    plugins = ["pyxpo_apple_authentication.plugin"]

No options. The App ID in your Apple Developer account also needs the Sign in with Apple capability.
"""
from __future__ import annotations

from typing import Any, Dict

from pyxpo.app_config import ConfigError
from pyxpo.config_plugins import PluginConfig, with_entitlements

ENTITLEMENT = "com.apple.developer.applesignin"


def plugin(config: PluginConfig, props: Dict[str, Any]) -> PluginConfig:
    if props:
        raise ConfigError("pyxpo_apple_authentication.plugin: takes no options, got %s" % sorted(props))

    def entitlements(d: Dict[str, Any]) -> None:
        d[ENTITLEMENT] = ["Default"]

    with_entitlements(config, entitlements)
    return config
