# test_plugin/new

这个目录是运行时与集成测试夹具，不是给插件作者直接照抄的入门模板。

它的目标是覆盖更多 SDK surface，例如：

- 生命周期
- LLM / DB / Memory / Platform / HTTP / Metadata client
- 自定义 capability
- schedule / event / message / command handler

如果你是在找最小可学习示例，请改看：

- `examples/hello_plugin/`
