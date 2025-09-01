# Astrbot API

提供了 AstrBot 所有的适合插件使用的 api

## API 结构

astrbot.api: 包括了所有的导入
astrbot.api.all(将弃用): 包括了所有的导入, 由 astrbot.api 代替
astrbot.api.message_components(将弃用): 包括了所有消息组件, 由 astrbot.api.event.message.message_components 代替

astrbot.api.event: 包括了 AstrBot 事件以及相关类的导入
astrbot.api.event.filter(将弃用): 包括了事件过滤器, 用于注册 Handler, 由 astrbot.api.star.register 统一注册来代替
astrbot.api.event.message: 包括了 AstrBot 事件中, 所有有关消息的类
astrbot.api.api.event.message.message_components: 包括了所有消息组件

astrbot.api.platform: 包括了所有平台相关的导入

astrbot.api.provider: 包括了所有大模型供应商相关的导入

astrbot.api.star: 包括了所有插件相关的导入
astrbot.api.star.register: 包括了所有插件注册 Handler 相关的导入

astrbot.api.util: 包括了所有的实用工具的导入
