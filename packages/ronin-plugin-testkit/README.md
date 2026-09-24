# ronin-plugin-testkit

Public contract checks for third-party Ronin plugins. Install this package in
the plugin's own test environment and use `assert_plugin_ready` or
`validate_plugin` against the plugin object; the checks exercise manifest
validation, deterministic composition, contribution registration and lifecycle
cleanup through Ronin's public plugin contract.

The package intentionally contains no host application wiring or repository
test fixtures.
