![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

</p>

<div align="center">

<br>

<div>
<a href="https://trendshift.io/repositories/12875" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12875" alt="Soulter%2FAstrBot | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
<a href="https://hellogithub.com/repository/AstrBotDevs/AstrBot" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=d127d50cd5e54c5382328acc3bb25483&claim_uid=ZO9by7qCXgSd6Lp&t=2" alt="Featured｜HelloGitHub" style="width: 250px; height: 54px;" width="250" height="54" /></a>
</div>

<br>

<div>
<img src="https://img.shields.io/github/v/release/AstrBotDevs/AstrBot?style=for-the-badge&color=76bad9" href="https://github.com/AstrBotDevs/AstrBot/releases/latest">
<img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&color=76bad9" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg?style=for-the-badge&color=76bad9"/></a>
<a href="https://qm.qq.com/cgi-bin/qm/qr?k=wtbaNx7EioxeaqS9z7RQWVXPIxg2zYr7&jump_from=webapi&authKey=vlqnv/AV2DbJEvGIcxdlNSpfxVy+8vVqijgreRdnVKOaydpc+YSw4MctmEbr0k5"><img alt="QQ_community" src="https://img.shields.io/badge/QQ群-775869627-purple?style=for-the-badge&color=76bad9"></a>
<a href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>
<img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fplugin-num&query=%24.result&suffix=%E5%80%8B&style=for-the-badge&label=%E3%83%97%E3%83%A9%E3%82%B0%E3%82%A4%E3%83%B3&cacheSeconds=3600">
</div>

<br>

<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README.md">中文</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_en.md">English</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_zh-TW.md">繁體中文</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_fr.md">Français</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_ru.md">Русский</a>

<a href="https://astrbot.app/">ドキュメント</a> ｜
<a href="https://blog.astrbot.app/">Blog</a> ｜
<a href="https://astrbot.featurebase.app/roadmap">ロードマップ</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/issues">Issue</a>
</div>

AstrBot は、主要なインスタントメッセージングアプリと統合できるオープンソースのオールインワン Agent チャットボットプラットフォームです。個人、開発者、チームに信頼性が高くスケーラブルな会話型 AI インフラストラクチャを提供します。パーソナル AI コンパニオン、インテリジェントカスタマーサービス、オートメーションアシスタント、エンタープライズナレッジベースなど、AstrBot を使用すると、IM プラットフォームのワークフロー内で本番環境対応の AI アプリケーションを迅速に構築できます。

<img width="1776" height="1080" alt="image" src="https://github.com/user-attachments/assets/00782c4c-4437-4d97-aabc-605e3738da5c" />

## 主な機能

1. 💯 無料 & オープンソース。
2. ✨ AI 大規模言語モデル対話、マルチモーダル、Agent、MCP、ナレッジベース、ペルソナ設定。
3. 🤖 Dify、Alibaba Cloud 百炼、Coze などの Agent プラットフォームとの統合をサポート。
4. 🌐 マルチプラットフォーム：QQ、WeChat Work、Feishu、DingTalk、WeChat 公式アカウント、Telegram、Slack、[その他](#サポートされているメッセージプラットフォーム)。
5. 📦 約800個のプラグインをワンクリックでインストール可能なプラグイン拡張機能。
6. 💻 WebUI サポート。
7. 🌐 国際化（i18n）サポート。

## クイックスタート

#### Docker デプロイ（推奨 🥳）

Docker / Docker Compose を使用した AstrBot のデプロイを推奨します。

公式ドキュメント [Docker を使用した AstrBot のデプロイ](https://astrbot.app/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot) をご参照ください。

#### uv デプロイ

```bash
uvx astrbot
```

#### 宝塔パネルデプロイ

AstrBot は宝塔パネルと提携し、宝塔パネルに公開されています。

公式ドキュメント [宝塔パネルデプロイ](https://astrbot.app/deploy/astrbot/btpanel.html) をご参照ください。

#### 1Panel デプロイ

AstrBot は 1Panel 公式により 1Panel パネルに公開されています。

公式ドキュメント [1Panel デプロイ](https://astrbot.app/deploy/astrbot/1panel.html) をご参照ください。

#### 雨云でのデプロイ

AstrBot は雨云公式によりクラウドアプリケーションプラットフォームに公開され、ワンクリックでデプロイ可能です。

[![Deploy on RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://app.rainyun.com/apps/rca/store/5994?ref=NjU1ODg0)

#### Replit でのデプロイ

コミュニティ貢献によるデプロイ方法。

[![Run on Repl.it](https://repl.it/badge/github/AstrBotDevs/AstrBot)](https://repl.it/github/AstrBotDevs/AstrBot)

#### Windows ワンクリックインストーラーデプロイ

公式ドキュメント [Windows ワンクリックインストーラーを使用した AstrBot のデプロイ](https://astrbot.app/deploy/astrbot/windows.html) をご参照ください。

#### CasaOS デプロイ

コミュニティ貢献によるデプロイ方法。

公式ドキュメント [CasaOS デプロイ](https://astrbot.app/deploy/astrbot/casaos.html) をご参照ください。

#### 手動デプロイ

まず uv をインストールします:

```bash
pip install uv
```

Git Clone で AstrBot をインストール:

```bash
git clone https://github.com/AstrBotDevs/AstrBot && cd AstrBot
uv run main.py
```

または、公式ドキュメント [ソースコードから AstrBot をデプロイ](https://astrbot.app/deploy/astrbot/cli.html) をご参照ください。

## サポートされているメッセージプラットフォーム

**公式メンテナンス**

- QQ (公式プラットフォーム & OneBot)
- Telegram
- WeChat Work アプリケーション & WeChat Work インテリジェントボット
- WeChat カスタマーサービス & WeChat 公式アカウント
- Feishu (Lark)
- DingTalk
- Slack
- Discord
- Satori
- Misskey
- WhatsApp (近日対応予定)
- LINE (近日対応予定)

**コミュニティメンテナンス**

- [Matrix](https://github.com/stevessr/astrbot_plugin_matrix_adapter)
- [KOOK](https://github.com/wuyan1003/astrbot_plugin_kook_adapter)
- [VoceChat](https://github.com/HikariFroya/astrbot_plugin_vocechat)


## サポートされているモデルサービス

**大規模言語モデルサービス**

- OpenAI および互換サービス
- Anthropic
- Google Gemini
- Moonshot AI
- 智谱 AI
- DeepSeek
- Ollama (セルフホスト)
- LM Studio (セルフホスト)
- [優云智算](https://www.compshare.cn/?ytag=GPU_YY-gh_astrbot&referral_code=FV7DcGowN4hB5UuXKgpE74)
- [302.AI](https://share.302.ai/rr1M3l)
- [小馬算力](https://www.tokenpony.cn/3YPyf)
- [硅基流動](https://docs.siliconflow.cn/cn/usercases/use-siliconcloud-in-astrbot)
- [PPIO 派欧云](https://ppio.com/user/register?invited_by=AIOONE)
- ModelScope
- OneAPI

**LLMOps プラットフォーム**

- Dify
- Alibaba Cloud 百炼アプリケーション
- Coze

**音声認識サービス**

- OpenAI Whisper
- SenseVoice

**音声合成サービス**

- OpenAI TTS
- Gemini TTS
- GPT-Sovits-Inference
- GPT-Sovits
- FishAudio
- Edge TTS
- Alibaba Cloud 百炼 TTS
- Azure TTS
- Minimax TTS
- Volcano Engine TTS

## ❤️ コントリビューション

Issue や Pull Request は大歓迎です!このプロジェクトに変更を送信してください :)

### コントリビュート方法

Issue を確認したり、PR(プルリクエスト)のレビューを手伝うことで貢献できます。どんな Issue や PR への参加も歓迎され、コミュニティ貢献を促進します。もちろん、これらは提案に過ぎず、どんな方法でも貢献できます。新機能の追加については、まず Issue で議論してください。

### 開発環境

AstrBot はコードのフォーマットとチェックに `ruff` を使用しています。

```bash
git clone https://github.com/AstrBotDevs/AstrBot
pip install pre-commit
pre-commit install
```

## 🌍 コミュニティ

### QQ グループ

- 1群: 322154837
- 3群: 630166526
- 5群: 822130018
- 6群: 753075035
- 開発者群: 975206796

### Telegram グループ

<a href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

### Discord サーバー

<a href="https://discord.gg/hAVk6tgV36"><img alt="Discord_community" src="https://img.shields.io/badge/Discord-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

## ❤️ Special Thanks

AstrBot への貢献をしていただいたすべてのコントリビューターとプラグイン開発者に特別な感謝を ❤️

<a href="https://github.com/AstrBotDevs/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=AstrBotDevs/AstrBot" />
</a>

また、このプロジェクトの誕生は以下のオープンソースプロジェクトの助けなしには実現できませんでした:

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - 素晴らしい猫猫フレームワーク

## ⭐ Star History

> [!TIP]
> このプロジェクトがあなたの生活や仕事に役立ったり、このプロジェクトの今後の発展に関心がある場合は、プロジェクトに Star をください。これがこのオープンソースプロジェクトを維持する原動力です <3

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=astrbotdevs/astrbot&type=Date)](https://star-history.com/#astrbotdevs/astrbot&Date)

</div>

</details>

_私は、高性能ですから!_
