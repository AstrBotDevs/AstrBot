# AstrBot Star

AstrBot calls plugins `Stars`. AstrBot is a highly modular project, and Stars leverage this modularity to implement various functionalities.

Plugin management uses a native command group:

- `/plugin list`: List loaded plugins.
- `/plugin show <plugin-name>`: Show the selected plugin's version, author, and registered commands.
- `/plugin disable <plugin-name>`: Disable a plugin; requires `extension.manage`.
- `/plugin enable <plugin-name>`: Enable a plugin; requires `extension.manage`.
- `/plugin install <repository-url>`: Install a plugin; requires `extension.plugin_install` and Dashboard step-up.

Entering `/plugin` alone displays the available subcommand tree. Quote repository URLs containing special characters such as `&` or `#`:

```text
/plugin install 'https://example.com/plugin.git?ref=main&source=manual#install'
```

Plugin load, unload, reload, enable, and disable operations immediately rebuild the command catalog and refresh enabled Telegram/Discord native command surfaces. Installed plugins can also be managed in the admin panel.

The Dashboard plugin marketplace uses an upstream compatibility source, not an official market for this fork. Appearing in that list does not mean the plugin will run on this branch. Check `astrbot_version` before installing. Plugins that need a Dashboard page must declare `requires.dashboard_extension: 1` and use Extension Protocol v1. If a plugin is incompatible, install it with `/plugin install <repository-url>` or the WebUI URL/file installer.

If you want to develop your own plugin, see [AstrBot Plugin Development Guide](/en/dev/star/plugin-new).
