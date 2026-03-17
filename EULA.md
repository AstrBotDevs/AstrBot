# 最终用户许可协议（EULA）

> 我们热爱开源软件，并始终致力于为所有用户提供健康、安全、可靠的使用体验。 ❤️

For English edition, please refer to the section below the Chinese version.

**最后更新：** 2026-01-12

感谢您使用 **AstrBot**。
在使用本项目之前，请仔细阅读以下声明内容。

**您一旦安装、运行或使用本项目，即表示您已阅读、理解并同意本声明中的全部内容。**

## 1. 项目性质

AstrBot 是一个遵循 **GNU Affero General Public License v3（AGPLv3）** 协议发布的**免费开源软件项目**。

* 截至目前，AstrBot 项目未开展任何形式的商业化服务，AstrBot 团队也未通过本项目向用户提供任何收费服务。若您因使用 AstrBot 被要求付费，请务必提高警惕，谨防诈骗行为。
* AstrBot 的代码实现未对任何第三方系统进行逆向工程、破解、反编译或绕过安全机制等行为。AstrBot 仅使用并支持各即时通讯（IM）平台官方公开提供的机器人接入接口、开放平台能力或相关通信协议进行集成与通信。

## 2. 无担保声明

AstrBot 按“**现状（as is）**”提供，不附带任何形式的明示或暗示担保。

AstrBot 团队不对以下内容作出任何保证：

* 系统本身的安全性、可靠性或稳定性；
* 任何第三方插件的安全性、正确性或可信度；
* 任何第三方 AI 模型或外部服务 API 的可用性、质量、准确性或安全性；
* 本软件对任何特定用途的适用性。

**您使用本软件所产生的一切风险均由您自行承担。**

## 3. 第三方插件与服务

* AstrBot 支持第三方插件及外部 AI 服务接入；
* AstrBot 团队**不对任何第三方插件、扩展或服务进行审计、控制、背书或担保**；
* 因使用第三方插件或服务所产生的任何风险、损失、数据泄露或法律后果，均由用户自行承担。
* 第三方插件指代的是非 AstrBot 自带的插件，AstrBot 自带的插件指代的是插件实现代码已经包含在 AstrBotDevs/AstrBot 代码库中的插件。插件市场中的插件都是第三方插件。

## 4. 使用与内容限制

您同意不会将 AstrBot 用于以下行为：

* 输入、生成、传播或处理任何违法、极端、暴力、色情、仇恨、辱骂或其他有害内容；
* 从事违反您所在国家或地区法律法规，或任何适用国际法律的行为；
* 试图绕过、关闭、削弱或破坏本系统内置的安全机制或内容限制。
* 任何侵犯他人合法权益、损害他人和自己身心健康、涉及个人隐私、个人信息等敏感内容的内容。

## 5. 项目用途说明

AstrBot 是一个**工具型对话与 Agent 系统**，在**安全、健康、友善**的前提下提供有限的人性化交互能力。

项目的主要目标是：

* 提供 Agent 能力与自动化辅助；
* 帮助用户提升工作、学习和信息处理效率；
* 在合理范围内提供友好的人机交互体验。
* 辅助用户成长，提供有益于用户身心健康的内容。

## 6. 安全措施说明

AstrBot 团队**已尽合理努力在技术和策略层面设置安全与内容约束机制**，以引导系统输出健康、友善、安全的内容。

但请理解：

* 世界上任何的系统均无法保证完全无误、绝对安全或无法被滥用；
* 用户仍有责任自行合理配置、监督并正确使用本系统。

如果您要关闭 AstrBot 默认启用的“健康模式”，请在 cmd_config.json 中将 `provider_settings.llm_safety_mode` 设置为 `False`。但请注意，关闭健康模式不是推荐的使用方式，可能导致系统输出不安全或不适当的内容。关闭该功能所产生的任何风险与后果，均由用户自行承担，AstrBot 团队不对此承担任何责任。

## 7. 心理健康提示

如果您在使用本项目过程中因系统输出内容而感到心理不适、情绪困扰，  
或您本身正处于心理压力较大、情绪不稳定、焦虑、抑郁等状态并因此使用本项目，  
请优先考虑寻求来自专业人士的帮助，例如心理咨询师、心理医生或当地心理援助机构。

如遇紧急情况（例如存在自伤或他伤风险），请立即联系当地的紧急救助电话或专业机构。

## 8. 统计信息与隐私说明

AstrBot 可能会收集有限的匿名统计信息，用于了解系统使用情况、发现问题以及持续改进项目。

所收集的统计信息仅包括与系统运行和功能使用相关的基础技术指标，例如功能使用频率、错误信息等。

AstrBot **不会收集、上传或存储您的对话内容、消息正文、输入文本，或任何能够识别您个人身份的敏感信息**。

您可以手动关闭此项功能，通过在系统环境变量中设置 `ASTRBOT_DISABLE_METRICS=1` 来禁用匿名统计信息收集。

## 9. 责任限制

在法律允许的最大范围内，AstrBot 团队不对因以下原因导致的任何直接或间接损失承担责任，包括但不限于：

* 使用或无法使用本软件；
* 使用第三方插件或服务；
* 系统生成的内容或输出；
* 数据丢失、服务中断或安全事件。

## 10. 条款的接受

您一旦安装、运行、修改或使用 AstrBot，即确认：

* 您已阅读并理解本声明内容；
* 您同意并接受上述所有条款；
* 您对自身使用行为承担全部责任。

如您不同意本声明的任何内容，请勿使用本项目。

## 11. 许可与版权

AstrBot 的源代码、文档及相关内容受版权法及相关法律保护。

在遵守本声明及 AGPLv3 协议的前提下，AstrBot 授予您一项非独占、不可转让、不可再许可的许可，用于下载、安装、运行、修改和分发本软件。

除非法律另有规定或本声明另有明确说明，AstrBot 团队保留本项目的所有未明确授予的权利。

## 12. 适用法律

本声明的解释与适用应遵循您所在地或项目发布地适用的法律法规。

如本声明的任何条款被认定为无效或不可执行，其余条款仍然有效。

---

# EULA

> We love open-source software and are always committed to providing all users with a healthy, safe, and reliable experience. ❤️

**Last updated:** January 12, 2026

Thank you for using **AstrBot**.
Please read the following notice carefully before using this project.

**By installing, running, or using this project, you acknowledge that you have read, understood, and agreed to all the terms stated below.**

## 1. Nature of the Project

AstrBot is a **free and open-source software project** released under the **GNU Affero General Public License v3 (AGPLv3)**.

* AstrBot does not constitute any form of commercial service;
* The AstrBot Team does not provide any paid services through this project;
* AstrBot’s implementation does not involve reverse engineering, cracking, decompilation, or circumvention of security mechanisms of any third-party systems. AstrBot only uses and supports officially published bot integration interfaces, open platform capabilities, or related communication protocols provided by instant messaging (IM) platforms for integration and communication.

## 2. No Warranty

AstrBot is provided **“as is”**, without any express or implied warranties.

The AstrBot Team makes no guarantees regarding:

* The security, reliability, or stability of the system;
* The security, correctness, or trustworthiness of any third-party plugins;
* The availability, quality, accuracy, or safety of any third-party AI model APIs or external services;
* The fitness of the software for any particular purpose.

**All risks arising from the use of this software are borne solely by the user.**

## 3. Third-Party Plugins and Services

* AstrBot supports third-party plugins and external AI services;
* The AstrBot Team does **not audit, control, endorse, or guarantee** any third-party plugins, extensions, or services;
* Any risks, losses, data leaks, or legal consequences arising from the use of third-party plugins or services are solely the responsibility of the user;
* “Third-party plugins” refer to plugins that are not built into AstrBot. Built-in plugins are those whose implementation code is included in the AstrBotDevs/AstrBot repository. All plugins available in the plugin marketplace are third-party plugins.

## 4. Usage and Content Restrictions

You agree not to use AstrBot for any of the following activities:

* Inputting, generating, distributing, or processing any illegal, extremist, violent, pornographic, hateful, abusive, or otherwise harmful content;
* Engaging in activities that violate the laws or regulations of your country or region, or any applicable international laws;
* Attempting to bypass, disable, weaken, or undermine the built-in safety mechanisms or content restrictions of the system;
* Any activities that infringe upon the legitimate rights and interests of others, harm the physical or mental well-being of yourself or others, or involve personal privacy or sensitive personal information.

## 5. Intended Use

AstrBot is a **tool-oriented conversational and agent system** that provides limited human-like interaction capabilities under the principles of **safety, health, and friendliness**.

The primary goals of the project are to:

* Provide agent capabilities and automation assistance;
* Help users improve efficiency in work, study, and information processing;
* Offer a friendly human–computer interaction experience within reasonable boundaries;
* Support user growth and provide content beneficial to users’ physical and mental well-being.

## 6. Safety Measures

The AstrBot Team has made **reasonable efforts** at both technical and policy levels to implement safety and content restriction mechanisms, guiding the system to produce healthy, friendly, and safe outputs.

However, please understand that:

* No system in the world can be guaranteed to be completely error-free, absolutely secure, or immune to misuse;
* Users remain responsible for properly configuring, supervising, and using the system.

If you wish to disable AstrBot’s default “Safety Mode,” please set `provider_settings.llm_safety_mode` to `False` in `cmd_config.json`. However, please note that disabling Safety Mode is not recommended and may lead to unsafe or inappropriate outputs. Any risks or consequences arising from disabling this feature are solely borne by the user, and the AstrBot Team assumes no responsibility.

## 7. Mental Health Notice

If you experience psychological discomfort or emotional distress due to system outputs during use,
or if you are experiencing significant psychological stress, emotional instability, anxiety, or depression and are using this project for such reasons,
please prioritize seeking help from qualified professionals, such as psychologists, psychiatrists, or local mental health support services.

In case of emergency (for example, if there is a risk of self-harm or harm to others), please immediately contact your local emergency number or professional crisis support services.

## 8. Metrics and Privacy

AstrBot may collect a limited amount of anonymous usage statistics to understand system usage, identify issues, and continuously improve the project.

Collected metrics are limited to basic technical indicators related to system operation and feature usage, such as feature usage frequency and error information.

AstrBot **does not collect, upload, or store your conversation content, message bodies, input text, or any personally identifiable or sensitive information**.

You may manually disable this feature by setting the environment variable `ASTRBOT_DISABLE_METRICS=1` to turn off anonymous metrics collection.

## 9. Limitation of Liability

To the maximum extent permitted by law, the AstrBot Team shall not be liable for any direct or indirect losses arising from, including but not limited to:

* The use or inability to use this software;
* The use of third-party plugins or services;
* Generated content or system outputs;
* Data loss, service interruptions, or security incidents.

## 10. Acceptance of Terms

By installing, running, modifying, or using AstrBot, you confirm that:

* You have read and understood this Notice;
* You agree to and accept all the terms stated above;
* You assume full responsibility for your use of the software.

If you do not agree with any part of this Notice, please do not use this project.

## 11. License and Copyright

The source code, documentation, and related materials of AstrBot are protected by copyright laws and applicable regulations.

Subject to compliance with this Notice and the AGPLv3 license, AstrBot grants you a non-exclusive, non-transferable, non-sublicensable license to download, install, run, modify, and distribute this software.

Unless otherwise required by law or expressly stated in this Notice, the AstrBot Team reserves all rights not expressly granted.

## 12. Governing Law

The interpretation and application of this Notice shall be governed by the laws and regulations applicable in your jurisdiction or the jurisdiction where the project is released.

If any provision of this Notice is held to be invalid or unenforceable, the remaining provisions shall remain in full force and effect.
