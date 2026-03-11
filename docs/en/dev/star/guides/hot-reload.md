# Plugin Hot Reload

## Manual Reload

After modifying your plugin code, you can navigate to the **Plugin Management** section in the AstrBot WebUI. Locate your plugin, click the `...` button in the top-right corner, and select **Reload Plugin**.

If a plugin fails to load due to code errors or other issues, you can also click **"Try One-Click Reload Fix"** within the error notification in the management panel to attempt a reload.

## Automatic Reload

In addition to manual reloading, AstrBot supports **Automatic Hot Reloading**. To enable this feature, simply add the environment variable `ASTRBOT_RELOAD=1`. Once active, AstrBot will monitor the plugin directory for file changes and reload the affected plugins automatically.

You can set this temporary environment variable in your current terminal session using the following commands:

### Windows (PowerShell)

```pwsh
$env:ASTRBOT_RELOAD = "1"
```

### Windows (cmd)

```cmd
set ASTRBOT_RELOAD=1
```

### Linux / macOS

```bash
export ASTRBOT_RELOAD=1
```

## VS Code Configuration

Below is a sample `launch.json` configuration that allows VS Code to automatically inject the environment variable every time you start AstrBot.

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "main.py",
            "type": "debugpy",
            "request": "launch",
            "program": "./main.py",  // Astrbot entry point
            "env": {
                "ASTRBOT_RELOAD":"1" // Enable plugin hot reload
            },
            "console": "integratedTerminal"
        }
    ]
}
```