<!--Please describe the motivation for this change: What problem does it solve? (e.g., Fixes XX issue, adds YY feature)-->
<!--请描述此项更改的动机：它解决了什么问题？（例如：修复了 XX issue，添加了 YY 功能）-->

修复流式输出时思维链（reasoning content）没有前缀的问题。在非流式输出时，思维链会被添加 "🤔 思考:" 前缀，但流式输出时由于跳过结果装饰阶段，导致思维链内容和正文混在一起，没有换行分隔。

Fixes the issue where thinking chain (reasoning content) lacks prefix in streaming output. In non-streaming mode, thinking chain is prefixed with "🤔 思考:", but in streaming mode, the result decoration stage is skipped, causing thinking chain content to be mixed with the main text without line breaks.

### Modifications / 改动点

<!--Please summarize your changes: What core files were modified? What functionality was implemented?-->
<!--请总结你的改动：哪些核心文件被修改了？实现了什么功能？-->

1. `astrbot/core/agent/runners/tool_loop_agent_runner.py`
   - 在流式输出时，为思维链添加 "🤔 思考:" 前缀（仅添加一次）
   - 在流式输出的正文开始处添加分割线 `\n\u200b-------\n`（仅添加一次）
   - Add "🤔 思考:" prefix to thinking chain in streaming output (only once)
   - Add separator `\n\u200b-------\n` at the beginning of main content in streaming output (only once)

2. `astrbot/core/pipeline/result_decorate/stage.py`
   - 非流式输出时，思维链前缀已在原位置添加
   - Thinking chain prefix is already added in non-streaming mode

- [x] This is no longer a breaking change. / 这不是一个破坏性变更。
<!-- If your changes is a breaking change, please uncheck the checkbox above -->

### Screenshots or Test Results / 运行截图或测试结果

<!--Please paste screenshots, GIFs, or test logs here as evidence of executing the "Verification Steps" to prove this change is effective.-->
<!--请粘贴截图、GIF 或测试日志，作为执行"验证步骤"的证据，证明此改动有效。-->

流式输出前 / Before streaming:
```
思维链正文
Thinking chain content
```

流式输出后 / After streaming:
```
🤔 思考: 思维链
-------
正文内容...
```

---

### Checklist / 检查清单

<!--If merged, your code will serve tens of thousands of users! Please double-check the following items before submitting.-->
<!--如果分支被合并，您的代码将服务于数万名用户！在提交前，请核查一下几点内容。-->

- [x] 😊 If there are new features added in the PR, I have discussed it with the authors through issues/emails, etc.
  / 如果 PR 中有新加入的功能，已经通过 Issue / 邮件等方式和作者讨论过。

- [x] 👀 My changes have been well-tested, **and "Verification Steps" and "Screenshots" have been provided above**.
  / 我的更改经过了良好的测试，**并已在上方提供了"验证步骤"和"运行截图"**。

- [x] 🤓 I have ensured that no new dependencies are introduced, OR if new dependencies are introduced, they have been added to the appropriate locations in `requirements.txt` and `pyproject.toml`.
  / 我确保没有引入新依赖库，或者引入了新依赖库的同时将其添加到 `requirements.txt` 和 `pyproject.toml` 文件相应位置。

- [x] 😮 My changes do not introduce malicious code.
  / 我的更改没有引入恶意代码。
