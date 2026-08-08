
# 插件热重载

## 手动重载插件

插件的代码修改后，可以在 AstrBot WebUI 的插件管理处找到自己的插件，点击右上角 `...` 按钮，选择 `重载插件`。

如果插件因为代码错误等原因加载失败，你也可以在管理面板的错误提示中点击 **“尝试一键重载修复”** 来重新加载。

## 自动重载插件

除手动将插件重载之外,Astrbot还支持自动热重载,只需要在环境变量中添加`ASTRBOT_RELOAD=1`即可启用,此时Astrbot会监听插件目录下的文件修改并自动重载插件。

可以通过以下命令在当前命令行中设置临时环境变量

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


## VSCode 配置

以下为样例`launch.json`配置,可以让 VS Code 每次启动Astrbot时都自动填入环境变量

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "main.py",
            "type": "debugpy",
            "request": "launch",
            "program": "./main.py",  // Astrbot 启动入口
            "env": {
                "ASTRBOT_RELOAD":"1" // 启用插件热重载
            },
            "console": "integratedTerminal"
        }
    ]
}
```
