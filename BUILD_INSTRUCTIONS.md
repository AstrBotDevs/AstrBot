# AstrBot 桌面应用构建指南

本指南介绍如何使用 Nuitka 将 Python 后端打包并集成到 Tauri 桌面应用中。

## 前置要求

### 系统要求
- Python 3.10+
- Node.js 20+
- Rust (通过 rustup 安装)
- UV 包管理器

### macOS 额外要求
- Xcode Command Line Tools: `xcode-select --install`

### Linux 额外要求
```bash
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev \
  libappindicator3-dev librsvg2-dev patchelf
```

### Windows 额外要求
- Visual Studio 2019+ with C++ build tools
- Windows 10 SDK

## 构建步骤

### 1. 安装 Python 依赖
```bash
pip install uv
uv sync
```

### 2. 安装 Nuitka
```bash
pip install nuitka
```

### 3. 构建 Python 后端
```bash
python build_nuitka.py
```

这会使用 Nuitka 将 `main.py` 编译为独立可执行文件，输出到 `build/nuitka/` 目录。

**注意**: Nuitka 编译过程可能需要 10-30 分钟，取决于您的系统性能。

### 4. 安装前端依赖
```bash
cd dashboard
npm install
```

### 5. 构建 Tauri 应用
```bash
npm run tauri:build
```

构建脚本会自动:
1. 运行 `build_nuitka.py` 编译 Python 后端
2. 将编译好的可执行文件复制到 `src-tauri/resources/` 目录
3. 构建 Tauri 应用并打包所有资源

### 6. 查找构建产物

构建完成后，您可以在以下位置找到安装包:

- **macOS**: `dashboard/src-tauri/target/release/bundle/dmg/AstrBot_*.dmg`
- **Windows**: `dashboard/src-tauri/target/release/bundle/msi/AstrBot_*.msi`
- **Linux**: 
  - `dashboard/src-tauri/target/release/bundle/deb/astrbot_*.deb`
  - `dashboard/src-tauri/target/release/bundle/appimage/astrbot_*.AppImage`

## 开发模式

在开发时，您可能不想每次都完整编译 Python 后端。

### 仅开发 Tauri + Vue
```bash
cd dashboard
npm run tauri:dev
```

这会启动开发服务器，但不会自动启动 Python 后端。您需要手动运行:
```bash
uv run main.py
```

### 测试完整集成
如果您想测试 Tauri 自动启动 Python 后端的功能:

1. 先编译一次 Python 后端:
```bash
python build_nuitka.py
```

2. 手动复制到资源目录:
```bash
# macOS
cp -r build/nuitka/main.app dashboard/src-tauri/resources/astrbot-backend.app

# Windows
copy build\nuitka\main.exe dashboard\src-tauri\resources\astrbot-backend.exe

# Linux
cp build/nuitka/main.bin dashboard/src-tauri/resources/astrbot-backend
```

3. 运行开发模式:
```bash
cd dashboard
npm run tauri:dev
```

## Nuitka 构建选项说明

`build_nuitka.py` 脚本使用以下关键选项:

- `--standalone`: 创建包含所有依赖的独立目录
- `--onefile`: 将所有内容打包到单个可执行文件
- `--follow-imports`: 自动跟踪所有 Python 导入
- `--include-package`: 明确包含特定包
- `--include-data-dir`: 包含数据目录（插件、配置等）

### 自定义构建

如果您需要修改构建选项，编辑 `build_nuitka.py`:

```python
# 添加更多要包含的包
include_packages = [
    "astrbot",
    "your_custom_package",
    # ...
]

# 添加更多数据目录
data_includes = [
    "data/config",
    "your_custom_data",
    # ...
]
```

## 常见问题

### 1. Nuitka 编译失败
**问题**: 编译时出现 "module not found" 错误

**解决方案**: 在 `build_nuitka.py` 中添加缺失的包到 `include_packages` 列表

### 2. 运行时找不到资源文件
**问题**: 应用启动后提示找不到配置文件或插件

**解决方案**: 确保在 `build_nuitka.py` 中使用 `--include-data-dir` 包含了所有必要的数据目录

### 3. macOS 安全警告
**问题**: macOS 提示"应用来自未知开发者"

**解决方案**: 
```bash
# 临时解除限制
sudo spctl --master-disable

# 或者为特定应用授权
xattr -cr /Applications/AstrBot.app
```

对于生产发布，您需要:
1. 注册 Apple Developer 账号
2. 对应用进行代码签名
3. 提交公证 (Notarization)

### 4. Windows Defender 报毒
**问题**: Windows Defender 或其他杀毒软件报毒

**解决方案**: 
- 这是 Nuitka 打包程序的常见问题
- 可以使用 `--windows-company-name` 和 `--windows-product-name` 添加元数据
- 对于生产发布，需要购买代码签名证书

### 5. Linux 依赖问题
**问题**: 在某些 Linux 发行版上缺少共享库

**解决方案**: 使用 AppImage 格式，它包含所有依赖:
```bash
# 构建时会自动生成 AppImage
npm run tauri:build
```

## 优化构建大小

默认的 `--onefile` 模式会生成较大的可执行文件。如果需要减小体积:

1. 移除不需要的包
2. 使用 `--standalone` 而不是 `--onefile`
3. 排除不必要的数据文件

修改 `build_nuitka.py`:
```python
# 移除 --onefile，使用 --standalone
nuitka_cmd = [
    sys.executable,
    "-m", "nuitka",
    "--standalone",  # 只使用 standalone
    # "--onefile",   # 注释掉 onefile
    # ...
]
```

## CI/CD 集成

项目已配置 GitHub Actions 工作流 (`.github/workflows/build-app.yml`)，可以自动为所有平台构建应用。

推送标签时自动触发:
```bash
git tag v4.5.7
git push origin v4.5.7
```

或手动触发:
在 GitHub Actions 页面选择 "Build Desktop App" 工作流并点击 "Run workflow"

## 发布清单

在发布新版本前:

- [ ] 更新版本号
  - `pyproject.toml` - Python 项目版本
  - `dashboard/package.json` - Node 项目版本
  - `dashboard/src-tauri/Cargo.toml` - Rust 项目版本
  - `dashboard/src-tauri/tauri.conf.json` - Tauri 配置版本

- [ ] 运行代码检查
  ```bash
  uv run ruff check .
  uv run ruff format .
  ```

- [ ] 本地测试构建
  ```bash
  python build_nuitka.py
  cd dashboard && npm run tauri:build
  ```

- [ ] 测试安装包
  - 安装生成的安装包
  - 验证应用启动
  - 验证 Python 后端自动启动
  - 测试核心功能

- [ ] 创建发布标签
  ```bash
  git tag -a v4.5.7 -m "Release v4.5.7"
  git push origin v4.5.7
  ```

## 技术架构

```
┌─────────────────────────────────────┐
│         Tauri Desktop App           │
│  (Rust + WebView)                   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │   Vue.js Dashboard          │   │
│  │   (Frontend UI)             │   │
│  └─────────────────────────────┘   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │   Python Backend            │   │
│  │   (Nuitka Compiled)         │   │
│  │   - AstrBot Core            │   │
│  │   - Plugins                 │   │
│  │   - API Server              │   │
│  └─────────────────────────────┘   │
│                                     │
│         HTTP/WebSocket              │
│      localhost:6185                 │
└─────────────────────────────────────┘
```

## 参考资源

- [Nuitka 文档](https://nuitka.net/doc/user-manual.html)
- [Tauri 文档](https://tauri.app/v1/guides/)
- [AstrBot 文档](https://astrbot.fun)
