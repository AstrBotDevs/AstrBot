总览：对于 chat_completion 的提供商，目前需要将 provider 分成 provider_source 和 provider 两个部分，这样可以更好地支持同一 provider_source 下的多模型添加。

目前已经在 astrbot/core/config/default.py 中对 provider 配置进行了拆分，接下来需要修改：

## provider/manager 部分：

需要传入 provider_sources 给 ProviderManager，然后在创建 provider 的时候:

1. 如果 provider.provider_source_id 存在且不为空，则从 provider_sources 中找到对应的 provider_source，并将 provider_source 的配置合并到 provider_config 中。provider 的配置优先级更高。
2. 如果 provider.provider_source_id 不存在或为空，则使用 provider 自身的配置。

## WebUI 部分：

我们主要需要大量修改 ProviderPage.vue 文件。

将整体页面换成左右多栏布局。

分为 三个 栏目：

1. 左第一个栏目用于选择 provider type。
2. 中间第二个栏目用于选择 provider source。
3. 右第三个栏目用于配置 provider。

中间的栏目最上面有一个添加按钮，点击后会出现一个 dropdown，列出所有的 provider source type，选择后会在中间栏目添加一个 provider source。

选中某个 provider source 后，右侧栏目会显示该 provider source 的配置。指向这个 provider source 的 provider 本质上是 model 的配置。在 provider source 配置下面，会有一个“获取模型”的按钮（如果没有保存/更新 source 配置，则写“保存并获取模型”），点击后会在下方有一个 v-list 列出该 provider source 支持的所有模型，选择后会在下方增加一个新的模型配置（也就是provider的配置）。整个过程从设计上看不要有任何 dialog。

有一个保存按钮，用于保存当前 provider source 和 provider 的配置。

### 模型列表的获取

需要增加一个 API，用于获取某个 provider source 支持的模型列表。前端在点击“添加模型”按钮时，调用该 API 获取模型列表并展示在 dropdown 中。

GET /config/provider_sources/<provider_source_id>/models

本质上这个会初始化一下 Provider，然后调用 Provider.get_models() 来获取模型列表，然后销毁 Provider 实例。

### 测试模型

在 provider 的配置那里，增加一个“测试模型”按钮，类同现在的测试功能。

## 迁移

需要编写一个迁移脚本，将现有的 provider 配置拆分成 provider_source 和 provider 两部分，provider_source 的配置从现有的 provider 中提取公共部分，provider 则只保留模型相关的配置。

仅对 chat_completion 类型的 provider 进行迁移，其他类型的 provider 保持不变。

可以在 astrbot/core/utils/migra_helper.py 的 migra 方法中添加迁移逻辑。

## UI 风格

整体风格需要现代化、简洁化，不要使用任何渐变。

## 其他

请最小化改动。