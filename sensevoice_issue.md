## SenseVoice STT Provider: 配置后显示"not found"且缺少依赖处理

### 问题描述

在 Dashboard 中启用 SenseVoice STT 语音识别后，测试/检查 Provider 状态时显示：

```
Provider with id 'sensevoice' not found in provider_manager.
```

但实际上 `sensevoice_selfhosted_source.py` 源码文件是存在的。

### 复现步骤

**场景一（仅设置 STT 开关，未在 Provider 页添加）：**

1. 打开 Dashboard → 设置页 → 语音识别选项卡
2. 启用 STT，填写 `provider_id: "sensevoice"`
3. 切换到 Provider 页 → Speech-to-Text 选项卡
4. Provider 列表中不存在 sensevoice
5. 点击 Test → 显示 "not found"

**场景二（在 Provider 页添加了，但缺依赖）：**

1. 打开 Dashboard → Provider 页 → Speech-to-Text 选项卡
2. 点击 + 添加 Provider，选择 SenseVoice(Local)
3. 填写配置并保存 → 前端显示"添加成功"
4. 点击 Test → 仍显示 "not found"

### 根因分析

#### 1. 关键依赖未声明（需要手动安装）

`sensevoice_selfhosted_source.py` 顶部直接 import：

```python
from funasr_onnx import SenseVoiceSmall
```

但以下依赖均未列在项目的 `requirements.txt` / `pyproject.toml` 中：

| 依赖 | 用途 |
|------|------|
| `funasr_onnx` | ONNX 推理引擎 |
| `torch` | PyTorch 模型加载（ONNX 导出步骤需要） |
| `modelscope` | 从 ModelScope 下载模型 |
| `funasr` | 完整 funasr 库（ONNX 导出依赖） |
| `torchaudio` | funasr 间接依赖 |
| `onnxscript` | `torch.onnx` 导出需要 |

用户安装 AstrBot 时不会安装这些包，需要用户自行猜测并手动 pip install。

#### 2. `load_provider()` 加载失败时静默吞异常

`create_provider()` 流程：

```
用户点"添加" → 配置写入 cmd_config.json ✅ → load_provider() → import funasr_onnx 失败 ❌
                                                                          ↓
                                                              异常被捕获，只打了一行 log
                                                                          ↓
                                                               provider 不加入 inst_map
                                                                          ↓
                                                          前端显示"添加成功"（返回了 200 OK）
```

`load_provider()` 内部的 import 错误被捕获后既不向上抛异常，也不给前端返回错误信息。用户看到的是"添加成功"，但 provider 实际上没有被加载到内存。

`post_new_provider` 的代码路径：

```python
async def post_new_provider(self):
    new_provider_config = await request.json
    try:
        await self.core_lifecycle.provider_manager.create_provider(new_provider_config)
    except Exception as e:
        return Response().error(str(e)).__dict__    # ← 只有这里会报错
    return Response().ok(None, "新增服务提供商配置成功").__dict__
```

但 `create_provider()` 调用的 `load_provider()` 内部捕获了异常却没有 re-raise，所以 `post_new_provider` 永远走不到 except 分支。

#### 3. `check_one` 无法区分失败原因

`check_one_provider_status()` 只查 `inst_map.get(provider_id)`：

```python
target = prov_mgr.inst_map.get(provider_id)
if not target:
    return Response().error(f"Provider with id '{provider_id}' not found").__dict__
```

它无法区分三种情况：
- Provider 从未被添加（配置里就没有）
- Provider 添加了但加载失败（import error / 缺依赖）
- Provider 初始化失败（模型下载失败、ONNX 导出错误等）

统一报 "not found"，对用户没有任何排查帮助。

#### 4. ONNX 导出模型类型不匹配（依赖齐全后仍会遇到）

安装完所有依赖后，`SenseVoiceSmall(model_name, quantize=True)` 初始化时执行 ONNX 导出会出现：

```
Type Error: Type parameter (T) of Optype (Less) bound to different types
```

根因：导出的 `model_quant.onnx` 中有一个 `Less` 节点，其输入 `arange` 输出类型为 FLOAT（elem_type 1），但 `convert_element_type_default` 输出类型为 INT64（elem_type 7），导致 `Less` 节点的类型参数 `T` 绑定冲突。需要在 ONNX 图中插入 Cast 节点修复。

#### 5. Provider 配置流程存在断裂

STT 设置页的 `provider_stt_settings.provider_id` 和 Provider 页的 `provider` 列表是两个独立的功能。用户可能在设置页直接填写了 `provider_id: "sensevoice"`，但从未在 Provider 页添加过对应的 provider 条目。两者之间缺少联动检查或引导。

### 建议修复

1. **`sensevoice_selfhosted_source.py`**: 补充 `default_config_tmpl` 参数
2. **`pyproject.toml` / `requirements.txt`**: 将 `funasr_onnx` 及其依赖列为可选依赖（extra / optional）
3. **`provider/manager.py` `load_provider`**: 加载失败时向上抛异常或通过回调通知前端，而不是静默吞掉
4. **`provider/manager.py` / `check_one_provider_status`**: 在 provider 记录中保存加载错误信息，`check_one` 时一并返回，而不是笼统报 "not found"
5. **`sensevoice_selfhosted_source.py` `initialize()`**: ONNX 导出后自动修复类型不匹配（或改为直接使用 PyTorch 推理跳过 ONNX 导出）
6. **Dashboard 交互**: 配置页的 provider 选择器和 Provider 页之间增加联动，provider 不存在时给出明确引导

### 环境

- AstrBot 版本: v4.25.5
- 操作系统: Windows 11
- Python: 3.12
