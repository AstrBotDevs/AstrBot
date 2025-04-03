<p align="center">
    
![6e1279651f16d7fdf4727558b72bbaf1](https://github.com/user-attachments/assets/ead4c551-fc3c-48f7-a6f7-afbfdb820512)

</p>

<div align="center">

_✨ 簡単に使えるマルチプラットフォーム LLM チャットボットおよび開発フレームワーク ✨_

<a href="https://trendshift.io/repositories/12875" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12875" alt="Soulter%2FAstrBot | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Soulter/AstrBot)](https://github.com/Soulter/AstrBot/releases/latest)
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg"/></a>
<img alt="Static Badge" src="https://img.shields.io/badge/QQ群-630166526-purple">
[![wakatime](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e.svg)](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e)
![Dynamic JSON Badge](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fstats&query=v&label=7%E6%97%A5%E6%B6%88%E6%81%AF%E4%B8%8A%E8%A1%8C%E9%87%8F&cacheSeconds=3600)
[![codecov](https://codecov.io/gh/Soulter/AstrBot/graph/badge.svg?token=FF3P5967B8)](https://codecov.io/gh/Soulter/AstrBot)

<a href="https://astrbot.app/">ドキュメントを見る</a> ｜
<a href="https://github.com/Soulter/AstrBot/issues">問題を報告する</a>
</div>

AstrBot は、疎結合、非同期、複数のメッセージプラットフォームに対応したデプロイ、使いやすいプラグインシステム、および包括的な大規模言語モデル（LLM）接続機能を備えたチャットボットおよび開発フレームワークです。

## ✨ 主な機能

1. **大規模言語モデルの対話**。OpenAI API、Google Gemini、Llama、Deepseek、ChatGLM など、さまざまな大規模言語モデルをサポートし、Ollama、LLMTuner を介してローカルにデプロイされた大規模モデルをサポートします。多輪対話、人格シナリオ、多モーダル機能を備え、画像理解、音声からテキストへの変換（Whisper）をサポートします。
2. **複数のメッセージプラットフォームの接続**。QQ（OneBot）、QQ チャンネル、WeChat（Gewechat）、Feishu、Telegram への接続をサポートします。今後、DingTalk、Discord、WhatsApp、Xiaoai 音響をサポートする予定です。レート制限、ホワイトリスト、キーワードフィルタリング、Baidu コンテンツ監査をサポートします。
3. **エージェント**。一部のエージェント機能をネイティブにサポートし、コードエグゼキューター、自然言語タスク、ウェブ検索などを提供します。[Dify プラットフォーム](https://dify.ai/)と連携し、Dify スマートアシスタント、ナレッジベース、Dify ワークフローを簡単に接続できます。
4. **プラグインの拡張**。深く最適化されたプラグインメカニズムを備え、[プラグインの開発](https://astrbot.app/dev/plugin.html)をサポートし、機能を拡張できます。複数のプラグインのインストールをサポートします。
5. **ビジュアル管理パネル**。設定の視覚的な変更、プラグイン管理、ログの表示などをサポートし、設定の難易度を低減します。WebChat を統合し、パネル上で大規模モデルと対話できます。
6. **高い安定性と高いモジュール性**。イベントバスとパイプラインに基づくアーキテクチャ設計により、高度にモジュール化され、低結合です。

> [!TIP]
> 管理パネルのオンラインデモを体験する: [https://demo.astrbot.app/](https://demo.astrbot.app/)
> 
> ユーザー名: `astrbot`, パスワード: `astrbot`。LLM が設定されていないため、チャットページで大規模モデルを使用することはできません。（デモのログインパスワードを変更しないでください 😭）

## ✨ 使用方法

#### Docker デプロイ

公式ドキュメント [Docker を使用して AstrBot をデプロイする](https://astrbot.app/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot) を参照してください。

#### Windows ワンクリックインストーラーのデプロイ

コンピュータに Python（>3.10）がインストールされている必要があります。公式ドキュメント [Windows ワンクリックインストーラーを使用して AstrBot をデプロイする](https://astrbot.app/deploy/astrbot/windows.html) を参照してください。

#### Replit デプロイ

[![Run on Repl.it](https://repl.it/badge/github/Soulter/AstrBot)](https://repl.it/github/Soulter/AstrBot)

#### CasaOS デプロイ

コミュニティが提供するデプロイ方法です。

公式ドキュメント [ソースコードを使用して AstrBot をデプロイする](https://astrbot.app/deploy/astrbot/casaos.html) を参照してください。

#### 手動デプロイ

公式ドキュメント [ソースコードを使用して AstrBot をデプロイする](https://astrbot.app/deploy/astrbot/cli.html) を参照してください。

## ⚡ メッセージプラットフォームのサポート状況

| プラットフォーム    | サポート状況 | 詳細 | メッセージタイプ |
| -------- | ------- | ------- | ------ |
| QQ(公式ロボットインターフェース) | ✔    | プライベートチャット、グループチャット、QQ チャンネルプライベートチャット、グループチャット | テキスト、画像 |
| QQ(OneBot)      | ✔    | プライベートチャット、グループチャット | テキスト、画像、音声 |
| WeChat(個人アカウント)    | ✔    | WeChat 個人アカウントのプライベートチャット、グループチャット | テキスト、画像、音声 |
| [Telegram](https://github.com/Soulter/astrbot_plugin_telegram)   | ✔    | プライベートチャット、グループチャット | テキスト、画像 |
| [WeChat(企業 WeChat)](https://github.com/Soulter/astrbot_plugin_wecom)    | ✔    | プライベートチャット | テキスト、画像、音声 |
| Feishu   | ✔    | グループチャット | テキスト、画像 |
| WeChat 対話オープンプラットフォーム | 🚧    | 計画中 | - |
| Discord   | 🚧    | 計画中 | - |
| WhatsApp   | 🚧    | 計画中 | - |
| Xiaoai 音響   | 🚧    | 計画中 | - |

# 🦌 今後のロードマップ

> [!TIP]
> Issue でさらに多くの提案を歓迎します <3

- [ ] 現在のすべてのプラットフォームアダプターの機能の一貫性を確保し、改善する
- [ ] プラグインインターフェースの最適化
- [ ] GPT-Sovits などの TTS サービスをデフォルトでサポート
- [ ] "チャット強化" 部分を完成させ、永続的な記憶をサポート
- [ ] i18n の計画

## ❤️ 貢献

Issue や Pull Request を歓迎します！このプロジェクトに変更を加えるだけです :)

新機能の追加については、まず Issue で議論してください。

## 🌟 サポート

- このプロジェクトに Star を付けてください！
- [愛発電](https://afdian.com/a/soulter)で私をサポートしてください！
- [WeChat](https://drive.soulter.top/f/pYfA/d903f4fa49a496fda3f16d2be9e023b5.png)で私をサポートしてください~

## ✨ デモ

> [!NOTE]
> コードエグゼキューターのファイル入力/出力は現在 Napcat(QQ)、Lagrange(QQ) でのみテストされています

<div align='center'>

<img src="https://github.com/user-attachments/assets/4ee688d9-467d-45c8-99d6-368f9a8a92d8" width="600">

_✨ Docker ベースのサンドボックス化されたコードエグゼキューター（ベータテスト中）✨_

<img src="https://github.com/user-attachments/assets/0378f407-6079-4f64-ae4c-e97ab20611d2" height=500>

_✨ 多モーダル、ウェブ検索、長文の画像変換（設定可能）✨_

<img src="https://github.com/user-attachments/assets/8ec12797-e70f-460a-959e-48eca39ca2bb" height=100>

_✨ 自然言語タスク ✨_

<img src="https://github.com/user-attachments/assets/e137a9e1-340a-4bf2-bb2b-771132780735" height=150>
<img src="https://github.com/user-attachments/assets/480f5e82-cf6a-4955-a869-0d73137aa6e1" height=150>

_✨ プラグインシステム - 一部のプラグインの展示 ✨_

<img src="https://github.com/user-attachments/assets/592a8630-14c7-4e06-b496-9c0386e4f36c" width="600">

_✨ 管理パネル ✨_

![webchat](https://drive.soulter.top/f/vlsA/ezgif-5-fb044b2542.gif)

_✨ 内蔵 Web Chat、オンラインでボットと対話 ✨_

</div>

## ⭐ Star History

> [!TIP] 
> このプロジェクトがあなたの生活や仕事に役立った場合、またはこのプロジェクトの将来の発展に関心がある場合は、プロジェクトに Star を付けてください。これはこのオープンソースプロジェクトを維持するためのモチベーションです <3

<div align="center">
    
[![Star History Chart](https://api.star-history.com/svg?repos=soulter/astrbot&type=Date)](https://star-history.com/#soulter/astrbot&Date)

</div>

## スポンサー

[<img src="https://api.gitsponsors.com/api/badge/img?id=575865240" height="20">](https://api.gitsponsors.com/api/badge/link?p=XEpbdGxlitw/RbcwiTX93UMzNK/jgDYC8NiSzamIPMoKvG2lBFmyXhSS/b0hFoWlBBMX2L5X5CxTDsUdyvcIEHTOfnkXz47UNOZvMwyt5CzbYpq0SEzsSV1OJF1cCo90qC/ZyYKYOWedal3MhZ3ikw==)

## 免責事項

1. このプロジェクトは `AGPL-v3` オープンソースライセンスの下で保護されています。
2. WeChat（個人アカウント）のデプロイメントには [Gewechat](https://github.com/Devo919/Gewechat) サービスを利用しています。AstrBot は Gewechat との接続を保証するだけであり、アカウントのリスク管理に関しては、このプロジェクトの著者は一切の責任を負いません。
3. このプロジェクトを使用する際は、現地の法律および規制を遵守してください。

<!-- ## ✨ ATRI [ベータテスト]

この機能はプラグインとしてロードされます。プラグインリポジトリのアドレス：[astrbot_plugin_atri](https://github.com/Soulter/astrbot_plugin_atri)

1. 《ATRI ~ My Dear Moments》の主人公 ATRI のキャラクターセリフを微調整データセットとして使用した `Qwen1.5-7B-Chat Lora` 微調整モデル。
2. 長期記憶
3. ミームの理解と返信
4. TTS
    -->


_私は、高性能ですから!_

