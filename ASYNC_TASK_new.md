我需要让 Agent 能够在未来提醒自己去做某些事情，这样 Agent 能够主动地去完成一些任务，而不是等用户主动来下达命令。

你需要实现一个 CronJob 系统，允许 Agent 创建未来任务，并且在未来的某个时间点自动触发这些任务的执行.

CronJob 系统分为 BasicCronJob 和 ActiveAgentCronJob 两种类型。前者只是简单的提供一个定时任务功能（给插件用），而后者则允许 Agent 主动地去完成一些任务。BasicCronJob 不必多说，就是定时执行某个函数。对于 ActiveAgentCronJob，Agent 应该可以主动管理（比如通过Tool来管理）这些 CronJobs，当添加的时候，Agent 可以给 CronJob 捎一段文字，以说明未来的自己需要做什么事情。比如说，Agent 在听到用户 “每天早上都给我整理一份今日早报” 之后，应该可以创建 Cron Job，并且自己写脚本来完成这个任务，并且注册 cron job。Agent 给未来的自己捎去的信息应该只是呈现为一段文字，这样可以保持设计简约。当触发后， CronJobManager 会调用 MainAgent 的一轮循环，MainAgent 通过上下文知道这是一个定时任务触发的循环，从而执行相应的操作。

此外，我还有一个需求，后台长任务。需要给当前的 FunctionTool 类增加一个属性，is_background_task: bool = False，插件可以通过这个属性来声明这是一个异步任务。这是为了解决一些 Tool 需要长时间运行的问题，比如 Deep Search tool 需要长时间搜索网页内容、Sub Agent 需要长时间运行来完成一个复杂任务。

基于上面的讨论，我觉得，应该：

1. 需要给当前的 FunctionTool 类增加一个属性is_background_task: bool = False，tool runner 在执行这个 tool 的时候，如果发现是后台任务，就不等待结果返回，而是直接返回一个任务 ID （已经创建成功提示）的结果，tool runner 在后台继续执行这个任务。当任务完成之后，任务的结果回传给 MainAgent（其实就是再执行一次 main agent loop，但是上下文应该是最新的），并且 MainAgent 此时应该有 send_message_to_user 的工具，通过这个工具可以选择是否主动通知用户任务完成的结果。
2. 增加一个 CronJobManager 类，负责管理所有的定时任务。Agent 可以通过调用这个类的方法来创建、删除、修改定时任务。通过 cron expression 来定义触发条件。
3. CronJobManager 除了管理普通的定时任务（比如插件可能有一些自己的定时任务），还有一种特殊的任务类型，就是上面提到的主动型 Agent 任务。用户提需求，MainAgent 选择性地调用 CronJobManager 的方法来创建这些任务，并且在任务触发时，CronJobManager 的回调就是执行 MainAgent 的一轮循环（需要加 send_message_to_user tool），MainAgent 通过上下文知道这是一个定时任务触发的循环，从而执行相应的操作。
4. WebUI 需要增加 Cron Job 管理界面，用户可以在界面上查看、创建、修改、删除定时任务。对于主动型 Agent 任务，用户可以看到任务的描述、触发条件等信息。
5. 除此之外，现在的代码中已经有了 subagent 的管理。WebUI 可以创建 SubAgent，但是还没写完。除了结合上面我说的之外，你还需要将 SubAgent 与 Persona 结合起来——因为 Persona 是一个包含了 tool、skills、name、description 的完整体，所以 SubAgent 应该直接继承 Persona 的定义，而不是单独定义 SubAgent。SubAgent 本质上就是一个有特定角色和能力的 Persona！多么美妙的设计啊！
6. 为了实现大一统，is_background_task = True 的时候，后台任务也挂到 CronJobManager 上去管理，只不过这个是立即触发的任务，不需要等到未来某个时间点才触发罢了。

我希望设计尽可能简单，但是强大。
