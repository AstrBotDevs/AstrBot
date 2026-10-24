# Unreleased

- Restore the previous certifi and pip minimum versions so existing updaters can install dependencies with their current core version locks. Core updates now bypass those locks; plugin and manual package installs retain dependency protection.
