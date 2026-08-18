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

If you want to develop your own plugin, see [AstrBot Plugin Development Guide](/en/dev/star/plugin-new).
