# AstrBot Dashboard - Tauri 桌面应用

本项目现已支持通过 Tauri 构建为桌面应用，同时保持与 Web 版本的兼容性。

## 环境要求

### 系统依赖

**macOS:**
```bash
# 安装 Xcode Command Line Tools
xcode-select --install
```

**Windows:**
- 安装 [Microsoft Visual Studio C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- 安装 [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install libwebkit2gtk-4.0-dev \
    build-essential \
    curl \
    wget \
    file \
    libssl-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev
```

### Rust 环境

```bash
# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 验证安装
rustc --version
cargo --version
```

## 安装依赖

```bash
cd dashboard
npm install
```

## 开发模式

### Web 端开发（不变）

```bash
npm run dev
```

访问 http://localhost:3000

### 桌面端开发

```bash
npm run tauri:dev
```

这会同时启动：
1. Vite 开发服务器（端口 3000）
2. Tauri 桌面应用窗口

热重载功能正常工作，修改代码后会自动刷新。

## 构建

### Web 端构建（不变）

```bash
npm run build
```

输出目录：`dist/`

### 桌面端构建

```bash
npm run tauri:build
```

构建产物位置：
- **macOS**: `src-tauri/target/release/bundle/dmg/`
- **Windows**: `src-tauri/target/release/bundle/msi/`
- **Linux**: `src-tauri/target/release/bundle/deb/` 或 `appimage/`

## 图标设置

### 自动生成图标

准备一个至少 512x512 像素的 PNG 图标，然后运行：

```bash
npm run tauri icon path/to/your/icon.png
```

### 手动设置图标

将以下图标放入 `src-tauri/icons/` 目录：
- `32x32.png`
- `128x128.png`
- `128x128@2x.png`
- `icon.icns` (macOS)
- `icon.ico` (Windows)

## 代码兼容性

项目已配置为同时支持 Web 和桌面端，使用相同的代码库。

### 环境检测工具

在 `src/utils/tauri.ts` 中提供了环境检测工具：

```typescript
import { isTauri, isWeb, PlatformAPI } from '@/utils/tauri';

// 检测运行环境
if (isTauri()) {
  console.log('运行在桌面应用中');
} else {
  console.log('运行在浏览器中');
}

// 获取正确的 API 端点
const baseURL = PlatformAPI.getBaseURL();
```

### API 调用注意事项

- **Web 端**: 使用 Vite 代理，API 路径为 `/api/*`
- **桌面端**: 直接连接到 `http://127.0.0.1:6185`

已在 `PlatformAPI.getBaseURL()` 中处理，使用 axios 时：

```typescript
import axios from 'axios';
import { PlatformAPI } from '@/utils/tauri';

const api = axios.create({
  baseURL: PlatformAPI.getBaseURL()
});
```

## 配置说明

### tauri.conf.json

主要配置项：
- `build.devPath`: 开发服务器地址（http://localhost:3000）
- `build.distDir`: 构建输出目录（../dist）
- `tauri.allowlist`: API 权限配置
- `tauri.windows`: 窗口配置（大小、标题等）

### 安全性

默认配置已启用必要的权限：
- 文件系统访问（限定在 APPDATA 目录）
- HTTP 请求（限定到本地后端）
- 窗口控制
- 对话框（打开/保存文件）

可在 `tauri.conf.json` 的 `allowlist` 部分调整权限。

## 后端连接

桌面应用需要后端服务运行在 `http://127.0.0.1:6185`。

### 启动流程

1. 启动 AstrBot 后端:
   ```bash
   cd /path/to/AstrBot
   uv run main.py
   ```

2. 启动桌面应用:
   ```bash
   cd dashboard
   npm run tauri:dev
   ```

或直接运行打包后的应用（后端需要已启动）。

## 常见问题

### Q: 桌面应用无法连接到后端？

确保：
1. AstrBot 后端正在运行（`uv run main.py`）
2. 后端监听在 `127.0.0.1:6185`
3. 防火墙未阻止连接

### Q: 图标未显示？

检查 `src-tauri/icons/` 目录中是否有所需的图标文件，或使用 `npm run tauri icon` 命令生成。

### Q: 构建失败？

- 确保已安装 Rust 和系统依赖
- 运行 `cargo clean` 清理缓存后重试
- 检查 Rust 版本（需要 1.60+）

### Q: Web 端功能是否受影响？

不受影响。`npm run dev` 和 `npm run build` 的行为完全不变。

## 开发建议

1. **优先使用 Web 端开发**: 更快的热重载，更好的调试体验
2. **定期测试桌面端**: 确保跨平台兼容性
3. **使用环境检测**: 针对不同平台提供最佳体验
4. **注意 API 差异**: Web 和桌面端的某些 API 可能有差异

## 更多资源

- [Tauri 官方文档](https://tauri.app/)
- [Tauri API 参考](https://tauri.app/v1/api/js/)
- [Tauri Discord 社区](https://discord.com/invite/tauri)
