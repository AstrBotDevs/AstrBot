### main.py

msg-5e25709f = このプロジェクトを実行するにはPython3.10以上を使用してください。
msg-afd0ab81 = 指定されたWebUIディレクトリを使用します：{ $webui_dir }
msg-7765f00f = 指定されたWebUIディレクトリ{ $webui_dir }存在しません、デフォルトのロジックが使用されます。
msg-9af20e37 = WebUIバージョンはすでに最新です。
msg-9dd5c1d2 = 検出されたWebUIバージョン ({ $v }) および現在のAstrBotバージョン (v{ $VERSION }) が一致しません。
msg-ec714d4e = 管理パネルのファイルをダウンロードしています…ピーク時（夜間）は速度が低下する可能性があります。ダウンロードが複数回失敗する場合は、https://github.com/AstrBotDevs/AstrBot/releases/latest から dist.zip をダウンロードし、dist フォルダを data ディレクトリに解凍してください。
msg-c5170c27 = 管理パネルファイルのダウンロードに失敗しました：{ $e }.
msg-e1592ad1 = 管理パネルのダウンロードが完了しました。
msg-fe494da6 = { $logo_tmpl }

### astrbot/core/lang.py

msg-d103bc8e = 名前空間は空であってはなりません。
msg-f66527da = 名前空間には '.' を含めることはできません。
msg-b3665aee = ロケールディレクトリが存在しません:{ $base_dir }
msg-3fe89e6a = ロケールディレクトリが見つかりません。場所:{ $base_dir }
msg-c79b2c75 = 名前空間 '{ $namespace }既に存在します。上書きするにはreplace=Trueを設定してください。
msg-7db3fccf = デフォルト名前空間は登録解除できません。
msg-3d066f64 = 名前空間{ $namespace }は登録されていません。

### astrbot/core/persona_mgr.py

msg-51a854e6 = 読み込まれました{ $res }パーソナリティ。
msg-1ea88f45 = IDを持つペルソナ{ $persona_id }存在しません。
msg-28104dff = IDを持つペルソナ{ $persona_id }既に存在します。
msg-08ecfd42 = { $res }人格シナリオのプリセット対話形式が正しくありません。エントリ数は偶数である必要があります。
msg-b6292b94 = Persona設定の解析に失敗しました：{ $e }

### astrbot/core/initial_loader.py

msg-78b9c276 = { $res }
msg-58525c23 = 😭 AstrBotの初期化に失敗しました:{ $e }!!!
msg-002cc3e8 = 🌈 AstrBotをシャットダウンしています...

### astrbot/core/log.py

msg-80a186b8 = ファイルシンクの追加に失敗しました:{ $e }

### astrbot/core/astrbot_config_mgr.py

msg-7875e5bd = 設定ファイル{ $conf_path }UUID用{ $uuid_ }存在しません、スキップします。
msg-39c4fd49 = デフォルトの設定ファイルは削除できません
msg-cf7b8991 = 構成ファイル{ $conf_id }マッピングに存在しません
msg-2aad13a4 = 削除された設定ファイル：{ $conf_path }
msg-94c359ef = 設定ファイルを削除{ $conf_path }失敗：{ $e }
msg-44f0b770 = 設定ファイルが正常に削除されました{ $conf_id }
msg-737da44e = デフォルト設定ファイル内の情報を更新できません
msg-9d496709 = 設定ファイルが正常に更新されました{ $conf_id }情報

### astrbot/core/zip_updator.py

msg-24c90ff8 = リクエスト{ $url }失敗しました、ステータスコード：{ $res }, コンテンツ:{ $text }
msg-14726dd8 = リクエストが失敗しました、ステータスコード:{ $res }
msg-fc3793c6 = バージョン情報の解析中に例外が発生しました：{ $e }
msg-491135d9 = バージョン情報の解析に失敗しました
msg-03a72cb5 = 適切なリリースバージョンが見つかりません
msg-8bcbfcf0 = 更新をダウンロード中{ $repo }翻訳するテキスト：...
msg-ccc87294 = 指定されたブランチから取得中{ $branch }ダウンロード{ $author }翻訳対象のテキスト：{ $repo }
msg-dfebcdc6 = 取得する{ $author }翻訳対象のテキスト：{ $repo }GitHubリリースが失敗しました：{ $e }、デフォルトブランチのダウンロードを試みます
msg-e327bc14 = デフォルトブランチからダウンロード中{ $author }翻訳対象のテキスト：{ $repo }
msg-3cd3adfb = ミラーサイトを検出しました。ダウンロードにはミラーサイトを使用します。{ $author }翻訳するテキスト：{ $repo }リポジトリソースコード：{ $release_url }
msg-1bffc0d7 = 無効なGitHub URL
msg-0ba954db = ファイルの解凍が完了しました:{ $zip_path }
msg-90ae0d15 = 一時的な更新ファイルを削除します:{ $zip_path }そして{ $res }
msg-f8a43aa5 = 更新ファイルの削除に失敗しました。手動で削除できます。{ $zip_path }そして{ $res }

### astrbot/core/file_token_service.py

msg-0e444e51 = ファイルが存在しません:{ $local_path }翻訳するテキスト: (元の入力:{ $file_path }翻訳対象テキスト：
msg-f61a5322 = 無効または期限切れのファイルトークン：{ $file_token }
msg-73d3e179 = ファイルが存在しません：{ $file_path }

### astrbot/core/subagent_orchestrator.py

msg-5d950986 = subagent_orchestrator.agents はリストでなければなりません
msg-29e3b482 = サブエージェントペルソナ %s が見つかりませんでした。インラインプロンプトにフォールバックします。
msg-f425c9f0 = 登録済みサブエージェントハンドオフツール：{ $res }

### astrbot/core/astr_main_agent.py

msg-8dcf5caa = 指定されたプロバイダが見つかりませんでした: %s。
msg-61d46ee5 = 選択されたプロバイダタイプが無効です（%s）、LLMリクエスト処理をスキップします。
msg-496864bc = プロバイダーの選択中にエラーが発生しました: %s
msg-507853eb = 新しい会話を作成できません。
msg-66870b7e = ナレッジベースの取得中にエラーが発生しました: %s
msg-36dc1409 = ファイル抽出用のMoonshot AI APIキーが設定されていません
msg-8534047e = サポートされていないファイル抽出プロバイダ: %s
msg-f2ea29f4 = プロバイダー ` の画像キャプションを取得できません。{ $provider_id }存在しません。
msg-91a70615 = 画像のキャプションを取得できません。プロバイダー `{ $provider_id }は有効なプロバイダーではありません、それは{ $res }.
msg-b1840df0 = プロバイダーで画像キャプションを処理中: %s
msg-089421fc = 画像の説明の処理に失敗しました：%s
msg-719d5e4d = 引用内の画像キャプション作成のためのプロバイダが見つかりません。
msg-e16a974b = 参照画像の処理に失敗しました: %s
msg-037dad2e = グループ名の表示は有効ですが、グループオブジェクトがNoneです。グループID: %s
msg-58b47bcd = タイムゾーン設定エラー: %s、ローカルタイムゾーンを使用中
msg-938af433 = プロバイダー %s は画像をサポートしていません、プレースホルダーを使用しています。
msg-83d739f8 = プロバイダ %s は tool_use をサポートしていません。ツールをクリアします。
msg-3dbad2d9 = sanitize_context_by_modalities が適用されました：削除された画像ブロック=%s、削除されたツールメッセージ=%s、削除されたツール呼び出し=%s
msg-4214b760 = セッション %s の生成されたチャットUIタイトル: %s
msg-cb6db56e = サポートされていない llm_safety_mode 戦略: %s。
msg-7ea2c5d3 = Shipyard サンドボックスの設定が不完全です。
msg-9248b273 = 指定されたコンテキスト圧縮モデル %s が見つかりませんでした。圧縮はスキップされます。
msg-16fe8ea5 = 指定されたコンテキスト圧縮モデル %s は会話型モデルではないため、圧縮からスキップされます。
msg-c6c9d989 = fallback_chat_models設定がリストではありません。フォールバックプロバイダーをスキップします。
msg-614aebad = フォールバックチャットプロバイダー `%s` が見つかりません、スキップします。
msg-1a2e87dd = フォールバックチャットプロバイダ `%s` は無効なタイプです：%s、スキップします。
msg-ee979399 = 会話モデル（プロバイダー）が見つかりません。LLMリクエストの処理をスキップします。
msg-7a7b4529 = 制限=%d、umo=%s のため、引用されたフォールバック画像をスキップします
msg-46bcda31 = 引用されたフォールバック画像を切り詰めます: umo=%s, reply_id=%s, %d から %d へ
msg-cbceb923 = フォールバック引用画像の解決に失敗しました umo=%s, reply_id=%s: %s
msg-31483e80 = ファイル抽出の適用中にエラーが発生しました: %s

### astrbot/core/umop_config_router.py

msg-dedcfded = umopキーは、[platform_id]:[message_type]:[session_id]の形式で文字列である必要があり、任意のワイルドカード*またはすべてを表す空が使用できます。
msg-8e3a16f3 = umopは、[platform_id]:[message_type]:[session_id]の形式の文字列でなければなりません。任意のワイルドカード*または空で全てを指定できます。

### astrbot/core/event_bus.py

msg-da466871 = ID用のPipelineSchedulerが見つかりませんでした:{ $res }, イベントは無視されました。
msg-7eccffa5 = 翻訳対象のテキスト：{ $conf_name }] [{ $res }翻訳するテキスト：{ $res_2 })]{ $res_3 }翻訳対象テキスト：{ $res_4 }翻訳するテキスト：{ $res_5 }
msg-88bc26f2 = 翻訳対象テキスト：{ $conf_name }] [{ $res }翻訳対象のテキスト：{ $res_2 })]{ $res_3 }翻訳対象のテキスト：{ $res_4 }

### astrbot/core/astr_agent_tool_exec.py

msg-e5f2fb34 = バックグラウンドタスク{ $task_id }失敗しました：{ $e }
msg-c54b2335 = バックグラウンド・ハンドオフ{ $task_id }翻訳対象テキスト：{ $res }) 失敗しました:{ $e }
msg-8c2fe51d = バックグラウンドタスクのメインエージェントのビルドに失敗しました{ $tool_name }.
msg-c6d4e4a6 = バックグラウンドタスクエージェントが応答なし
msg-0b3711f1 = ローカル関数ツールにはイベントを指定する必要があります。
msg-8c19e27a = ツールには有効なハンドラーが必要です。または'run'メソッドをオーバーライドしてください。
msg-24053a5f = ツールが直接メッセージを送信できませんでした:{ $e }
msg-f940b51e = ツール{ $res }実行タイムアウト{ $res_2 }秒。
msg-7e22fc8e = 不明なメソッド名:{ $method_name }
msg-c285315c = ツール実行エラー ValueError:{ $e }
msg-41366b74 = ツールハンドラのパラメータ不一致、ハンドラ定義を確認してください。ハンドラパラメータ：{ $handler_param_str }
msg-e8cadf8e = ツール実行エラー：{ $e }. トレースバック:{ $trace_ }
msg-d7b4aa84 = 前回のエラー：{ $trace_ }

### astrbot/core/astr_agent_run_util.py

msg-6b326889 = エージェントが最大ステップ数に到達しました（{ $max_step })、最終的な応答を強制します。
msg-bb15e9c7 = { $status_msg }
msg-78b9c276 = { $res }
msg-9c246298 = エージェント完了フックでのエラー
msg-34f164d4 = { $err_msg }
msg-6d9553b2 = [ライブエージェント] ストリーミングTTSの利用（get_audio_streamをネイティブサポート）
msg-becf71bf = [Live Agent] TTS の使用 ({ $res }get_audioを使用すると、文単位のチャンクで音声が生成されます
msg-21723afb = [Live Agent] ランタイムエラーが発生しました:{ $e }
msg-ca1bf0d7 = TTS統計の送信に失敗しました:{ $e }
msg-5ace3d96 = [ライブエージェントフィーダー] 文セグメンテーション：{ $temp_buffer }
msg-bc1826ea = [Live Agent Feeder] エラー：{ $e }
msg-a92774c9 = [ライブTTSストリーム] エラー:{ $e }
msg-d7b3bbae = [ライブTTSシミュレーション] テキスト '{ $res }'...':{ $e }
msg-035bca5f = [ライブTTSシミュレーション] 致命的エラー:{ $e }

### astrbot/core/astr_main_agent_resources.py

msg-509829d8 = サンドボックスからファイルをダウンロードしました:{ $path }->{ $local_path }
msg-b462b60d = サンドボックスからファイルをチェック/ダウンロードできませんでした:{ $e }
msg-0b3144f1 = [ナレッジベース] セッション{ $umo }ナレッジベースを使用しないように設定されています。
msg-97e13f98 = [ナレッジベース] ナレッジベースが存在しないか、ロードされていません：{ $kb_id }
msg-312d09c7 = [ナレッジベース] セッション{ $umo }次の設定された知識ベースは無効です：{ $invalid_kb_ids }
msg-42b0e9f8 = [ナレッジベース] セッションレベル設定を使用したナレッジベース数：{ $res }
msg-08167007 = [ナレッジベース] グローバル設定を使用、ナレッジベースの数：{ $res }
msg-a00becc3 = [ナレッジベース] ナレッジベースの検索を開始します、件数：{ $res }, top_k={ $top_k }
msg-199e71b7 = [ナレッジベース] 会話用{ $umo }インジェクション{ $res }ナレッジブロック

### astrbot/core/conversation_mgr.py

msg-86f404dd = セッション削除コールバックの実行に失敗しました（セッション：{ $unified_msg_origin }):{ $e }
msg-57dcc41f = ID {$id} との会話{ $cid }見つかりません

### astrbot/core/updator.py

msg-e3d42a3b = 終了中{ $res }子プロセス。
msg-e7edc4a4 = 子プロセスを終了中です{ $res }
msg-37bea42d = 子プロセス{ $res }正常に終了せず、強制終了を実行します。
msg-cc6d9588 = 再起動に失敗しました ({ $executable }{ $e }手動で再起動してみてください。
msg-0e4439d8 = この方法で開始されたAstrBotの更新はサポートされていません。
msg-3f39a942 = 現在のバージョンはすでに最新です。
msg-c7bdf215 = バージョン番号が見つかりません{ $version }ファイルを更新します。
msg-92e46ecc = コミットハッシュの長さが正しくありません。40文字である必要があります。
msg-71c01b1c = 指定されたバージョンへのAstrBot Core更新準備中：{ $version }
msg-d3a0e13d = AstrBot Core アップデートファイルのダウンロードが完了しました。現在展開中です...

### astrbot/core/core_lifecycle.py

msg-9967ec8b = プロキシを使用中：{ $proxy_config }
msg-5a29b73d = HTTPプロキシをクリアしました
msg-fafb87ce = サブエージェントオーケストレータの初期化に失敗しました：{ $e }
msg-f7861f86 = AstrBotの移行に失敗しました:{ $e }
msg-78b9c276 = { $res }
msg-967606fd = タスク{ $res }エラーが発生しました:{ $e }
msg-a2cd77f3 = 翻訳対象のテキスト：{ $line }
msg-1f686eeb = 翻訳対象テキスト：
msg-9556d279 = AstrBot の起動が完了しました。
msg-daaf690b = フック(on_astrbot_loaded) ->{ $res }-{ $res_2 }
msg-4719cb33 = プラグイン{ $res }適切に終了されていません{ $e }リソースリークやその他の問題を引き起こす可能性があります。
msg-c3bbfa1d = タスク{ $res }エラーが発生しました：{ $e }
msg-af06ccab = 構成ファイル{ $conf_id }存在しません

### astrbot/core/pipeline/context_utils.py

msg-49f260d3 = ハンドラ関数のパラメータが一致しません、ハンドラの定義を確認してください。
msg-d7b4aa84 = 前回のエラー:{ $trace_ }
msg-eb8619cb = フック{ $res }) ->{ $res_2 }-{ $res_3 }
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }イベント伝播を終了しました。

### astrbot/core/pipeline/__init__.py


### astrbot/core/pipeline/scheduler.py

msg-c240d574 = ステージ{ $res }イベント伝播は終了しました。
msg-609a1ac5 = パイプラインの実行が完了しました。

### astrbot/core/pipeline/rate_limit_check/stage.py

msg-18092978 = セッション{ $session_id }レート制限中。レート制限ポリシーに従い、このセッションの処理は一時停止されます。{ $stall_duration }2番目
msg-4962387a = セッション{ $session_id }レート制限されています。レート制限ポリシーに従い、このリクエストはクォータがリセットされるまで破棄されます。リセット時間は{ $stall_duration }数秒でリセット。

### astrbot/core/pipeline/whitelist_check/stage.py

msg-8282c664 = セッションID{ $res }会話ホワイトリストに含まれていません。イベントの伝播は終了しました。設定ファイルで会話IDをホワイトリストに追加してください。

### astrbot/core/pipeline/process_stage/follow_up.py

msg-df881b01 = アクティブエージェント実行のフォローアップメッセージをキャプチャしました、umo=%s、order_seq=%s

### astrbot/core/pipeline/process_stage/method/agent_request.py

msg-3267978a = LLMチャットの追加のウェイクアッププレフィックスを特定{ $res }ロボットのウェイクアップ接頭辞{ $bwp }開始、自動的に削除されました。
msg-97a4d573 = このパイプラインはAI機能を有効にしていないため、処理をスキップします。
msg-f1a11d2b = セッション{ $res }AI機能が無効になっているため、処理をスキップします。

### astrbot/core/pipeline/process_stage/method/star_request.py

msg-f0144031 = 指定されたハンドラーモジュールパスのプラグインが見つかりません：{ $res }
msg-1e8939dd = plugin ->{ $res }-{ $res_2 }
msg-6be73b5e = { $traceback_text }
msg-d919bd27 = スター{ $res }エラーの処理：{ $e }
msg-ed8dcc22 = { $ret }

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/internal.py

msg-60493581 = サポートされていない tool_schema_mode: %s、skills_like にフォールバックします
msg-9cdb2b6e = LLMリクエストをスキップします：空のメッセージで、プロバイダリクエストがありません
msg-e461e5af = LLMプロバイダーへのリクエスト準備完了
msg-be33dd11 = フォローアップチケットは既に消費済みのため、処理を停止します。umo=%s, seq=%s
msg-abd5ccbc = LLMリクエスト用のセッションロックを取得しました
msg-f9d617d7 = セキュリティ上の理由により、プロバイダーAPIベース%sがブロックされています。他のAIプロバイダーをご利用ください。
msg-3247374d = [内部エージェント] ライブモードを検出しました、TTS処理を有効化します。
msg-dae92399 = [ライブモード] TTSプロバイダーが設定されていません。通常のストリーミングモードを使用します。
msg-1b1af61e = エージェント処理中にエラーが発生しました：{ $e }
msg-ea02b899 = エージェントリクエスト処理中にエラーが発生しました：{ $e }
msg-ee7e792b = LLMの応答が空です。記録は保存されていません。

### astrbot/core/pipeline/process_stage/method/agent_sub_stages/third_party.py

msg-5e551baf = サードパーティエージェントランナーエラー：{ $e }
msg-34f164d4 = { $err_msg }
msg-f9d76893 = エージェントランナープロバイダーIDが入力されていません。設定ページに移動して構成してください。
msg-0f856470 = エージェントランナープロバイダー{ $res }設定が存在しません。設定ページに移動して設定を変更してください。
msg-b3f25c81 = サポートされていないサードパーティエージェントランナータイプ:{ $res }
msg-6c63eb68 = エージェントランナーは最終結果を返しませんでした。

### astrbot/core/pipeline/result_decorate/stage.py

msg-7ec898fd = フック(on_decorating_result) ->{ $res }-{ $res_2 }
msg-5e27dae6 = ストリーミング出力が有効な場合、pre-message-sendイベントフックに依存するプラグインは正常に機能しない可能性があります。
msg-caaaec29 = フック(on_decorating_result) ->{ $res }-{ $res_2 }メッセージの結果をクリア。
msg-78b9c276 = { $res }
msg-add19f94 = { $res }-{ $res_2 }イベントの伝播を終了しました。
msg-813a44bb = ストリーミング出力が有効になりました。結果装飾フェーズをスキップします。
msg-891aa43a = セグメント化された返信の正規表現エラー、デフォルトのセグメント化方式を使用中：{ $res }
msg-82bb9025 = セッション{ $res }テキスト読み上げモデルが設定されていません。
msg-fb1c757a = TTSリクエスト:{ $res }
msg-06341d25 = TTS結果:{ $audio_path }
msg-2057f670 = TTS音声ファイルが不足しているため、メッセージセグメントを音声に変換できませんでした：{ $res }
msg-f26725cf = 登録済み:{ $url }
msg-47716aec = TTSが失敗しました、テキストとして送信します。
msg-ffe054a9 = 画像変換に失敗しました、テキストとして送信します。
msg-06c1aedc = テキストから画像への変換に3秒以上かかりました。遅いと感じる場合は、/t2iを使用してテキストから画像モードをオフにすることができます。

### astrbot/core/pipeline/waking_check/stage.py

msg-df815938 = enabled_plugins_name:{ $enabled_plugins_name }
msg-51182733 = プラグイン{ $res }翻訳対象テキスト：{ $e }
msg-e0dcf0b8 = あなた (ID:{ $res }このコマンドを使用するための十分な権限がありません。/sid でIDを取得し、管理者に追加を依頼してください。
msg-a3c3706f = トリガー{ $res }ユーザー(ID={ $res_2 }権限が不足しています。

### astrbot/core/pipeline/session_status_check/stage.py

msg-f9aba737 = セッション{ $res }閉じました、イベント伝播が終了しました。

### astrbot/core/pipeline/respond/stage.py

msg-59539c6e = セグメント化された応答の間隔時間の解析に失敗しました。{ $e }
msg-4ddee754 = セグメント応答間隔：{ $res }
msg-5e2371a9 = 送信の準備{ $res }翻訳対象のテキスト：{ $res_2 }翻訳するテキスト：{ $res_3 }
msg-df92ac24 = async_stream は空です、送信をスキップします。
msg-858b0e4f = アプリケーションストリーミング出力{ $res }翻訳するテキスト: )
msg-22c7a672 = メッセージが空です。送信フェーズをスキップします。
msg-e6ab7a25 = 空コンテンツチェック例外：{ $e }
msg-b29b99c1 = 実際のメッセージチェーンが空です。送信フェーズをスキップします。header_chain:{ $header_comps }, actual_chain:{ $res }
msg-842df577 = メッセージチェーンの送信に失敗しました: chain ={ $res }, エラー ={ $e }
msg-f35465cf = メッセージチェーンは完全に返信とAtメッセージセグメントで構成されており、送信段階をスキップします。chain:{ $res }
msg-784e8a67 = メッセージチェーンの送信に失敗しました: chain ={ $chain }, エラー ={ $e }

### astrbot/core/pipeline/content_safety_check/stage.py

msg-c733275f = あなたのメッセージまたはAIの応答には不適切な内容が含まれており、ブロックされました。
msg-46c80f28 = コンテンツセキュリティチェックに失敗しました。理由:{ $info }

### astrbot/core/pipeline/content_safety_check/strategies/strategy.py

msg-27a700e0 = Baiduコンテンツモデレーションを使用するには、まずbaidu-aipをpipインストールする必要があります。

### astrbot/core/pipeline/preprocess_stage/stage.py

msg-7b9074fa = { $platform }事前応答絵文字送信失敗:{ $e }
msg-43f1b4ed = パスマッピング:{ $url }->{ $res }
msg-9549187d = セッション{ $res }音声認識モデルが設定されていません。
msg-5bdf8f5c = { $e }
msg-ad90e19e = 再試行:{ $res }翻訳するテキスト：{ $retry }
msg-78b9c276 = { $res }
msg-4f3245bf = 音声からテキストへの変換に失敗しました:{ $e }

### astrbot/core/config/astrbot_config.py

msg-e0a69978 = サポートされていない設定タイプ{ $res }サポートされているタイプには以下が含まれます：{ $res_2 }
msg-b9583fc9 = 検出された構成項目{ $path_ }存在しない、デフォルト値が挿入されました{ $value }
msg-ee26e40e = 検出された構成項目{ $path_ }存在しません、現在の設定から削除されます
msg-2d7497a5 = 設定項目が検出されました{ $path }サブアイテムの順序が一貫していないため、並べ替えられました。
msg-5fdad937 = 設定項目の順序不一致が検出され、順序がリセットされました。
msg-555373b0 = キーが見つかりません: '{ $key }翻訳対象のテキスト：

### astrbot/core/platform/register.py

msg-eecf0aa8 = プラットフォームアダプター{ $adapter_name }すでに登録済みです。アダプターの命名競合が発生する可能性があります。
msg-614a55eb = プラットフォームアダプター{ $adapter_name }登録済み
msg-bb06a88d = プラットフォームアダプター{ $res }削除済み (モジュールから){ $res_2 }翻訳対象テキスト：

### astrbot/core/platform/platform.py

msg-30fc9871 = プラットフォーム{ $res }統合Webhookモードは実装されていません

### astrbot/core/platform/astr_message_event.py

msg-b593f13f = メッセージタイプの変換に失敗しました{ $res }MessageTypeへ。FRIEND_MESSAGEにフォールバックします。
msg-98bb33b7 = クリア{ $res }追加情報:{ $res_2 }
msg-0def44e2 = { $result }
msg-8e7dc862 = { $text }

### astrbot/core/platform/manager.py

msg-464b7ab7 = プラットフォームアダプタの終了に失敗しました: client_id=%s, error=%s
msg-78b9c276 = { $res }
msg-563a0a74 = 初期化{ $platform }プラットフォームアダプターが失敗しました：{ $e }
msg-8432d24e = プラットフォームID %r に不正な文字 ':' または '!' が含まれているため、%r に置き換えられました。
msg-31361418 = プラットフォームID{ $platform_id }空にすることはできません。このプラットフォームアダプターの読み込みをスキップします。
msg-e395bbcc = 読み込み中{ $res }翻訳対象のテキスト：({ $res_2 }) プラットフォームアダプタ ...
msg-b4b29344 = プラットフォームアダプターを読み込み中{ $res }失敗しました。理由:{ $e }依存関係ライブラリがインストールされているか確認してください。ヒント：依存関係ライブラリは管理パネル -> プラットフォームログ -> Pipライブラリのインストールでインストールできます。
msg-18f0e1fe = プラットフォームアダプターを読み込み中{ $res }失敗、理由:{ $e }.
msg-2636a882 = 該当なし{ $res }翻訳するテキスト:{ $res_2 }) プラットフォームアダプター、インストールされているか、または名前が正しく入力されているか確認してください。
msg-c4a38b85 = hook(on_platform_loaded) ->{ $res }-{ $res_2 }
msg-967606fd = タスク{ $res }エラーが発生しました：{ $e }
msg-a2cd77f3 = |{ $line }
msg-1f686eeb = 翻訳対象テキスト： -------
msg-38723ea8 = 終了を試みています{ $platform_id }プラットフォームアダプタ ...
msg-63f684c6 = 完全に削除されていない可能性があります{ $platform_id }プラットフォームアダプター
msg-136a952f = プラットフォーム統計情報の取得に失敗しました:{ $e }

### astrbot/core/platform/sources/dingtalk/dingtalk_adapter.py

msg-c81e728d = 2
msg-d6371313 = dingtalk:{ $res }
msg-a1c8b5b1 = DingTalkのプライベートチャットセッションにはstaff_idのマッピングが不足しており、送信のためにsession_idをuserIdとして使用するようにフォールバックします。
msg-2abb842f = DingTalk会話マッピングの保存に失敗しました:{ $e }
msg-46988861 = DingTalkファイルのダウンロードに失敗しました：{ $res }翻訳対象テキスト：,{ $res_2 }
msg-ba9e1288 = DingTalkストリーム経由でaccess_tokenの取得に失敗しました。{ $e }
msg-835b1ce6 = DingTalkロボットアクセストークンの取得に失敗しました:{ $res }{ $res_2 }
msg-331fcb1f = DingTalkのstaff_idマッピングの読み込みに失敗しました：{ $e }
msg-ba183a34 = DingTalkグループメッセージ送信失敗：access_tokenが空です
msg-b8aaa69b = DingTalkグループメッセージの送信に失敗しました：{ $res }{ $res_2 }
msg-cfb35bf5 = DingTalkプライベートメッセージ送信失敗：access_tokenが空です
msg-7553c219 = DingTalkプライベートチャットメッセージの送信に失敗しました：{ $res }{ $res_2 }
msg-5ab2d58d = 一時ファイルのクリーンアップに失敗しました：{ $file_path }翻訳対象テキスト：{ $e }
msg-c0c40912 = DingTalk音声変換がOGGへの変換に失敗しました、AMRにフォールバックします：{ $e }
msg-21c73eca = DingTalkメディアアップロード失敗：access_tokenが空です
msg-24e3054f = DingTalkメディアアップロードに失敗しました:{ $res }{ $res_2 }
msg-34d0a11d = DingTalk メディアアップロード失敗：{ $data }
msg-3b0d4fb5 = DingTalk音声メッセージ送信に失敗しました:{ $e }
msg-7187f424 = DingTalkビデオ送信失敗：{ $e }
msg-e40cc45f = DingTalkプライベートチャットの返信に失敗しました：送信者スタッフIDが不足しています
msg-be63618a = DingTalkアダプターが無効化されました。
msg-0ab22b13 = DingTalkロボット起動失敗：{ $e }

### astrbot/core/platform/sources/dingtalk/dingtalk_event.py

msg-eaa1f3e4 = DingTalkメッセージ送信失敗：アダプターが不足しています

### astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_server.py

msg-41a3e59d = QQ公式ボットにログイン中...
msg-66040e15 = 公式QQボットアカウントにログインしました:{ $res }
msg-6ed59b60 = qq_official_webhookコールバックを受信しました：{ $msg }
msg-ad355b59 = { $signed }
msg-1f6260e4 = _parser unknown event %s.
msg-cef08b17 = する予定です{ $res }翻訳対象のテキスト：{ $res_2 }ポートはQQ公式ボットWebhookアダプターを開始します。

### astrbot/core/platform/sources/qqofficial_webhook/qo_webhook_adapter.py

msg-3803e307 = [QQOfficialWebhook] セッション: %s にキャッシュされたmsg_idがありません、send_by_sessionをスキップします
msg-08fd28cf = [QQOfficialWebhook] send_by_sessionでサポートされていないメッセージタイプ: %s
msg-6fa95bb3 = QQOfficialWebhookサーバーシャットダウン中に例外が発生しました：{ $exc }
msg-6f83eea0 = QQボット公式APIアダプターが正常にシャットダウンされました

### astrbot/core/platform/sources/discord/discord_platform_event.py

msg-0056366b = [Discord] メッセージチェーンの解析に失敗しました：{ $e }
msg-fa0a9e40 = [Discord] 空のメッセージ送信を試みましたが、無視されました。
msg-5ccebf9a = [Discord] チャンネル{ $res }送信できるメッセージの種類ではありません
msg-1550c1eb = [Discord] メッセージ送信中に不明なエラーが発生しました：{ $e }
msg-7857133d = [Discord] チャンネルの取得に失敗しました{ $res }
msg-050aa8d6 = [Discord] Imageコンポーネントの処理を開始します:{ $i }
msg-57c802ef = [Discord] 画像コンポーネントにファイル属性がありません：{ $i }
msg-f2bea7ac = [Discord] URL画像処理中：{ $file_content }
msg-c3eae1f1 = [Discord] ファイルURIを処理中:{ $file_content }
msg-6201da92 = [Discord] 画像ファイルが存在しません：{ $path }
msg-2a6f0cd4 = [Discord] Base64 URIを処理中
msg-b589c643 = [Discord] 生のBase64として処理を試行
msg-41dd4b8f = [Discord] Raw Base64デコードに失敗しました。ローカルパスとして扱います：{ $file_content }
msg-f59778a1 = [Discord] 画像の処理中に不明な重大なエラーが発生しました:{ $file_info }
msg-85665612 = [Discord] ファイルの取得に失敗しました。指定されたパスは存在しません：{ $file_path_str }
msg-e55956fb = [Discord] ファイルの取得に失敗しました：{ $res }
msg-56cc0d48 = [Discord] ファイルの処理に失敗しました：{ $res }、エラー：{ $e }
msg-c0705d4e = [Discord] サポートされていないメッセージコンポーネントを無視しました：{ $res }
msg-0417d127 = [Discord] メッセージの内容が2000文字を超えています。切り捨てられます。
msg-6277510f = [Discord] リアクションの追加に失敗しました:{ $e }

### astrbot/core/platform/sources/discord/client.py

msg-940888cb = [Discord] クライアントがユーザー情報を正常に読み込めませんでした (self.user が None です)
msg-9a3c1925 = [Discord]が追加されました{ $res }(ID:{ $res_2 }) サインイン
msg-30c1f1c8 = [Discord] クライアントの準備が完了しました。
msg-d8c03bdf = [Discord] on_ready_once_callback の実行に失敗しました：{ $e }
msg-c9601653 = ボットの準備ができていません：self.userがNoneです
msg-4b017a7c = 有効なユーザーなしで受け取ったインタラクション
msg-3067bdce = [Discord] 元のメッセージを受信しました{ $res }翻訳対象のテキスト：{ $res_2 }

### astrbot/core/platform/sources/discord/discord_platform_adapter.py

msg-7ea23347 = [Discord] クライアントが準備できていません（self.client.userがNoneです）、メッセージを送信できません
msg-ff6611ce = [Discord] 無効なチャンネルID形式:{ $channel_id_str }
msg-5e4e5d63 = [Discord] チャンネル情報を取得できません{ $channel_id_str }, メッセージタイプを推測します。
msg-32d4751b = [Discord] 受信メッセージ：{ $message_data }
msg-8296c994 = [Discord] Botトークンが設定されていません。設定ファイルでトークンを正しく設定してください。
msg-170b31df = [Discord] ログインに失敗しました。Botトークンが正しいか確認してください。
msg-6678fbd3 = [Discord] Discordへの接続が閉じられました。
msg-cd8c35d2 = [Discord] アダプターランタイムで予期せぬエラーが発生しました:{ $e }
msg-4df30f1d = [Discord] クライアントが準備できていません（self.client.userがNoneです）、メッセージを処理できません
msg-f7803502 = [Discord] メッセージ以外のタイプのメッセージを受信しました：{ $res }無視されます。
msg-134e70e9 = [Discord] アダプターを終了中... (ステップ1: ポーリングタスクをキャンセル)
msg-5c01a092 = [Discord] polling_task はキャンセルされました。
msg-77f8ca59 = [Discord] polling_task キャンセル例外：{ $e }
msg-528b6618 = [Discord] 登録されたスラッシュコマンドをクリーンアップ中... (ステップ2)
msg-d0b832e6 = [Discord] コマンドのクリーンアップが完了しました。
msg-43383f5e = [Discord] コマンドのクリア中にエラーが発生しました：{ $e }
msg-b960ed33 = [Discord] Discordクライアントを終了中... (ステップ 3)
msg-5e58f8a2 = [Discord] クライアントが異常終了しました：{ $e }
msg-d1271bf1 = [Discord] アダプターが終了しました。
msg-c374da7a = [Discord] スラッシュコマンドの収集と登録を開始しています...
msg-a6d37e4d = [Discord] 同期準備中{ $res }commands:{ $res_2 }
msg-dbcaf095 = [Discord] 登録可能なコマンドが見つかりませんでした。
msg-09209f2f = [Discord] コマンド同期が完了しました。
msg-a95055fd = [Discord] コールバック関数がトリガーされました:{ $cmd_name }
msg-55b13b1e = [Discord] コールバック関数のパラメータ：{ $ctx }
msg-79f72e4e = [Discord] コールバック関数のパラメータ：{ $params }
msg-22add467 = [Discord] スラッシュコマンド '{ $cmd_name }トリガーされました。元のパラメータ:{ $params }'. ビルドされたコマンド文字列: '{ $message_str_for_filter }翻訳対象テキスト:
msg-ccffc74a = [Discord] コマンド '{ $cmd_name }延期失敗しました：{ $e }
msg-13402a28 = [Discord] 準拠していないコマンドをスキップ中：{ $cmd_name }

### astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py

msg-859d480d = リクエストメッセージの処理に失敗しました：{ $e }
msg-6fb672e1 = 通知メッセージの処理に失敗しました:{ $e }
msg-cf4687a3 = グループメッセージの処理に失敗しました：{ $e }
msg-3a9853e3 = プライベートメッセージの処理に失敗しました：{ $e }
msg-ec06dc3d = aiocqhttp (OneBot v11) アダプターが接続されました。
msg-1304a54d = [aiocqhttp] RawMessage{ $event }
msg-93cbb9fa = { $err }
msg-a4487a03 = メッセージへの返信に失敗しました：{ $e }
msg-48bc7bff = ラグランジュ推測
msg-6ab145a1 = ファイルの取得に失敗しました:{ $ret }
msg-457454d7 = ファイルの取得に失敗しました：{ $e }このメッセージセグメントは無視されます。
msg-7a299806 = 返信メッセージデータからEventオブジェクトを構築できません：{ $reply_event_data }
msg-e6633a51 = 参照メッセージの取得に失敗しました：{ $e }.
msg-6e99cb8d = ユーザー情報の取得に失敗しました：{ $e }このメッセージセグメントは無視されます。
msg-cf15fd40 = サポートされていないメッセージセグメントタイプ、無視されました：{ $t }, data={ $res }
msg-45d126ad = メッセージセグメントの解析に失敗しました: type={ $t }, data={ $res }.{ $e }
msg-394a20ae = aiocqhttp: ws_reverse_host または ws_reverse_port が設定されていません。デフォルト値を使用します: http://0.0.0.0:6199
msg-7414707c = aiocqhttpアダプターはシャットダウンされました。

### astrbot/core/platform/sources/aiocqhttp/aiocqhttp_message_event.py

msg-0db8227d = メッセージを送信できません: 有効な数値のsession_idが不足しています{ $session_id }) または イベント({ $event }翻訳対象のテキスト：

### astrbot/core/platform/sources/lark/server.py

msg-2f3bccf1 = encrypt_keyが設定されていないため、イベントを復号できません
msg-e77104e2 = [Lark Webhook] チャレンジ検証リクエストを受信しました：{ $challenge }
msg-34b24fa1 = [Lark Webhook] リクエストボディの解析に失敗しました：{ $e }
msg-ec0fe13e = [Lark Webhook] リクエストボディが空です
msg-f69ebbdb = [Lark Webhook] 署名検証に失敗しました
msg-7ece4036 = [Lark Webhook] 復号化されたイベント：{ $event_data }
msg-f2cb4b46 = [Lark Webhook] イベントの復号に失敗しました：{ $e }
msg-ef9f8906 = [Lark Webhook] 検証トークンが一致しません。
msg-bedb2071 = [Lark Webhook] イベントコールバックの処理に失敗しました:{ $e }

### astrbot/core/platform/sources/lark/lark_event.py

msg-eefbe737 = [Lark] APIクライアントのimモジュールが初期化されていません
msg-a21f93fa = [Lark] メッセージを能動的に送信する際、receive_idとreceive_id_typeは空にできません。
msg-f456e468 = [Lark] Larkメッセージの送信に失敗しました{ $res }):{ $res_2 }
msg-1eb66d14 = [Lark] ファイルが存在しません:{ $path }
msg-1df39b24 = [Lark] APIクライアントIMモジュールが初期化されていません、ファイルをアップロードできません
msg-2ee721dd = [Lark] ファイルのアップロードに失敗しました{ $res }):{ $res_2 }
msg-a04abf78 = [Lark] ファイルは正常にアップロードされましたが、データが返されませんでした（データはNoneです）
msg-959e78a4 = [Lark] ファイルのアップロードが完了しました:{ $file_key }
msg-901a2f60 = [Lark] ファイルを開くまたはアップロードできません:{ $e }
msg-13065327 = [Lark] 画像のパスが空です。アップロードできません。
msg-37245892 = [Lark] 画像ファイルを開くことができません：{ $e }
msg-ad63bf53 = [Lark] APIクライアントimモジュールが初期化されていないため、画像をアップロードできません。
msg-ef90038b = Feishu画像をアップロードできません{ $res }):{ $res_2 }
msg-d2065832 = [Lark] 画像のアップロードは成功しましたが、データは返されませんでした（データがNoneです）
msg-dbb635c2 = { $image_key }
msg-d4810504 = [Lark] ファイルコンポーネントが検出されました。別途送信されます。
msg-45556717 = [Lark] 音声コンポーネントが検出されました。別途送信します。
msg-959070b5 = [Lark] ビデオコンポーネントを検出しました。別途送信されます。
msg-4e2aa152 = Feishuは現在メッセージセグメントをサポートしていません：{ $res }
msg-20d7c64b = [Lark] オーディオファイルのパスの取得に失敗しました：{ $e }
msg-2f6f35e6 = [Lark] オーディオファイルが存在しません：{ $original_audio_path }
msg-528b968d = [Lark] オーディオ形式の変換に失敗しました。直接アップロードを試みます：{ $e }
msg-fbc7efb9 = [Lark] 変換済み音声ファイルを削除しました：{ $converted_audio_path }
msg-09840299 = [Lark] 変換済み音声ファイルの削除に失敗しました:{ $e }
msg-e073ff1c = [Lark] ビデオファイルパスを取得できません:{ $e }
msg-47e52913 = [Lark] 動画ファイルが存在しません：{ $original_video_path }
msg-85ded1eb = [Lark] 動画形式の変換に失敗しました。直接アップロードを試みます：{ $e }
msg-b3bee05d = [Lark] 変換されたビデオファイルが削除されました：{ $converted_video_path }
msg-775153f6 = [Lark] 変換されたビデオファイルの削除に失敗しました：{ $e }
msg-45038ba7 = [Lark] APIクライアントのimモジュールが初期化されていません、絵文字を送信できません
msg-8d475b01 = Lark絵文字リアクションの送信に失敗しました{ $res }):{ $res_2 }

### astrbot/core/platform/sources/lark/lark_adapter.py

msg-06ce76eb = Feishuボット名が設定されていません。@ボットに返信が届かない可能性があります。
msg-eefbe737 = [Lark] APIクライアントのIMモジュールが初期化されていません
msg-236bcaad = [Lark] メッセージリソースのダウンロードに失敗しました type={ $resource_type }、キー={ $file_key }, code={ $res }, msg={ $res_2 }
msg-ef9a61fe = [Lark] メッセージリソースの応答にファイルストリームが含まれていません：{ $file_key }
msg-7b69a8d4 = [Lark] 画像メッセージに message_id がありません
msg-59f1694d = [Lark] リッチテキストビデオメッセージにmessage_idがありません
msg-af8f391d = [Lark] ファイルメッセージにmessage_idがありません
msg-d4080b76 = [Lark] ファイルメッセージにfile_keyがありません
msg-ab21318a = [Lark] オーディオメッセージにmessage_idがありません
msg-9ec2c30a = [Lark] オーディオメッセージにファイルキーがありません
msg-0fa9ed18 = [Lark] ビデオメッセージにmessage_idがありません
msg-ae884c5c = [Lark] ビデオメッセージでファイルキーがありません
msg-dac98a62 = [Lark] 引用メッセージIDの取得に失敗しました{ $parent_message_id }, code={ $res }, msg={ $res_2 }
msg-7ee9f7dc = [Lark] 引用メッセージの応答が空です id={ $parent_message_id }
msg-2b3b2db9 = [Lark] 参照メッセージコンテンツの解析に失敗しました id={ $quoted_message_id }
msg-c5d54255 = [Lark] 空のイベントを受信しました (event.event が None)
msg-82f041c4 = [Lark] イベント内にメッセージ本文がありません（メッセージはNoneです）
msg-206c3506 = [Lark] メッセージ内容が空です
msg-876aa1d2 = [Lark] メッセージコンテンツの解析に失敗しました：{ $res }
msg-514230f3 = [Lark] メッセージ内容はJSONオブジェクトではありません：{ $res }
msg-0898cf8b = [Lark] メッセージ内容の解析中：{ $content_json_b }
msg-6a8bc661 = [Lark] メッセージにmessage_idがありません
msg-26554571 = [Lark] 送信者情報が不完全です
msg-007d863a = [Lark Webhook] 重複イベントをスキップしました：{ $event_id }
msg-6ce17e71 = [Lark Webhook] 未処理のイベントタイプ：{ $event_type }
msg-8689a644 = [Lark Webhook] イベントの処理に失敗しました:{ $e }
msg-20688453 = [Lark] Webhookモードが有効になっていますが、webhook_serverが初期化されていません。
msg-f46171bc = [Lark] Webhookモードが有効ですが、webhook_uuidが設定されていません。
msg-dd90a367 = Larkアダプターは無効化されています。

### astrbot/core/platform/sources/wecom/wecom_event.py

msg-e164c137 = 微信カスタマーサービスメッセージの送信方法が見つかりません。
msg-c114425e = WeChatカスタマーサービスが画像のアップロードに失敗しました：{ $e }
msg-a90bc15d = WeChatカスタマーサービス画像アップロードの返信：{ $response }
msg-38298880 = WeChatカスタマーサービス音声アップロードに失敗しました：{ $e }
msg-3aee0caa = WeChatカスタマーサービスが音声をアップロードし、返信します：{ $response }
msg-15e6381b = 一時的なオーディオファイルの削除に失敗しました:{ $e }
msg-a79ae417 = 微信カスタマーサービスファイルアップロード失敗:{ $e }
msg-374455ef = WeChatカスタマーサービスファイルアップロード結果：{ $response }
msg-a2a133e4 = WeChatカスタマーサービスでの動画アップロードに失敗しました：{ $e }
msg-2732fffd = WeChatカスタマーサービスによる動画アップロードの返信：{ $response }
msg-60815f02 = このメッセージタイプの送信ロジックはまだ実装されていません。{ $res }
msg-9913aa52 = WeChat Work 画像のアップロードに失敗しました:{ $e }
msg-9e90ba91 = WeChat Work 画像アップロード結果：{ $response }
msg-232af016 = WeChat Workでの音声メッセージのアップロードに失敗しました：{ $e }
msg-e5b8829d = WeChat Work音声アップロード戻り値：{ $response }
msg-f68671d7 = WeComでのファイルアップロードに失敗しました:{ $e }
msg-8cdcc397 = WeChat Work ファイルアップロードの返り値：{ $response }
msg-4f3e15f5 = エンタープライズWeChatビデオアップロードに失敗しました:{ $e }
msg-4e9aceea = エンタープライズWeChatビデオアップロードの戻り値:{ $response }

### astrbot/core/platform/sources/wecom/wecom_adapter.py

msg-d4bbf9cb = リクエストの妥当性を確認：{ $res }
msg-f8694a8a = 要求の有効性の検証に成功しました。
msg-8f4cda74 = リクエストの有効性の検証に失敗しました、署名例外が発生しました、設定を確認してください。
msg-46d3feb9 = 復号化に失敗しました、署名例外が発生しました。設定を確認してください。
msg-4d1dfce4 = 解析成功：{ $msg }
msg-a98efa4b = Will be{ $res }翻訳対象テキスト：{ $res_2 }ポート起動 WeChat Work アダプター。
msg-a616d9ce = WeChat Workのカスタマーサービスモードでは、send_by_sessionを介した能動的なメッセージ送信はサポートされていません。
msg-5d01d7b9 = send_by_session が失敗しました: セッションへの送信ができません{ $res }エージェントIDを推測します。
msg-3f05613d = WeChatカスタマーサービスリストを取得しました：{ $acc_list }
msg-8fd19bd9 = WeChatカスタマーサービスの取得に失敗しました。open_kfidが空です。
msg-5900d9b6 = オープンKFIDが見つかりました：{ $open_kfid }
msg-391119b8 = 以下のリンクを開き、WeChatでQRコードをスキャンしてカスタマーサービスWeChatアカウントを取得してください: https://api.cl2wm.cn/api/qrcode/code?text={ $kf_url }
msg-5bdf8f5c = { $e }
msg-93c9125e = オーディオ変換に失敗しました:{ $e }ffmpegがインストールされていない場合は、まずインストールしてください。
msg-b2f7d1dc = 未実装のイベント:{ $res }
msg-61480a61 = abm:{ $abm }
msg-42431e46 = 未実装のWeChatカスタマーサービスメッセージイベント：{ $msg }
msg-fbca491d = WeChat Workアダプターが無効になっています

### astrbot/core/platform/sources/weixin_official_account/weixin_offacc_event.py

msg-fa7f7afc = プレーンテキストを分割{ $res }パッシブリプライのためのチャンク。メッセージは送信されませんでした。
msg-59231e07 = WeChat公式プラットフォームで画像のアップロードに失敗しました:{ $e }
msg-d3968fc5 = WeChat Public Platform 画像アップロードの戻り値：{ $response }
msg-7834b934 = WeChat公式アカウントプラットフォームでの音声アップロードに失敗しました:{ $e }
msg-4901d769 = WeChat Official Account Platform Upload Audio Return:{ $response }
msg-15e6381b = 一時的なオーディオファイルの削除に失敗しました:{ $e }
msg-60815f02 = このメッセージタイプの送信ロジックはまだ実装されていません。{ $res }

### astrbot/core/platform/sources/weixin_official_account/weixin_offacc_adapter.py

msg-d4bbf9cb = リクエストの妥当性を確認:{ $res }
msg-b2edb1b2 = 不明な応答、コールバックアドレスが正しく入力されているか確認してください。
msg-f8694a8a = リクエストの検証が成功しました。
msg-8f4cda74 = リクエストの有効性を検証できませんでした。署名例外が発生しました。設定を確認してください。
msg-46d3feb9 = 復号化に失敗しました、署名が異常です。設定を確認してください。
msg-e23d8bff = 解析に失敗しました。メッセージがNoneです。
msg-4d1dfce4 = パース成功:{ $msg }
msg-193d9d7a = ユーザーメッセージバッファの状態: ユーザー={ $from_user }ステータス={ $state }
msg-57a3c1b2 = トリガーでのwxバッファヒット：ユーザー={ $from_user }
msg-bed995d9 = 再試行ウィンドウでのwxバッファヒット: ユーザー={ $from_user }
msg-3a94b6ab = wx finished message sending in passive window: user={ $from_user }msg_id={ $msg_id }
msg-50c4b253 = wx finished message sending in passive window but not final: user={ $from_user }メッセージID={ $msg_id }
msg-7d8b62e7 = ウィンドウ内で完了したが最終ではないwx; プレースホルダーを返す: user={ $from_user }メッセージID={ $msg_id }
msg-2b9b8aed = wxタスクがパッシブウィンドウで失敗しました
msg-7bdf4941 = wx 受動ウィンドウのタイムアウト: ユーザー={ $from_user }メッセージID={ $msg_id }
msg-98489949 = 考え中にwxトリガー: user={ $from_user }
msg-01d0bbeb = wx new trigger: user={ $from_user }msg_id={ $msg_id }
msg-52bb36cd = wx start task: user={ $from_user }msg_id={ $msg_id }プレビュー={ $preview }
msg-ec9fd2ed = wxバッファが即座にヒットしました：ユーザー={ $from_user }
msg-61c91fb9 = wxが最初のウィンドウで完了していません; プレースホルダーを返します: user={ $from_user }msg_id={ $msg_id }
msg-35604bba = 最初のウィンドウでwxタスクが失敗しました
msg-e56c4a28 = wx最初のウィンドウタイムアウト: ユーザー={ $from_user }msg_id={ $msg_id }
msg-e163be40 = になります{ $res }翻訳対象のテキスト：{ $res_2 }ポート起動 WeChatパブリックプラットフォームアダプター
msg-c1740a04 = 重複したメッセージIDがチェックされました：{ $res }
msg-04718b37 = 将来の結果を取得しました：{ $result }
msg-296e66c1 = コールバックメッセージ処理タイムアウト: message_id={ $res }
msg-eb718c92 = メッセージ変換中に例外が発生しました：{ $e }
msg-93c9125e = 音声変換に失敗しました:{ $e }ffmpegがインストールされていない場合は、先にインストールしてください。
msg-b2f7d1dc = 実装されていないイベント：{ $res }
msg-61480a61 = ABM:{ $abm }
msg-2e7e0187 = ユーザーメッセージバッファリングステータスが見つかりません、メッセージを処理できません: ユーザー={ $res }メッセージID={ $res_2 }
msg-84312903 = WeChatパブリックプラットフォームアダプターは無効化されました

### astrbot/core/platform/sources/misskey/misskey_adapter.py

msg-7bacee77 = [Misskey] 設定が不完全です。起動できません。
msg-99cdf3d3 = [Misskey] 接続済みユーザー:{ $res }(ID:{ $res_2 }翻訳対象テキスト：
msg-5579c974 = [Misskey] ユーザー情報の取得に失敗しました:{ $e }
msg-d9547102 = [Misskey] APIクライアントが初期化されていません
msg-341b0aa0 = [Misskey] WebSocket接続完了（試行回数 #{ $connection_attempts })
msg-c77d157b = [Misskey] チャットチャンネルを購読しました
msg-a0c5edc0 = [Misskey] WebSocket接続に失敗しました（試行回数 #{ $connection_attempts }翻訳対象のテキスト：)
msg-1958faa8 = [Misskey] WebSocket 例外 (試行回数 #{ $connection_attempts }):{ $e }
msg-1b47382d = [Misskey]{ $sleep_time }数秒で再接続します（次回の試行 #{ $res })
msg-a10a224d = [Misskey] 通知イベントを受信しました: type={ $notification_type }, user_id={ $res }
msg-7f0abf4a = [Misskey] 投稿のメンションを処理中:{ $res }翻訳対象のテキスト：...
msg-2da7cdf5 = [Misskey] 通知の処理に失敗しました：{ $e }
msg-6c21d412 = [Misskey] チャットイベントを受信しました: sender_id={ $sender_id }, room_id={ $room_id }, is_self={ $res }
msg-68269731 = [Misskey] グループチャットメッセージを確認中: '{ $raw_text }', ボットユーザー名: '{ $res }翻訳対象テキスト：
msg-585aa62b = [Misskey] グループチャットメッセージを処理中：{ $res }翻訳対象テキスト：
msg-426c7874 = [Misskey] プライベートメッセージ処理中:{ $res }翻訳対象テキスト：...
msg-f5aff493 = [Misskey] チャットメッセージの処理に失敗しました：{ $e }
msg-ea465183 = [Misskey] 未処理のイベントを受信しました: type={ $event_type }, channel={ $res }
msg-8b69eb93 = [Misskey] メッセージ内容が空でファイルコンポーネントもありません、送信をスキップします。
msg-9ba9c4e5 = [Misskey] 一時ファイルがクリーンアップされました:{ $local_path }
msg-91af500e = [Misskey] ファイル数が制限を超えています{ $res }>{ $MAX_FILE_UPLOAD_COUNT }最初のアップロードのみ{ $MAX_FILE_UPLOAD_COUNT }ファイル
msg-9746d7f5 = [Misskey] 同時アップロード中に例外が発生しました。テキストの送信を続行します。
msg-d6dc928c = [Misskey] チャットメッセージは単一ファイルのみサポートしており、残りは無視されます{ $res }ファイル
msg-af584ae8 = [Misskey] 可視性の解析中: visibility={ $visibility }, visible_user_ids={ $visible_user_ids }, session_id={ $session_id }, user_id_for_cache={ $user_id_for_cache }
msg-1a176905 = [Misskey] メッセージの送信に失敗しました:{ $e }

### astrbot/core/platform/sources/misskey/misskey_api.py

msg-fab20f57 = Misskey APIにはaiohttpとwebsocketsが必要です。以下のコマンドでインストールしてください: pip install aiohttp websockets
msg-f2eea8e1 = [Misskey WebSocket] 接続済み
msg-5efd11a2 = [Misskey WebSocket] 再購読{ $channel_type }失敗：{ $e }
msg-b70e2176 = [Misskey WebSocket] 接続失敗:{ $e }
msg-b9f3ee06 = [Misskey WebSocket] 接続が切断されました
msg-7cd98e54 = WebSocketは接続されていません
msg-43566304 = [Misskey WebSocket] メッセージの解析に失敗しました:{ $e }
msg-e617e390 = [Misskey WebSocket] メッセージの処理に失敗しました：{ $e }
msg-c60715cf = [Misskey WebSocket] 接続が予期せず切断されました：{ $e }
msg-da9a2a17 = [Misskey WebSocket] 接続が閉じられました (コード:{ $res }, 理由:{ $res_2 })
msg-bbf6a42e = [Misskey WebSocket] ハンドシェイクに失敗しました:{ $e }
msg-254f0237 = [Misskey WebSocket] メッセージの受信に失敗しました：{ $e }
msg-49f7e90e = { $channel_summary }
msg-630a4832 = [Misskey WebSocket] チャンネルメッセージ:{ $channel_id }イベントタイプ：{ $event_type }
msg-0dc61a4d = [Misskey WebSocket] 使用中ハンドラー：{ $handler_key }
msg-012666fc = [Misskey WebSocket] イベントハンドラを使用中：{ $event_type }
msg-e202168a = [Misskey WebSocket] ハンドラーが見つかりません:{ $handler_key }または{ $event_type }
msg-a397eef1 = [Misskey WebSocket] ダイレクトメッセージハンドラー：{ $message_type }
msg-a5f12225 = [Misskey WebSocket] 未処理のメッセージタイプ:{ $message_type }
msg-ad61d480 = [Misskey API]{ $func_name }再試行{ $max_retries }リトライ後も再び失敗しました:{ $e }
msg-7de2ca49 = [Misskey API]{ $func_name }ページ{ $attempt }セカンダリ再試行が失敗しました:{ $e }翻訳するテキスト：{ $sleep_time }s後に再試行
msg-f5aecf37 = [Misskey API]{ $func_name }リトライ不可能な例外が発生しました：{ $e }
msg-e5852be5 = [Misskey API] クライアントは接続を閉じました
msg-21fc185c = [Misskey API] リクエストパラメータエラー：{ $endpoint }(HTTP{ $status }翻訳対象テキスト：
msg-5b106def = 不正なリクエストです{ $endpoint }
msg-28afff67 = [Misskey API] 認証されていないアクセス:{ $endpoint }(HTTP{ $status })
msg-e12f2d28 = 不正なアクセスです{ $endpoint }
msg-beda662d = [Misskey API] アクセス拒否:{ $endpoint }(HTTP{ $status }翻訳するテキスト：
msg-795ca227 = アクセス禁止{ $endpoint }
msg-5c6ba873 = [Misskey API] リソースが見つかりませんでした：{ $endpoint }(HTTP{ $status })
msg-74f2bac2 = リソースが見つかりません{ $endpoint }
msg-9ceafe4c = [Misskey API] リクエストボディが大きすぎます:{ $endpoint }(HTTP{ $status }翻訳対象テキスト：
msg-3e336b73 = リクエストエンティティが大きすぎます{ $endpoint }
msg-a47067de = [Misskey API] リクエストレート制限:{ $endpoint }(HTTP{ $status }翻訳対象テキスト:
msg-901dc2da = レート制限を超過しました{ $endpoint }
msg-2bea8c2e = [Misskey API] サーバー内部エラー:{ $endpoint }(HTTP{ $status }翻訳対象テキスト：翻訳対象テキスト：
msg-ae8d3725 = 内部サーバーエラー{ $endpoint }
msg-7b028462 = [Misskey API] ゲートウェイエラー：{ $endpoint }(HTTP{ $status })
msg-978414ef = ゲートウェイが不正です{ $endpoint }
msg-50895a69 = [Misskey API] サービス利用不可：{ $endpoint }(HTTP{ $status })
msg-62adff89 = サービス利用不可{ $endpoint }
msg-1cf15497 = [Misskey API] ゲートウェイタイムアウト:{ $endpoint }(HTTP{ $status })
msg-a8a2578d = ゲートウェイのタイムアウト{ $endpoint }
msg-c012110a = [Misskey API] 不明なエラー：{ $endpoint }(HTTP{ $status }翻訳対象テキスト：
msg-dc96bbb8 = HTTP{ $status }対象{ $endpoint }
msg-4c7598b6 = [Misskey API] フェッチ済み{ $res }新しい通知
msg-851a2a54 = [Misskey API] リクエスト成功:{ $endpoint }
msg-5f5609b6 = [Misskey API] 無効なレスポンス形式:{ $e }
msg-c8f7bbeb = 無効なJSONレスポンス
msg-82748b31 = [Misskey API] リクエストが失敗しました:{ $endpoint }- HTTP{ $res }、応答：{ $error_text }
msg-c6de3320 = [Misskey API] リクエストが失敗しました:{ $endpoint }- HTTP{ $res }
msg-affb19a7 = [Misskey API] HTTPリクエストエラー:{ $e }
msg-9f1286b3 = HTTPリクエストが失敗しました:{ $e }
msg-44f91be2 = [Misskey API] 投稿が正常に送信されました:{ $note_id }
msg-fbafd3db = アップロード用のファイルパスが提供されていません
msg-872d8419 = [Misskey API] ローカルファイルが存在しません：{ $file_path }
msg-37186dea = ファイルが見つかりません：{ $file_path }
msg-65ef68e0 = [Misskey API] ローカルファイルのアップロードに成功しました：{ $filename }->{ $file_id }
msg-0951db67 = [Misskey API] ファイルアップロード時のネットワークエラー：{ $e }
msg-e3a322f5 = アップロードに失敗しました:{ $e }
msg-f28772b9 = ハッシュ検索用のMD5ハッシュが提供されていません
msg-25e566ef = [Misskey API] find-by-hash リクエスト: md5={ $md5_hash }
msg-a036a942 = [Misskey API] ハッシュ検索レスポンス：見つかりました{ $res }ファイル
msg-ea3581d5 = [Misskey API] ハッシュによるファイルの検索に失敗しました：{ $e }
msg-1d2a84ff = 名前が指定されていません
msg-f25e28b4 = [Misskey API] 検索リクエスト: name={ $name }, folder_id={ $folder_id }
msg-cd43861a = [Misskey API] 検索応答：見つかりました{ $res }ファイル
msg-05cd55ef = [Misskey API] ファイル名からファイルの検索に失敗しました:{ $e }
msg-c01052a4 = [Misskey API] ファイルリストリクエスト: limit={ $limit }, folder_id={ $folder_id }, type={ $type }
msg-7c81620d = [Misskey API] ファイルリストのレスポンス: 見つかりました{ $res }ファイル
msg-a187a089 = [Misskey API] ファイルの一覧取得に失敗しました:{ $e }
msg-9e776259 = 既存のセッションが利用できません
msg-de18c220 = URLは空にできません
msg-25b15b61 = [Misskey API] SSL証明書のダウンロードに失敗しました:{ $ssl_error }, SSL検証なしで再試行
msg-b6cbeef6 = [Misskey API] ローカルアップロード成功：{ $res }
msg-a4a898e2 = [Misskey API] ローカルアップロード失敗:{ $e }
msg-46b7ea4b = [Misskey API] チャットメッセージが正常に送信されました：{ $message_id }
msg-32f71df4 = [Misskey API] ルームメッセージ送信成功：{ $message_id }
msg-7829f3b3 = [Misskey API] チャットメッセージの応答形式が異常です：{ $res }
msg-d74c86a1 = [Misskey API] メンション通知の応答形式が異常です:{ $res }
msg-65ccb697 = メッセージの内容は空にできません：テキストまたはメディアファイルが必要です。
msg-b6afb123 = [Misskey API] URLメディアアップロード成功：{ $res }
msg-4e62bcdc = [Misskey API] URLメディアのアップロードに失敗しました：{ $url }
msg-71cc9d61 = [Misskey API] URLメディア処理に失敗しました{ $url }翻訳対象テキスト：{ $e }
msg-75890c2b = [Misskey API] ローカルファイルのアップロードに成功しました：{ $res }
msg-024d0ed5 = [Misskey API] ローカルファイルのアップロードに失敗しました：{ $file_path }
msg-f1fcb5e1 = [Misskey API] ローカルファイル処理に失敗しました{ $file_path }翻訳するテキスト：{ $e }
msg-1ee80a6b = サポートされていないメッセージタイプ：{ $message_type }

### astrbot/core/platform/sources/misskey/misskey_event.py

msg-85cb7d49 = [MisskeyEvent] sendメソッドが呼び出されました、メッセージチェーンに含まれる{ $res }コンポーネント
msg-252c2fca = [MisskeyEvent] アダプターメソッドの確認：hasattr(self.client, 'send_by_session') ={ $res }
msg-44d7a060 = [MisskeyEvent] アダプターのsend_by_sessionメソッドを呼び出しています
msg-b6e08872 = [MisskeyEvent] コンテンツが空のため、送信をスキップします
msg-8cfebc9c = [MisskeyEvent] 新しい投稿を作成
msg-ed0d2ed5 = [MisskeyEvent] 送信に失敗しました:{ $e }

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_webhook.py

msg-a5c90267 = メッセージプッシュWebhook URLを空にすることはできません
msg-76bfb25b = メッセージプッシュWebhook URLにキーパラメータがありません
msg-3545eb07 = Webhookリクエストが失敗しました: HTTP{ $res }{ $text }
msg-758dfe0d = Webhookがエラーを返しました：{ $res } { $res_2 }
msg-c056646b = Enterprise WeChatメッセージの送信が成功しました: %s
msg-73d3e179 = ファイルが存在しません：{ $file_path }
msg-774a1821 = メディアのアップロードに失敗しました: HTTP{ $res }翻訳対象テキスト：,{ $text }
msg-6ff016a4 = メディアのアップロードに失敗しました：{ $res } { $res_2 }
msg-0e8252d1 = メディアのアップロードに失敗しました：返されたメディアIDがありません
msg-9dbc2296 = ファイルメッセージに有効なファイルパスがありません、スキップされました：%s
msg-2e567c36 = 一時的な音声ファイル %s のクリーンアップに失敗しました: %s
msg-e99c4df9 = エンタープライズWeChatメッセージプッシュは現在、コンポーネントタイプ%sをサポートしていないため、スキップしました。

### astrbot/core/platform/sources/wecom_ai_bot/WXBizJsonMsgCrypt.py

msg-5bdf8f5c = { $e }
msg-fe69e232 = receiveid が一致しません
msg-00b71c27 = 署名が一致しません
msg-5cfb5c20 = { $signature }

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_event.py

msg-e44e77b0 = 画像データが空です、スキップします。
msg-30d116ed = 画像メッセージの処理に失敗しました: %s
msg-31b11295 = [WecomAI] サポートされていないメッセージコンポーネントタイプ：{ $res }、スキップ

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_adapter.py

msg-277cdd37 = エンタープライズWeChatメッセージプッシュWebhook設定が無効です: %s
msg-2102fede = キュー メッセージの処理中に例外が発生しました：{ $e }
msg-d4ea688d = メッセージタイプが不明です。無視されました:{ $message_data }
msg-15ba426f = メッセージ処理中に例外が発生しました：%s
msg-740911ab = ストリームは既に終了しました、終了メッセージを返しています:{ $stream_id }
msg-9fdbafe9 = ストリームIDのバックキューが見つかりません:{ $stream_id }
msg-7a52ca2b = ストリームIDのバックキューに新しいメッセージがありません：{ $stream_id }
msg-9ffb59fb = 集約されたコンテンツ:{ $latest_plain_content }画像：{ $res }完了{ $finish }
msg-de9ff585 = ストリームメッセージが正常に送信されました、stream_id:{ $stream_id }
msg-558310b9 = メッセージ暗号化に失敗しました
msg-251652f9 = ウェルカムメッセージ処理中に例外が発生しました: %s
msg-480c5dac = [WecomAI] メッセージがキューに追加されました:{ $stream_id }
msg-f595dd6e = 暗号化された画像の処理に失敗しました:{ $result }
msg-e8beeb3d = WecomAIアダプタ：{ $res }
msg-6f8ad811 = アクティブメッセージ送信失敗：エンタープライズWeChatメッセージプッシュWebhook URLが設定されていません。設定に移動して追加してください。session_id=%s
msg-84439b09 = エンタープライズWeChatメッセージのプッシュに失敗しました（セッション=%s）: %s
msg-f70f5008 = WeChat Workスマートロボットアダプターを起動し、%s:%dで待機中
msg-87616945 = エンタープライズWeChatインテリジェントロボットアダプターがシャットダウンしています...

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_api.py

msg-86f6ae9f = メッセージの復号に失敗しました。エラーコード:{ $ret }
msg-45ad825c = 復号に成功しました。メッセージの内容:{ $message_data }
msg-84c476a7 = JSONの解析に失敗しました:{ $e }元のメッセージ:{ $decrypted_msg }
msg-c0d8c5f9 = 復号化されたメッセージは空です
msg-a08bcfc7 = 復号化プロセスで例外が発生しました:{ $e }
msg-4dfaa613 = メッセージの暗号化に失敗しました。エラーコード：{ $ret }
msg-6e566b12 = メッセージは正常に暗号化されました
msg-39bf8dba = 暗号化プロセス例外が発生しました:{ $e }
msg-fa5be7c5 = URL検証が失敗しました。エラーコード：{ $ret }
msg-813a4e4e = URL検証成功
msg-65ce0d23 = URL検証中に例外が発生しました:{ $e }
msg-b1aa892f = 暗号化されたイメージのダウンロードを開始:{ $image_url }
msg-10f72727 = { $error_msg }
msg-70123a82 = 画像が正常にダウンロードされました、サイズ：{ $res }バイト
msg-85d2dba1 = AESキーは空にできません
msg-67c4fcea = 無効なAESキー長：32バイトである必要があります
msg-bde4bb57 = 無効なパディング長（32バイトを超える）
msg-63c22912 = 画像復号化成功、復号化サイズ:{ $res }バイト
msg-6ea489f0 = テキストメッセージの解析に失敗しました
msg-eb12d147 = 画像メッセージの解析に失敗しました
msg-ab1157ff = ストリームメッセージの解析に失敗しました
msg-e7e945d1 = 混合メッセージの解析に失敗しました
msg-06ada9dd = イベントメッセージの解析に失敗しました

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_server.py

msg-adaee66c = URL検証パラメータが不足しています
msg-742e0b43 = 企業WeChatスマートボットWebHook URLの検証リクエストを受信しました。
msg-f86c030c = メッセージコールバックパラメータが不足しています
msg-cce4e44c = メッセージ受信コールバック、msg_signature={ $msg_signature }, timestamp={ $timestamp }、nonce={ $nonce }
msg-7f018a3c = メッセージ復号化に失敗しました。エラーコード：%d
msg-9d42e548 = メッセージハンドラ実行例外: %s
msg-15ba426f = メッセージ処理中に例外が発生しました：%s
msg-5bf7dffa = エンタープライズWeChatインテリジェントロボットサーバーを起動中、%s:%dでリッスンしています
msg-445921d5 = サーバーの動作が異常です: %s
msg-3269840c = エンタープライズWeChatインテリジェントロボットサーバーがシャットダウンしています...

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_queue_mgr.py

msg-8be03d44 = [WecomAI] 入力キューを作成中：{ $session_id }
msg-9804296a = [WecomAI] 出力キューを作成中：{ $session_id }
msg-bdf0fb78 = [WecomAI] 出力キューを削除:{ $session_id }
msg-40f6bb7b = [WecomAI] 保留中の応答を削除：{ $session_id }
msg-fbb807cd = [WecomAI] ストリームマーキングが終了しました：{ $session_id }
msg-9d7f5627 = [WecomAI] 入力キューから削除:{ $session_id }
msg-7637ed00 = [WecomAI] 保留中の応答を設定：{ $session_id }
msg-5329c49b = [WecomAI] 期限切れの応答とキューをクリーンアップ中：{ $session_id }
msg-09f098ea = [WecomAI] 会話のリスナーを開始中:{ $session_id }
msg-c55856d6 = セッションの処理中{ $session_id }メッセージ送信中にエラーが発生しました：{ $e }

### astrbot/core/platform/sources/wecom_ai_bot/wecomai_utils.py

msg-14d01778 = JSON解析に失敗しました:{ $e }原文文字列:{ $json_str }
msg-df346cf5 = 暗号化されたイメージのダウンロードを開始中: %s
msg-cb266fb3 = 画像のダウンロードが成功しました。サイズ: %d バイト
msg-10f72727 = { $error_msg }
msg-1d91d2bb = AESキーは空にできません
msg-bb32bedd = 無効なAESキー長：32バイトである必要があります
msg-bde4bb57 = 無効なパディング長（32バイトを超えています）
msg-3cf2120e = 画像の復号に成功、復号サイズ：%d バイト
msg-3f8ca8aa = 画像はbase64エンコードに変換されました、エンコードされた長さ: %d

### astrbot/core/platform/sources/line/line_api.py

msg-06e3f874 = [LINE] %s メッセージ送信失敗: ステータス=%s ボディ=%s
msg-1478c917 = [LINE] %s メッセージリクエストに失敗しました: %s
msg-39941f06 = [LINE] コンテンツ取得のリトライに失敗しました：message_id=%s status=%s body=%s
msg-1fe70511 = [LINE] コンテンツの取得に失敗しました：message_id=%s status=%s body=%s

### astrbot/core/platform/sources/line/line_event.py

msg-4068a191 = [LINE] 画像URLの解決に失敗しました：%s
msg-2233b256 = [LINE] レコードURLの解決に失敗しました: %s
msg-a7455817 = [LINE] レコード期間の解決に失敗しました: %s
msg-9d0fee66 = [LINE] 動画URLの解決に失敗しました: %s
msg-3b8ea946 = [LINE] 動画カバーの解決に失敗しました: %s
msg-aea2081a = [LINE] 動画プレビューの生成に失敗しました：%s
msg-af426b7e = [LINE] ファイルのURLの解決に失敗しました: %s
msg-fe44c12d = [LINE] ファイルサイズの解決に失敗しました: %s
msg-d6443173 = [LINE] メッセージ数が5を超えました。追加のセグメントは破棄されます。

### astrbot/core/platform/sources/line/line_adapter.py

msg-68539775 = LINEアダプタにはchannel_access_tokenとchannel_secretが必要です。
msg-30c67081 = [LINE] webhook_uuidが空です。統合Webhookがメッセージを受信できない可能性があります。
msg-64e92929 = [LINE] 無効なウェブフック署名
msg-71bc0b77 = [LINE] 無効なウェブフックボディ: %s
msg-8c7d9bab = [LINE] 重複イベントをスキップしました: %s

### astrbot/core/platform/sources/telegram/tg_event.py

msg-7757f090 = [Telegram] チャットアクションの送信に失敗しました：{ $e }
msg-80b075a3 = ユーザーのプライバシー設定により音声メッセージの受信が制限されているため、音声ファイルとして送信します。音声メッセージを有効にするには、Telegram設定 → プライバシーとセキュリティ → 音声メッセージ → 「全員」に設定してください。
msg-20665ad1 = MarkdownV2送信に失敗しました:{ $e }. プレーンテキストを使用します。
msg-323cb67c = [Telegram] リアクションの追加に失敗しました：{ $e }
msg-abe7fc3d = メッセージ編集に失敗しました(streaming-break):{ $e }
msg-f7d40103 = サポートされていないメッセージタイプ:{ $res }
msg-d4b50a96 = メッセージ編集失敗（ストリーミング）：{ $e }
msg-2701a78f = メッセージの送信に失敗しました（ストリーミング）：{ $e }
msg-2a8ecebd = Markdown変換に失敗しました。プレーンテキストを使用します：{ $e }

### astrbot/core/platform/sources/telegram/tg_adapter.py

msg-cb53f79a = Telegram ベースURL：{ $res }
msg-e6b6040f = Telegram Updaterが初期化されていません。ポーリングを開始できません。
msg-2c4b186e = Telegram Platform Adapterが実行中です。
msg-908d0414 = Telegramへのコマンド登録中にエラーが発生しました：{ $e }
msg-d2dfe45e = コマンド名 '{ $cmd_name }重複登録、最初の登録定義を使用します：{ $res }翻訳対象テキスト：
msg-63bdfab8 = 有効なチャットなしで開始コマンドを受信しました、/start返信をスキップします。
msg-03a27b01 = Telegramメッセージ：{ $res }
msg-e47b4bb4 = メッセージなしで更新を受信しました。
msg-c97401c6 = [Telegram] from_userのないメッセージを受信しました。
msg-f5c839ee = TelegramドキュメントファイルのパスがNoneです、ファイルを保存できません。{ $file_name }.
msg-dca991a9 = TelegramのビデオファイルのパスがNoneです、ファイルを保存できません。{ $file_name }.
msg-56fb2950 = メディアグループキャッシュを作成:{ $media_group_id }
msg-0de2d4b5 = メディアグループにメッセージを追加{ $media_group_id }現在は{ $res }項目。
msg-9e5069e9 = メディアグループ{ $media_group_id }最大待機時間に達しました{ $elapsed }s >={ $res }s)、処理を即時実行します。
msg-9156b9d6 = スケジュール済みメディアグループ{ $media_group_id }処理待ち{ $delay }秒（すでに待機済み{ $elapsed }s)
msg-2849c882 = メディアグループ{ $media_group_id }キャッシュに見つかりません
msg-c75b2163 = メディアグループ{ $media_group_id }空です
msg-0a3626c1 = メディアグループの処理中{ $media_group_id }、合計{ $res }アイテム
msg-2842e389 = メディアグループの最初のメッセージを変換できませんでした{ $media_group_id }
msg-32fbf7c1 = 追加しました{ $res }メディアグループへのコンポーネント{ $media_group_id }
msg-23bae28a = Telegramアダプターが閉じられました。
msg-e46e7740 = Telegramアダプタを閉じる際にエラーが発生しました：{ $e }

### astrbot/core/platform/sources/slack/client.py

msg-1d6b68b9 = Slackリクエスト署名検証が失敗しました
msg-53ef18c3 = Slackイベントを受信しました：{ $event_data }
msg-58488af6 = Slackイベント処理エラー：{ $e }
msg-477be979 = Slack Webhook サーバーを起動中、待機中{ $res }翻訳対象テキスト：{ $res_2 }{ $res_3 }...
msg-639fee6c = Slack Webhookサーバーが停止しました
msg-a238d798 = ソケットクライアントは初期化されていません
msg-4e6de580 = Socket Modeイベントの処理中にエラーが発生しました：{ $e }
msg-5bb71de9 = Slack Socket Mode クライアントを起動中...
msg-f79ed37f = Slack Socket Modeクライアントが停止しました

### astrbot/core/platform/sources/slack/slack_adapter.py

msg-c34657ff = Slack bot_tokenは必須です。
msg-64f8a45d = Socket Modeではapp_tokenが必要です
msg-a2aba1a7 = Webhook Modeにはsigning_secretが必要です
msg-40e00bd4 = Slackメッセージの送信に失敗しました:{ $e }
msg-56c1d0a3 = [slack] RawMessage{ $event }
msg-855510b4 = Slackファイルのダウンロードに失敗しました:{ $res } { $res_2 }
msg-04ab2fae = ファイルのダウンロードに失敗しました：{ $res }
msg-79ed7e65 = Slack認証テストOK。ボットID:{ $res }
msg-ec27746a = Slack Adapter (Socket Mode) を起動しています...
msg-34222d3a = Slack Adapter (Webhook Mode) 起動中、待機中{ $res }翻訳するテキスト：{ $res_2 }{ $res_3 }...
msg-6d8110d2 = サポートされていない接続モード：{ $res }、'socket'または'webhook'を使用してください
msg-d71e7f36 = Slackアダプターがクローズされました。

### astrbot/core/platform/sources/slack/slack_event.py

msg-b233107c = Slackファイルアップロード失敗:{ $res }
msg-596945d1 = Slackファイルアップロード応答：{ $response }

### astrbot/core/platform/sources/satori/satori_adapter.py

msg-ab7db6d9 = Satori WebSocket接続が閉じられました：{ $e }
msg-4ef42cd1 = Satori WebSocket接続に失敗しました:{ $e }
msg-b50d159b = 最大再試行回数に達しました（{ $max_retries })，リトライを停止
msg-89de477c = SatoriアダプターがWebSocketに接続中：{ $res }
msg-cfa5b059 = Satori Adapter HTTP API アドレス:{ $res }
msg-d534864b = 無効なWebSocket URL：{ $res }
msg-a110f9f7 = WebSocket URLはws://またはwss://で始まる必要があります{ $res }
msg-bf43ccb6 = Satoriはメッセージの処理中にエラーが発生しました：{ $e }
msg-89081a1a = Satori WebSocket接続例外:{ $e }
msg-5c04bfcd = Satori WebSocketが異常終了しました:{ $e }
msg-b67bcee0 = WebSocket接続が確立されていません
msg-89ea8b76 = WebSocket接続が閉じられました
msg-4c8a40e3 = IDENTIFYシグナル送信中に接続が切断されました:{ $e }
msg-05a6b99d = IDENTIFY信号の送信に失敗しました：{ $e }
msg-c9b1b774 = Satori WebSocketハートビートの送信に失敗しました:{ $e }
msg-61edb4f3 = ハートビートタスク例外:{ $e }
msg-7db44899 = さとり接続成功 - ボット{ $res }platform={ $platform }, user_id={ $user_id }, user_name={ $user_name }
msg-01564612 = WebSocketメッセージの解析に失敗しました:{ $e }, メッセージ内容:{ $message }
msg-3a1657ea = WebSocketメッセージ処理中の例外：{ $e }
msg-dc6b459c = 処理イベントに失敗しました：{ $e }
msg-6524f582 = <quote>タグの解析中にエラーが発生しました：{ $e }エラー内容：{ $content }
msg-3be535c3 = Satoriメッセージの変換に失敗しました:{ $e }
msg-be17caf1 = XML解析に失敗しました、正規表現抽出を使用します：{ $e }
msg-f6f41d74 = <quote>タグの抽出中にエラーが発生しました:{ $e }
msg-ca6dca7f = 参照メッセージの変換に失敗しました:{ $e }
msg-cd3b067e = Satori要素の解析中に解析エラーが発生しました：{ $e }, エラー内容:{ $content }
msg-03071274 = Satori要素の解析中に不明なエラーが発生しました：{ $e }
msg-775cd5c0 = HTTPセッションが初期化されていません
msg-e354c8d1 = Satori HTTPリクエスト例外:{ $e }

### astrbot/core/platform/sources/satori/satori_event.py

msg-c063ab8a = Satori メッセージ送信例外：{ $e }
msg-9bc42a8d = Satoriメッセージ送信に失敗しました
msg-dbf77ca2 = 画像をbase64に変換できませんでした:{ $e }
msg-8b6100fb = サトリストリーミングメッセージ送信例外：{ $e }
msg-3c16c45c = 音声をbase64に変換できませんでした：{ $e }
msg-66994127 = ビデオファイルの変換に失敗しました：{ $e }
msg-30943570 = メッセージコンポーネントの変換に失敗しました:{ $e }
msg-3e8181fc = 転送ノードの変換に失敗しました：{ $e }
msg-d626f831 = マージされたメッセージの変換および転送に失敗しました：{ $e }

### astrbot/core/platform/sources/webchat/webchat_queue_mgr.py

msg-4af4f885 = 会話のリスナーを開始しました：{ $conversation_id }
msg-10237240 = 会話からのメッセージ処理中にエラーが発生しました{ $conversation_id }翻訳するテキスト:{ $e }

### astrbot/core/platform/sources/webchat/webchat_adapter.py

msg-9406158c = WebChatAdapter:{ $res }

### astrbot/core/platform/sources/webchat/webchat_event.py

msg-6b37adcd = ウェブチャット無視：{ $res }

### astrbot/core/platform/sources/qqofficial/qqofficial_platform_adapter.py

msg-8af45ba1 = QQ Bot Official API Adapterはsend_by_sessionをサポートしていません
msg-8ebd1249 = 不明なメッセージタイプ:{ $message_type }
msg-c165744d = QQ公式ボットインターフェースアダプターは正常にシャットダウンされました。

### astrbot/core/platform/sources/qqofficial/qqofficial_message_event.py

msg-28a74d9d = [QQOfficial] botpy FormData パッチをスキップします。
msg-c0b123f6 = ストリーミングメッセージ送信エラー：{ $e }
msg-05d6bba5 = [QQOfficial] サポートされていないメッセージソースタイプ：{ $res }
msg-e5339577 = [QQOfficial] GroupMessageにはgroup_openidがありません
msg-71275806 = C2Cに送信されたメッセージ：{ $ret }
msg-040e7942 = [QQOfficial] markdown送信が拒否されました。コンテンツモードにフォールバックして再試行します。
msg-9000f8f7 = 無効なアップロードパラメータ
msg-d72cffe7 = 画像のアップロードに失敗しました。レスポンスが辞書型ではありません。{ $result }
msg-5944a27c = ファイルアップロード応答フォーマットエラー：{ $result }
msg-1e513ee5 = アップロードリクエストエラー：{ $e }
msg-f1f1733c = C2Cメッセージの投稿に失敗しました。応答は辞書ではありません：{ $result }
msg-9b8f9f70 = サポートされていない画像ファイル形式
msg-24eb302a = 音声フォーマット変換エラー：音声の再生時間が0より大きくありません。
msg-b49e55f9 = 音声処理エラー：{ $e }
msg-6e716579 = qq_official を無視{ $res }

### astrbot/core/provider/provider.py

msg-e6f0c96f = プロバイダタイプ{ $provider_type_name }登録されていません
msg-c7953e3f = バッチ{ $batch_idx }処理に失敗しました。再試行しました{ $max_retries }第二：{ $e }
msg-10f72727 = { $error_msg }
msg-7ff71721 = リランクプロバイダーのテストが失敗しました、結果が返されませんでした

### astrbot/core/provider/register.py

msg-19ddffc0 = 大規模モデルプロバイダーアダプターを検出しました{ $provider_type_name }既に登録済みです。大規模モデルプロバイダーのアダプタータイプにおける命名の競合が原因である可能性があります。
msg-7e134b0d = サービスプロバイダ{ $provider_type_name }登録済み

### astrbot/core/provider/func_tool_manager.py

msg-0c42a4d9 = 関数呼び出しツールを追加：{ $name }
msg-e8fdbb8c = MCPサービス設定ファイルが見つかりませんでした。デフォルトの設定ファイルが作成されました。{ $mcp_json_file }
msg-cf8aed84 = MCPクライアントを受信しました{ $name }終了シグナル
msg-3d7bcc64 = MCPクライアントを初期化中{ $name }失敗しました
msg-1b190842 = MCPサーバー{ $name }リストツールの応答：{ $tools_res }
msg-6dc4f652 = MCPサービスに接続されました{ $name }, ツール：{ $tool_names }
msg-a44aa4f2 = MCPクライアントリソースをクリア{ $name }翻訳対象テキスト：{ $e }.
msg-e9c96c53 = MCPサービスは無効化されました。{ $name }
msg-10f72727 = { $error_msg }
msg-85f156e0 = 設定を使用したMCPサーバー接続のテスト:{ $config }
msg-93c54ce0 = 接続テスト後のMCPクライアントのクリーンアップを実行中。
msg-368450ee = この関数呼び出しツールが属するプラグイン{ $res }無効です。まず管理パネルでこのツールを有効にしてください。
msg-4ffa2135 = MCP設定の読み込みに失敗しました：{ $e }
msg-a486ac39 = MCP設定の保存に失敗しました:{ $e }
msg-58dfdfe7 = ModelScopeから同期されました{ $synced_count }MCPサーバー
msg-75f1222f = 利用可能なModelScope MCPサーバーが見つかりませんでした
msg-c9f6cb1d = ModelScope APIリクエストが失敗しました：HTTP{ $res }
msg-c8ebb4f7 = ネットワーク接続エラー：{ $e }
msg-0ac6970f = ModelScope MCPサーバーの同期中にエラーが発生しました:{ $e }

### astrbot/core/provider/entities.py

msg-7fc6f623 = 画像{ $image_url }取得された結果は空であり、無視されます。

### astrbot/core/provider/manager.py

msg-9e1a7f1f = プロバイダー{ $provider_id }存在しません、設定できません。
msg-5fda2049 = 不明なプロバイダタイプ:{ $provider_type }
msg-a5cb19c6 = IDが見つかりません{ $provider_id }プロバイダーは、プロバイダー（モデル）IDを変更したことが原因である可能性があります。
msg-78b9c276 = { $res }
msg-5bdf8f5c = { $e }
msg-b734a1f4 = プロバイダー{ $provider_id }設定項目キー{ $idx }] 環境変数を使用{ $env_key }設定されていません。
msg-664b3329 = プロバイダー{ $res }無効になっています、スキップ中
msg-f43f8022 = 読み込み中{ $res }翻訳するテキスト：{ $res_2 }サービスプロバイダー ...
msg-edd4aefe = 読み込み中{ $res }翻訳対象テキスト：{ $res_2 }) プロバイダーアダプターが失敗しました:{ $e }インストールされていない依存関係が原因かもしれません。
msg-78e514a1 = 読み込み中{ $res }翻訳対象テキスト：({ $res_2 }) プロバイダーアダプターが失敗しました:{ $e }不明な理由
msg-4636f83c = 適用なし{ $res }翻訳するテキスト：{ $res_2 }) プロバイダーアダプター、インストール済みか、または名前が正しく入力されているか確認してください。スキップしました。
msg-e9c6c4a2 = 見つかりません{ $res }クラス
msg-f705cf50 = プロバイダークラス{ $cls_type }STTProviderのサブクラスではありません
msg-d20620aa = 選択済み{ $res }翻訳対象のテキスト：{ $res_2 }) を現在の音声テキスト変換プロバイダーアダプターとして設定します。
msg-afbe5661 = プロバイダークラス{ $cls_type }TTSProvider のサブクラスではありません
msg-74d437ed = 選択済み{ $res }翻訳するテキスト：{ $res_2 }) を現在のテキスト読み上げプロバイダアダプタとして設定します。
msg-08cd85c9 = プロバイダークラス{ $cls_type }Providerのサブクラスではありません
msg-16a2b8e0 = 選択済み{ $res }翻訳対象テキスト：({ $res_2 }) を現在のプロバイダーアダプターとして設定します。
msg-0e1707e7 = プロバイダークラス{ $cls_type }はEmbeddingProviderのサブクラスではありません
msg-821d06e0 = プロバイダークラス{ $cls_type }RerankProviderのサブクラスではありません。
msg-14c35664 = 不明なプロバイダタイプ:{ $res }
msg-186fd5c6 = インスタンス化{ $res }翻訳対象テキスト：{ $res_2 }) プロバイダアダプタが失敗しました:{ $e }
msg-ede02a99 = ユーザーの設定内のプロバイダ：{ $config_ids }
msg-95dc4227 = 自動選択{ $res }現在のプロバイダーアダプターとして。
msg-a6187bac = 自動選択{ $res }現在の音声テキスト変換プロバイダーアダプターとして。
msg-bf28f7e2 = 自動選択{ $res }現在のテキスト読み上げプロバイダーアダプターとして。
msg-dba10c27 = 終了{ $provider_id }プロバイダーアダプター ({ $res }{ $res_2 }翻訳対象テキスト：{ $res_3 }) ...
msg-9d9d9765 = { $provider_id }プロバイダーアダプターが終了しました（{ $res }{ $res_2 }翻訳対象のテキスト：{ $res_3 })
msg-925bb70a = プロバイダ{ $target_prov_ids }設定から削除されました。
msg-a1657092 = 新しいプロバイダ設定には「id」フィールドが必要です
msg-1486c653 = プロバイダーID{ $npid }既に存在します
msg-f9fc1545 = プロバイダーID{ $origin_provider_id }見つかりません
msg-4e2c657c = MCPサーバーの無効化中にエラーが発生しました

### astrbot/core/provider/sources/gemini_embedding_source.py

msg-173efb0e = [Gemini Embedding] プロキシを使用中：{ $proxy }
msg-58a99789 = Gemini Embedding APIリクエストが失敗しました:{ $res }
msg-5c4ea38e = Gemini Embedding API のバッチリクエストが失敗しました:{ $res }

### astrbot/core/provider/sources/bailian_rerank_source.py

msg-dc1a9e6e = Alibaba Cloud Bailian APIキーは空にできません。
msg-f7079f37 = AstrBot Hundred Refinements Rerankの初期化が完了しました。モデル:{ $res }
msg-5b6d35ce = Bailian APIエラー:{ $res }翻訳対象テキスト：{ $res_2 }
msg-d600c5e2 = Bailian Rerankは空の結果を返します：{ $data }
msg-d3312319 = 結果{ $idx }関連性スコアがありません、デフォルト値0.0を使用します
msg-2855fb44 = 分析結果{ $idx }エラーが発生しました：{ $e }, result={ $result }
msg-392f26e8 = Bailian Rerank Token Consumption:{ $tokens }
msg-595e0cf9 = 百連リランククライアントセッションが閉じられました。空の結果を返します。
msg-d0388210 = ドキュメントリストが空です、空の結果を返します。
msg-44d6cc76 = クエリテキストが空です。空の結果を返します。
msg-bd8b942a = ドキュメント数{ $res }) が制限（500）を超えています。最初の500件のドキュメントを切り捨てます
msg-0dc3bca4 = Bailian Rerank リクエスト: query='{ $res }..., ドキュメント数={ $res_2 }
msg-4a9f4ee3 = Bailian Rerankが正常に返されました{ $res }結果
msg-fa301307 = Bailian Rerankネットワークリクエストが失敗しました：{ $e }
msg-10f72727 = { $error_msg }
msg-9879e226 = Bailian Rerank処理に失敗しました:{ $e }
msg-4f15074c = Baichuan Rerank クライアントセッションを閉じる
msg-d01b1b0f = Baichuan Rerankクライアントを閉じる際のエラー:{ $e }

### astrbot/core/provider/sources/edge_tts_source.py

msg-f4ab0713 = pyffmpeg変換失敗：{ $e }、変換には ffmpeg コマンドラインをお試しください
msg-ddc3594a = [EdgeTTS] FFmpeg標準出力：{ $res }
msg-1b8c0a83 = FFmpegエラー出力：{ $res }
msg-1e980a68 = [EdgeTTS] 戻り値（成功時は0）:{ $res }
msg-c39d210c = 生成されたWAVファイルが存在しないか、空です。
msg-57f60837 = FFmpeg変換に失敗しました：{ $res }
msg-ca94a42a = FFmpeg変換に失敗しました：{ $e }
msg-be660d63 = オーディオ生成に失敗しました:{ $e }

### astrbot/core/provider/sources/whisper_api_source.py

msg-28cbbf07 = ファイルが存在しません:{ $audio_url }
msg-b335b8db = Tencent_silk_to_wavを使用してsilkファイルをwavに変換中...
msg-68b5660f = convert_to_pcm_wavを使用してamrファイルをwavに変換中...
msg-cad3735e = 一時ファイルの削除に失敗しました{ $audio_url }翻訳対象テキスト：{ $e }

### astrbot/core/provider/sources/gemini_source.py

msg-1474947f = [Gemini] プロキシの使用中：{ $proxy }
msg-e2a81024 = キー異常が検出されました{ $res })、APIキーを変更して再試行しています... 現在のキー:{ $res_2 }翻訳対象のテキスト：...
msg-0d388dae = 検出されたキーの異常{ $res })、これ以上のキーは利用できません。現在のキー:{ $res_2 }翻訳対象テキスト：...
msg-1465290c = Geminiのレート制限に達しました。後でもう一度お試しください...
msg-7e9c01ca = ストリーミング出力は画像モダリティをサポートしておらず、自動的にテキストモダリティにダウングレードされました。
msg-89bac423 = コード実行ツールと検索ツールは相互排他的であり、検索ツールは無視されました。
msg-301cf76e = コード実行ツールとURLコンテキストツールは相互排他的です。URLコンテキストツールは無視されました。
msg-356e7b28 = 現在のSDKバージョンはURLコンテキストツールをサポートしていません。この設定は無視されました。google-genaiパッケージをアップグレードしてください。
msg-7d4e7d48 = gemini-2.0-liteはコード実行、検索ツール、URLコンテキストをサポートしていません。これらの設定は無視されます。
msg-cc5c666f = ネイティブツールが有効化されているため、機能ツールは無視されます。
msg-aa7c77a5 = 無効な思考レベル:{ $thinking_level }, HIGHを使用して
msg-59e1e769 = テキストコンテンツが空です、プレースホルダースペースが追加されました
msg-34c5c910 = Google Gemini思考署名のデコードに失敗しました：{ $e }
msg-a2357584 = アシスタント役割のメッセージ内容が空です。スペースのプレースホルダーが追加されました。
msg-f627f75d = Geminiネイティブツールが有効で、コンテキストに関数呼び出しが存在することが検出されました。コンテキストをリセットするには /reset を使用することをお勧めします。
msg-cb743183 = 受信したcandidate.contentが空です：{ $candidate }
msg-34b367fc = APIから返されたcandidate.contentが空です。
msg-73541852 = Geminiプラットフォームでモデル生成コンテンツの安全性チェックに失敗しました。
msg-ae3cdcea = モデル生成コンテンツはGeminiプラットフォームポリシーに違反します
msg-5d8f1711 = 受信したcandidate.content.partsが空です：{ $candidate }
msg-57847bd5 = APIによって返されたcandidate.content.partsが空です。
msg-a56c85e4 = genai 結果:{ $result }
msg-42fc0767 = リクエストが失敗しました。返された候補が空です：{ $result }
msg-faf3a0dd = リクエストが失敗しました。返された候補が空です。
msg-cd690916 = 温度パラメータは最大値2を超えましたが、復唱は依然として発生しました。
msg-632e23d7 = リサイテーションが発生し、温度を上昇させました{ $temperature }再試行...
msg-41ff84bc = { $model }システムプロンプトはサポートされていません、自動的に削除されました（ペルソナ設定に影響します）。
msg-ef9512f7 = { $model }関数呼び出しはサポートされておらず、自動的に削除されました。
msg-fde41b1d = { $model }マルチモーダル出力はサポートされていないため、テキストモードにダウングレードされました。
msg-4e168d67 = 受信したチャンクに空の候補があります:{ $chunk }
msg-11af7d46 = 受信したチャンクの内容が空です：{ $chunk }
msg-8836d4a2 = リクエストが失敗しました。
msg-757d3828 = モデルリストの取得に失敗しました：{ $res }
msg-7fc6f623 = 画像{ $image_url }取得された結果は空で、無視されます。
msg-0b041916 = サポートされていない追加コンテンツブロックタイプ：{ $res }

### astrbot/core/provider/sources/gsvi_tts_source.py

msg-520e410f = GSVI TTS APIリクエストが失敗しました、ステータスコード：{ $res }エラー:{ $error_text }

### astrbot/core/provider/sources/anthropic_source.py

msg-d6b1df6e = 画像データURIの解析に失敗しました:{ $res }翻訳対象テキスト：...
msg-6c2c0426 = Anthropicでサポートされていない画像URL形式：{ $res }翻訳対象のテキスト：...
msg-999f7680 = completion:{ $completion }
msg-8d2c43ec = APIが空の完了を返しました。
msg-26140afc = Anthropic APIから返された完了応答の解析に失敗しました:{ $completion }翻訳対象のテキスト：
msg-8e4c8c24 = ツール呼び出しパラメータのJSON解析に失敗しました：{ $tool_info }
msg-7fc6f623 = 画像{ $image_url }取得した結果は空であり、無視されます。
msg-0b041916 = サポートされていない追加コンテンツブロックタイプ:{ $res }

### astrbot/core/provider/sources/openai_source.py

msg-bbb399f6 = 画像リクエスト失敗 (%s) が検出され、画像は削除されて再試行されました（テキストコンテンツは保持されています）。
msg-d6f6a3c2 = モデルリストの取得に失敗しました:{ $e }
msg-1f850e09 = APIが不正な完了タイプを返しました：{ $res }翻訳対象テキスト：{ $completion }翻訳対象のテキスト:
msg-999f7680 = 完了：{ $completion }
msg-844635f7 = 予期しない辞書形式のコンテンツ:{ $raw_content }
msg-8d2c43ec = APIが空の完了を返しました。
msg-87d75331 = { $completion_text }
msg-0614efaf = ツールセットが提供されていません
msg-c46f067a = APIから返された完了は、コンテンツセキュリティフィルタリング（AstrBotではない）により拒否されました。
msg-647f0002 = APIによって返された完了結果を解析できません：{ $completion }.
msg-5cc50a15 = API呼び出しが頻繁すぎます。別のキーを使用して再試行してください。現在のキー：{ $res }
msg-c4e639eb = コンテキスト長が制限を超えています。最も古いレコードを削除して再試行してください。現在のレコード数:{ $res }
msg-5f8be4fb = { $res }関数ツール呼び出しはサポートされていません。自動的に削除され、使用には影響しません。
msg-45591836 = モデルは関数呼び出しまたはツール呼び出しをサポートしていないようです。/tool off_all を入力してください。
msg-6e47d22a = API呼び出しに失敗しました。再試行中{ $max_retries }再び失敗しました。
msg-974e7484 = 不明なエラー
msg-7fc6f623 = 画像{ $image_url }結果が空であり、無視されます。
msg-0b041916 = サポートされていない追加コンテンツブロックタイプ:{ $res }

### astrbot/core/provider/sources/gemini_tts_source.py

msg-29fe386a = [Gemini TTS] プロキシを使用中：{ $proxy }
msg-012edfe1 = Gemini TTS APIからオーディオコンテンツが返されませんでした。

### astrbot/core/provider/sources/genie_tts.py

msg-583dd8a6 = genie_ttsを最初にインストールしてください。
msg-935222b4 = キャラクターの読み込みに失敗しました{ $res }翻訳対象テキスト：{ $e }
msg-a6886f9e = Genie TTSはファイルに保存されませんでした。
msg-e3587d60 = Genie TTS生成に失敗しました：{ $e }
msg-3303e3a8 = Genie TTSが以下のオーディオ生成に失敗しました：{ $text }
msg-1cfe1af1 = Genie TTS ストリーミングエラー:{ $e }

### astrbot/core/provider/sources/dashscope_tts.py

msg-f23d2372 = Dashscope TTSモデルが設定されていません。
msg-74a7cc0a = 音声合成に失敗しました。空のコンテンツが返されました。モデルがサポートされていないか、サービスが利用できない可能性があります。
msg-bc8619d3 = dashscope SDKにはMultiModalConversationが不足しています。Qwen TTSモデルを使用するには、dashscopeパッケージをアップグレードしてください。
msg-95bbf71e = Qwen TTSモデルに音声が指定されていないため、デフォルトの「Cherry」を使用します。
msg-3c35d2d0 = モデル '{$model}' のオーディオ合成に失敗しました{ $model }'.'{ $response }
msg-16dc3b00 = base64オーディオデータのデコードに失敗しました。
msg-26603085 = URLからオーディオのダウンロードに失敗しました{ $url }翻訳対象テキスト：{ $e }
msg-78b9c276 = { $res }

### astrbot/core/provider/sources/whisper_selfhosted_source.py

msg-27fda50a = Whisperモデルをダウンロードまたは読み込み中です。時間がかかる場合があります...
msg-4e70f563 = Whisperモデルの読み込みが完了しました。
msg-28cbbf07 = ファイルが存在しません：{ $audio_url }
msg-d98780e5 = シルクファイルをwavに変換中...
msg-e3e1215c = Whisperモデルが初期化されていません

### astrbot/core/provider/sources/openai_tts_api_source.py

msg-d7084760 = [OpenAI TTS] プロキシを使用中：{ $proxy }

### astrbot/core/provider/sources/xinference_rerank_source.py

msg-1ec1e6e4 = Xinference Rerank: APIキーを使用して認証を行います。
msg-7bcb6e1b = Xinference Rerank: APIキーが提供されていません。
msg-b0d1e564 = モデル{ $res }はすでにUIDで実行されています:{ $uid }
msg-16965859 = 起動中{ $res }モデル...
msg-7b1dfdd3 = モデルが起動しました。
msg-3fc7310e = モデル{ $res }' は実行されていず、自動起動が無効になっています。プロバイダーは利用できません。
msg-15f19a42 = Xinferenceモデルの初期化に失敗しました：{ $e }
msg-01af1651 = Xinferenceの初期化中に例外が発生しました：{ $e }
msg-2607cc7a = Xinference 再ランキングモデルが初期化されていません。
msg-3d28173b = Rerank API response:{ $response }
msg-4c63e1bd = Rerank APIが空のリストを返しました。元のレスポンス:{ $response }
msg-cac71506 = Xinference 再ランキング失敗：{ $e }
msg-4135cf72 = Xinferenceのリランクが例外で失敗しました:{ $e }
msg-ea2b36d0 = Xinference 再ランククライアントを終了しています...
msg-633a269f = Xinferenceクライアントのクローズに失敗しました:{ $e }

### astrbot/core/provider/sources/minimax_tts_api_source.py

msg-77c88c8a = SSEメッセージからのJSONデータの解析に失敗しました
msg-7873b87b = MiniMax TTS APIリクエストが失敗しました：{ $e }

### astrbot/core/provider/sources/azure_tts_source.py

msg-93d9b5cf = [Azure TTS] プロキシを使用中：{ $res }
msg-9eea5bcb = クライアントが初期化されていません。'async with'コンテキストを使用してください。
msg-fd53d21d = タイム同期に失敗しました
msg-77890ac4 = OTTSリクエストが失敗しました：{ $e }
msg-c6ec6ec7 = OTTSは音声ファイルを返しませんでした
msg-5ad71900 = 無効なAzureサブスクリプションキー
msg-6416da27 = [Azure TTS Native] プロキシを使用中：{ $res }
msg-90b31925 = OTTSパラメータが不足しています：{ $res }
msg-10f72727 = { $error_msg }
msg-60b044ea = 設定エラー：必須パラメータが不足しています{ $e }
msg-5c7dee08 = サブスクリプションキーの形式が無効です。32文字の英数字または他の[...]形式である必要があります。

### astrbot/core/provider/sources/openai_embedding_source.py

msg-cecb2fbc = [OpenAI Embedding] プロキシを使用中：{ $proxy }

### astrbot/core/provider/sources/vllm_rerank_source.py

msg-6f160342 = Rerank APIが空のリストデータを返しました。元のレスポンス：{ $response_data }

### astrbot/core/provider/sources/xinference_stt_provider.py

msg-4e31e089 = Xinference STT: 認証にAPIキーを使用しています。
msg-e291704e = Xinference STT：APIキーが提供されていません。
msg-b0d1e564 = モデル{ $res }は既にUIDで実行中です：{ $uid }
msg-16965859 = 起動中{ $res }モデル...
msg-7b1dfdd3 = モデルが起動しました。
msg-3fc7310e = モデル{ $res }実行されていません。自動起動が無効になっています。プロバイダーは利用できません。
msg-15f19a42 = Xinferenceモデルの初期化に失敗しました:{ $e }
msg-01af1651 = Xinferenceの初期化が例外で失敗しました:{ $e }
msg-42ed8558 = Xinference STTモデルが初期化されていません。
msg-bbc43272 = オーディオのダウンロードに失敗しました{ $audio_url }、ステータス:{ $res }
msg-f4e53d3d = ファイルが見つかりません:{ $audio_url }
msg-ebab7cac = オーディオバイトが空です。
msg-7fd63838 = オーディオは変換が必要です ({ $conversion_type }一時的なファイルを使用中...
msg-d03c4ede = シルクをwavに変換中...
msg-79486689 = AMRからWAVへの変換中...
msg-c4305a5b = Xinference STT 結果：{ $text }
msg-d4241bd5 = Xinference STT転写がステータスで失敗しました{ $res }翻訳するテキスト：{ $error_text }
msg-8efe4ef1 = Xinference STT が失敗しました:{ $e }
msg-b1554c7c = Xinference STTが例外で失敗しました:{ $e }
msg-9d33941a = 一時ファイルを削除しました:{ $temp_file }
msg-7dc5bc44 = 一時ファイルの削除に失敗しました{ $temp_file }翻訳対象テキスト：{ $e }
msg-31904a1c = Xinference STTクライアントを終了中...
msg-633a269f = Xinferenceクライアントのクローズに失敗しました：{ $e }

### astrbot/core/provider/sources/fishaudio_tts_api_source.py

msg-c785baf0 = [FishAudio TTS] プロキシを使用中:{ $res }
msg-822bce1c = 無効なFishAudio参照モデルID: '{ $res }'. IDは必ず32桁の16進数文字列（例：626bb6d3f3364c9cbc3aa6a67300a664）にしてください。有効なモデルIDは https://fish.audio/zh-CN/discovery から取得できます。
msg-5956263b = Fish Audio APIリクエスト失敗: ステータスコード{ $res }応答内容:{ $error_text }

### astrbot/core/provider/sources/gsv_selfhosted_source.py

msg-5fb63f61 = [GSV TTS] 初期化完了
msg-e0c38c5b = [GSV TTS] 初期化に失敗しました：{ $e }
msg-4d57bc4f = [GSV TTS] プロバイダのHTTPセッションが準備できていないか、閉じています。
msg-2a4a0819 = [GSV TTS] リクエストURL:{ $endpoint }, パラメータ:{ $params }
msg-5fdee1da = [GSV TTS] リクエスト先{ $endpoint }ステータスで失敗しました{ $res }翻訳対象のテキスト：{ $error_text }
msg-3a51c2c5 = [GSV TTS] リクエスト{ $endpoint }ページ{ $res }失敗しました{ $e }再試行中...
msg-49c1c17a = [GSV TTS] リクエスト{ $endpoint }最終失敗:{ $e }
msg-1beb6249 = [GSV TTS] GPTモデルパスを正常に設定しました：{ $res }
msg-17f1a087 = [GSV TTS] GPTモデルのパスが設定されていません。組み込みGPTモデルを使用します。
msg-ddeb915f = [GSV TTS] SoVITSモデルパスの設定が完了しました：{ $res }
msg-bee5c961 = [GSV TTS] SoVITSモデルのパスが設定されていません。組み込みのSoVITSモデルを使用します。
msg-423edb93 = [GSV TTS] モデルパスの設定中にネットワークエラーが発生しました：{ $e }
msg-7d3c79cb = [GSV TTS] モデルパスの設定中に不明なエラーが発生しました：{ $e }
msg-d084916a = [GSV TTS] TTSテキストは空にできません
msg-fa20c883 = [GSV TTS] 音声合成インターフェースを呼び出しています。パラメータ:{ $params }
msg-a7fc38eb = [GSV TTS] 合成に失敗しました、入力テキスト：{ $text }, エラーメッセージ:{ $result }
msg-a49cb96b = [GSV TTS] セッションが閉じられました

### astrbot/core/provider/sources/volcengine_tts.py

msg-4b55f021 = リクエストヘッダー:{ $headers }
msg-d252d96d = リクエストURL:{ $res }
msg-72e07cfd = リクエストボディ:{ $res }翻訳待ちのテキスト：
msg-fb8cdd69 = レスポンスステータスコード：{ $res }
msg-4c62e457 = レスポンス内容：{ $res }翻訳対象のテキスト：...
msg-1477973b = Volcano Engine TTS API がエラーを返しました：{ $error_msg }
msg-75401c15 = Volcano Engine TTS APIリクエストが失敗しました:{ $res }翻訳するテキスト：{ $response_text }
msg-a29cc73d = Volcano Engine TTS 例外の詳細：{ $error_details }
msg-01433007 = Volcano Engine TTS 例外：{ $e }

### astrbot/core/provider/sources/sensevoice_selfhosted_source.py

msg-ee0daf96 = SenseVoiceモデルをダウンロードまたはロードしています。しばらく時間がかかる場合があります...
msg-cd6da7e9 = SenseVoiceモデルの読み込みが完了しました。
msg-28cbbf07 = ファイルが存在しません：{ $audio_url }
msg-d98780e5 = シルクファイルをWAVに変換中...
msg-4e8f1d05 = SenseVoiceによる認識済みのコピー：{ $res }
msg-55668aa2 = 感情情報の抽出に失敗しました
msg-0cdbac9b = 音声ファイルの処理エラー:{ $e }

### astrbot/core/message/components.py

msg-afb10076 = 有効なURLではありません
msg-fe4c33a0 = 有効なファイルではありません：{ $res }
msg-24d98e13 = callback_api_baseが設定されていません。ファイルサービスは利用できません。
msg-a5c69cc9 = 登録日:{ $callback_host }/api/file/{ $token }
msg-3cddc5ef = ダウンロード失敗:{ $url }
msg-1921aa47 = 有効なファイルではありません:{ $url }
msg-2ee3827c = 生成された動画ファイルのコールバックリンク：{ $payload_file }
msg-32f4fc78 = 有効なファイルまたはURLが提供されていません
msg-36375f4c = 非同期コンテキストでダウンロードを同期待機することはできません！この警告は通常、一部のロジックが <File>.file を通じてファイルメッセージセグメントの内容を取得しようとする際に発生します。直接 <File>.file フィールドを取得する代わりに、await get_file() を使用してください。
msg-4a987754 = ファイルのダウンロードに失敗しました：{ $e }
msg-7c1935ee = ダウンロードに失敗しました：FileコンポーネントにURLが指定されていません。
msg-35bb8d53 = 生成ファイルコールバックリンク：{ $payload_file }

### astrbot/core/utils/metrics.py

msg-314258f2 = データベースへの指標の保存に失敗しました:{ $e }

### astrbot/core/utils/trace.py

msg-fffce1b9 = [トレース]{ $payload }
msg-78b9c276 = { $res }

### astrbot/core/utils/webhook_utils.py

msg-64c7ddcf = コールバックAPIベースの取得に失敗しました：{ $e }
msg-9b5d1bb1 = ダッシュボードポートの取得に失敗しました：{ $e }
msg-3db149ad = ダッシュボードSSL設定の取得に失敗しました：{ $e }
msg-3739eec9 = { $display_log }

### astrbot/core/utils/path_util.py

msg-cf211d0f = パスマッピングルールエラー:{ $mapping }
msg-ecea161e = パスマッピング：{ $url }->{ $srcPath }

### astrbot/core/utils/media_utils.py

msg-2f697658 = [Media Utils] メディアの長さを取得：{ $duration_ms }ミリ秒
msg-52dfbc26 = [Media Utils] メディアファイルの長さの取得に失敗しました：{ $file_path }
msg-486d493a = [Media Utils] ffprobeがインストールされていないか、PATHに含まれていません。メディアの長さを取得できません。ffmpegをインストールしてください: https://ffmpeg.org/
msg-0f9c647b = [Media Utils] メディアの長さの取得に失敗しました：{ $e }
msg-aff4c5f8 = [Media Utils] 失敗したOpus出力ファイルをクリーンアップしました：{ $output_path }
msg-82427384 = [Media Utils] 失敗したOpus出力ファイルのクリーンアップ中にエラーが発生しました：{ $e }
msg-215a0cfc = [メディア ユーティリティ] ffmpeg オーディオ変換に失敗しました：{ $error_msg }
msg-8cce258e = ffmpeg変換に失敗しました:{ $error_msg }
msg-f0cfcb92 = [Media Utils] オーディオ変換が成功しました：{ $audio_path }->{ $output_path }
msg-ead1395b = [メディア ユーティリティ] ffmpegがインストールされていないか、PATHに含まれていません。音声フォーマットを変換できません。ffmpegをインストールしてください: https://ffmpeg.org/
msg-5df3a5ee = ffmpegが見つかりません
msg-6322d4d2 = [Media Utils] オーディオフォーマット変換エラー:{ $e }
msg-e125b1a5 = [メディアユーティリティ] 失敗したクリーンアップがクリアされました{ $output_format }出力ファイル：{ $output_path }
msg-5cf417e3 = [メディアユーティリティ] クリーンアップに失敗しました{ $output_format }ファイル出力時のエラー：{ $e }
msg-3766cbb8 = [メディアユーティリティ] ffmpegによるビデオ変換に失敗しました：{ $error_msg }
msg-77f68449 = [Media Utils] ビデオ変換成功:{ $video_path }->{ $output_path }
msg-3fb20b91 = [Media Utils] ffmpegがインストールされていないか、PATHに設定されていません。動画フォーマットの変換ができません。ffmpegをインストールしてください: https://ffmpeg.org/
msg-696c4a46 = [Media Utils] ビデオフォーマット変換エラー:{ $e }
msg-98cc8fb8 = [Media Utils] 失敗したオーディオ出力ファイルのクリーンアップ中にエラーが発生しました:{ $e }
msg-3c27d5e8 = [メディアユーティリティ] 失敗したビデオカバーファイルのクリーンアップ中にエラーが発生しました:{ $e }
msg-072774ab = ffmpegカバー画像抽出失敗：{ $error_msg }

### astrbot/core/utils/session_waiter.py

msg-0c977996 = 待機タイムアウト
msg-ac406437 = session_filterはSessionFilterでなければなりません

### astrbot/core/utils/history_saver.py

msg-fb7718cb = 会話履歴の解析に失敗しました: %s

### astrbot/core/utils/io.py

msg-665b0191 = SSL証明書の検証に失敗しました{ $url }SSL検証を無効化（CERT_NONE）してフォールバックします。これは安全ではなく、アプリケーションを中間者攻撃にさらす可能性があります。証明書の問題を調査して解決してください。
msg-04ab2fae = ファイルのダウンロードに失敗しました：{ $res }
msg-63dacf99 = ファイルサイズ:{ $res }KB | ファイルアドレス:{ $url }
msg-14c3d0bb = ダウンロードの進捗状況:{ $res }速度：{ $speed }キロバイト/秒
msg-4e4ee68e = SSL証明書の検証に失敗しました。SSL検証はオフになっています（安全でないため、一時的なダウンロードのみに使用してください）。対象サーバーの証明書設定を確認してください。
msg-5a3beefb = SSL証明書の検証に失敗しました{ $url }. 未検証接続 (CERT_NONE) にフォールバックします。これは安全ではなく、アプリケーションを中間者攻撃にさらします。リモートサーバーの証明書の問題を調査してください。
msg-315e5ed6 = 指定されたリリースバージョンのAstrBot WebUIファイルをダウンロードする準備中:{ $dashboard_release_url }
msg-c709cf82 = 指定されたバージョンのAstrBot WebUIのダウンロード準備中：{ $url }

### astrbot/core/utils/shared_preferences.py

msg-9a1e6a9a = 特定の設定を取得する際、scope_idとkeyはNoneにできません。

### astrbot/core/utils/migra_helper.py

msg-497ddf83 = サードパーティエージェントランナー構成の移行に失敗しました：{ $e }
msg-78b9c276 = { $res }
msg-e21f1509 = プロバイダーの移行{ $res }新しい構造へ
msg-dd3339e6 = プロバイダーソース構造の移行が完了しました
msg-1cb6c174 = バージョン4.5から4.6への移行に失敗しました:{ $e }
msg-a899acc6 = Webchatセッションの移行に失敗しました：{ $e }
msg-b9c52817 = トークン使用量カラムの移行に失敗しました:{ $e }
msg-d9660ff5 = プロバイダーソース構造の移行に失敗しました:{ $e }

### astrbot/core/utils/temp_dir_cleaner.py

msg-752c7cc8 = 無効{ $res }={ $configured }, 代替として{ $res_2 }MB。
msg-b1fc3643 = 一時ファイルをスキップ{ $path }statエラーにより：{ $e }
msg-5e61f6b7 = 一時ファイルの削除に失敗しました{ $res }翻訳するテキスト：{ $e }
msg-391449f0 = 一時ディレクトリの制限を超過しました{ $total_size }翻訳対象テキスト：{ $limit }). 削除済み{ $removed_files }ファイル、リリース済み{ $released }バイト数（ターゲット{ $target_release }バイト）。
msg-aaf1e12a = TempDirCleanerが開始されました。interval={ $res }cleanup_ratio={ $res_2 }
msg-e6170717 = TempDirCleanerの実行に失敗しました：{ $e }
msg-0fc33fbc = TempDirCleaner が停止しました。

### astrbot/core/utils/tencent_record_helper.py

msg-377ae139 = pilkモジュールがインストールされていません。Admin Panel -> Platform Logs -> Install pip Libraries に移動して、pilkライブラリをインストールしてください。
msg-f4ab0713 = pyffmpeg変換に失敗しました：{ $e }変換にはffmpegコマンドラインを試してください
msg-33c88889 = [FFmpeg] 標準出力：{ $res }
msg-2470430c = [FFmpeg] stderr:{ $res }
msg-1321d5f7 = [FFmpeg] 戻り値:{ $res }
msg-c39d210c = 生成されたWAVファイルが存在しないか、空です。
msg-6e04bdb8 = pilkがインストールされていません: pip install pilk

### astrbot/core/utils/pip_installer.py

msg-aa9e40b8 = pip モジュールが利用できません (sys.executable={ $res }, frozen={ $res_2 }, ASTRBOT_DESKTOP_CLIENT={ $res_3 })
msg-560f11f2 = 依存関係ファイルの読み込みに失敗しました。競合検出をスキップします: %s
msg-91ae1d17 = サイトパッケージのメタデータの読み込みに失敗しました。代替モジュール名を使用します: %s
msg-c815b9dc = { $conflict_message }
msg-e8d4b617 = プラグインのサイトパッケージから %s をロードしました: %s
msg-4ef5d900 = プラグインのsite-packagesから%sを優先しながら、依存関係%sを回復しました。
msg-0bf22754 = プラグインのsite-packagesにモジュール %s が見つかりません: %s
msg-76a41595 = プラグイン site-packages からモジュール %s を優先できませんでした: %s
msg-3d4de966 = ローダー %s (%s) のpip distlibファインダーへのパッチ適用に失敗しました: %s
msg-117d9cf4 = Distlibファインダーパッチはローダー%s (%s)に対して有効になりませんでした。
msg-b7975236 = フリーズされたローダー用のpip distlibファインダーにパッチを適用しました: %s (%s)
msg-b1fa741c = _finder_registryが利用できないため、distlibファインダーのパッチ適用をスキップします。
msg-4ef0e609 = distlibファインダーの登録APIが利用できないため、パッチ適用をスキップします。
msg-b8c741dc = Pipパッケージマネージャー: pip{ $res }
msg-6b72a960 = インストールに失敗しました、エラーコード:{ $result_code }
msg-c8325399 = { $line }

### astrbot/core/utils/llm_metadata.py

msg-d6535d03 = メタデータの取得に成功しました{ $res }LLMs.
msg-8cceaeb0 = LLMメタデータの取得に失敗しました:{ $e }

### astrbot/core/utils/network_utils.py

msg-54b8fda8 = 翻訳するテキスト：{ $provider_label }ネットワーク/プロキシ接続失敗{ $error_type }プロキシアドレス:{ $effective_proxy }, エラー：{ $error }
msg-ea7c80f1 = 翻訳対象テキスト：{ $provider_label }ネットワーク接続に失敗しました{ $error_type })。 エラー：{ $error }
msg-f8c8a73c = 翻訳対象のテキスト：{ $provider_label }] プロキシを使用:{ $proxy }

### astrbot/core/utils/t2i/renderer.py

msg-4225607b = AstrBot APIによる画像レンダリングに失敗しました：{ $e }ローカルレンダリングにフォールバックしています。

### astrbot/core/utils/t2i/local_strategy.py

msg-94a58a1e = フォントを読み込めません
msg-d5c7d255 = 画像の読み込みに失敗しました: HTTP{ $res }
msg-7d59d0a0 = 画像の読み込みに失敗しました：{ $e }

### astrbot/core/utils/t2i/template_manager.py

msg-47d72ff5 = テンプレート名に不正な文字が含まれています。
msg-d1b2131b = テンプレートが存在しません。
msg-dde05b0f = 同じ名前のテンプレートは既に存在します。
msg-0aa209bf = ユーザーテンプレートが存在しないため、削除できません。

### astrbot/core/utils/t2i/network_strategy.py

msg-be0eeaa7 = 正常に取得しました{ $res }公式T2Iエンドポイント。
msg-3bee02f4 = 公式エンドポイントの取得に失敗しました：{ $e }
msg-829d3c71 = HTTP{ $res }
msg-05fb621f = エンドポイント{ $endpoint }失敗しました:{ $e }次を試しています...
msg-9a836926 = すべてのエンドポイントが失敗しました：{ $last_exception }

### astrbot/core/utils/quoted_message/extractor.py

msg-24049c48 = quoted_message_parser: %d 回ホップ後にネストされた転送メッセージの取得を停止します

### astrbot/core/utils/quoted_message/onebot_client.py

msg-062923e6 = quoted_message_parser: アクション %s がパラメータ %s で失敗しました: %s
msg-f33f59d5 = quoted_message_parser: アクション %s のすべての試行が失敗しました、last_params=%s、error=%s

### astrbot/core/utils/quoted_message/image_resolver.py

msg-94224a01 = quoted_message_parser: 非画像ローカルパス参照をスキップしました ref=%s
msg-3e6c0d14 = quoted_message_parser: 引用画像 ref=%s を %d 回のアクション後も解決できませんでした

### astrbot/core/agent/tool_image_cache.py

msg-45da4af7 = ToolImageCacheが初期化されました。キャッシュディレクトリ:{ $res }
msg-017bde96 = 保存されたツールイメージ:{ $file_path }
msg-29398f55 = ツールイメージの保存に失敗しました:{ $e }
msg-128aa08a = キャッシュされた画像の読み込みに失敗しました{ $file_path }翻訳対象テキスト:{ $e }
msg-3c111d1f = キャッシュクリーンアップ中のエラー:{ $e }
msg-eeb1b849 = クリーンアップしました{ $cleaned }期限切れのキャッシュ画像

### astrbot/core/agent/message.py

msg-d38656d7 = { $invalid_subclass_error_msg }
msg-42d5a315 = 検証できません{ $value }コンテンツパートとして
msg-ffc376d0 = コンテンツは、役割が 'assistant' で tool_calls が None でない場合を除き、必須です。

### astrbot/core/agent/mcp_client.py

msg-6a61ca88 = 警告: 'mcp' 依存関係が不足しています、MCPサービスは利用できません。
msg-45995cdb = 警告：'mcp'依存関係が欠落しているか、MCPライブラリのバージョンが古すぎるため、Streamable HTTP接続が利用できません。
msg-2866b896 = MCP接続設定にトランスポートまたはタイプフィールドがありません
msg-3bf7776b = MCPサーバー{ $name }エラー:{ $msg }
msg-10f72727 = { $error_msg }
msg-19c9b509 = MCPクライアントは初期化されていません
msg-5b9b4918 = MCPクライアント{ $res }既に再接続中です、スキップ中
msg-c1008866 = 再接続できません：接続構成が見つかりません
msg-7c3fe178 = MCPサーバーへの再接続を試みています{ $res }翻訳待ちテキスト：...
msg-783f3b85 = MCPサーバーへの再接続に成功しました{ $res }
msg-da7361ff = MCPサーバーへの再接続に失敗しました{ $res }翻訳対象のテキスト：{ $e }
msg-c0fd612e = MCPセッションはMCP機能ツールには利用できません。
msg-8236c58c = MCPツール{ $tool_name }呼び出しに失敗しました（ClosedResourceError）、再接続を試みています...
msg-044046ec = 現在の終了スタックを閉じるエラー：{ $e }

### astrbot/core/agent/tool.py

msg-983bc802 = FunctionTool.call() はサブクラスによって実装されるか、またはハンドラーを設定する必要があります。

### astrbot/core/agent/context/compressor.py

msg-6c75531b = サマリーの生成に失敗しました：{ $e }

### astrbot/core/agent/context/manager.py

msg-59241964 = コンテキスト処理中のエラー：{ $e }
msg-a0d672dc = 圧縮がトリガーされました、圧縮を開始しています...
msg-e6ef66f0 = 圧縮が完了しました。{ $prev_tokens }->{ $tokens_after_summary }トークン数、圧縮率：{ $compress_rate }%.
msg-3fe644eb = 圧縮後もコンテキストが最大トークンを超えているため、半減切り捨てを適用中...

### astrbot/core/agent/runners/tool_loop_agent_runner.py

msg-960ef181 = %sからフォールバックチャットプロバイダー%sに切り替えました。
msg-4f999913 = チャットモデル %s がエラーレスポンスを返しました。次のプロバイダーへのフォールバックを試行中です。
msg-c042095f = チャットモデル %s のリクエストエラー: %s
msg-81b2aeae = { $tag }RunCtx.messages -> [{ $res }翻訳するテキスト：{ $res_2 }
msg-55333301 = リクエストが設定されていません。最初にreset()を呼び出してください。
msg-d3b77736 = on_agent_beginフックでのエラー：{ $e }
msg-61de315c = ユーザーによりエージェントの実行停止が要求されました。
msg-8eb53be3 = エージェント完了フックでのエラー：{ $e }
msg-508d6d17 = LLM応答エラー：{ $res }
msg-ed80313d = LLMがツール呼び出しなしで空のアシスタントメッセージを返しました。
msg-970947ae = 追加済み{ $res }LLMレビューのためにコンテキストにキャッシュされた画像
msg-6b326889 = エージェントが最大ステップ数に到達しました（{ $max_step }最終応答を強制します。
msg-948ea4b7 = エージェントがツールを使用中：{ $res }
msg-a27ad3d1 = ツールの使用：{ $func_tool_name }パラメーター：{ $func_tool_args }
msg-812ad241 = 指定されたツールが見つかりません：{ $func_tool_name }スキップされます。
msg-20b4f143 = ツール{ $func_tool_name }期待されるパラメータ：{ $res }
msg-78f6833c = ツール{ $func_tool_name }予期しないパラメータを無視:{ $ignored_params }
msg-2b523f8c = on_tool_startフックでのエラー：{ $e }
msg-ec868b73 = { $func_tool_name }戻り値がない、または結果が既に直接ユーザーに送信されています。
msg-6b61e4f1 = ツールがサポートされていないタイプを返しました：{ $res }.
msg-34c13e02 = on_tool_endフックでのエラー：{ $e }
msg-78b9c276 = { $res }
msg-a1493b6d = ツール `{ $func_tool_name }結果:{ $last_tcr_content }

### astrbot/core/agent/runners/base.py

msg-24eb2b08 = エージェント状態遷移:{ $res }->{ $new_state }

### astrbot/core/agent/runners/dashscope/dashscope_agent_runner.py

msg-dc1a9e6e = Alibaba Cloud Bailian APIキーは空にできません。
msg-c492cbbc = Alibaba Cloud Bailian APP IDは空にできません。
msg-bcc8e027 = Alibaba Cloud Bailianアプリのタイプは空にできません。
msg-55333301 = リクエストが設定されていません。最初にreset()を呼び出してください。
msg-d3b77736 = on_agent_begin フックでのエラー：{ $e }
msg-e3af4efd = Alibaba Cloud Bailian リクエストが失敗しました:{ $res }
msg-fccf5004 = dashscopeストリームチャンク：{ $chunk }
msg-100d7d7e = Alibaba Cloud Bailianリクエストが失敗しました: request_id={ $res }, code={ $res_2 }, message={ $res_3 }、ドキュメントを参照してください: https://help.aliyun.com/zh/model-studio/developer-reference/error-code
msg-10f72727 = { $error_msg }
msg-e8615101 = { $chunk_text }
msg-dfb132c4 = { $ref_text }
msg-8eb53be3 = on_agent_doneフックでのエラー：{ $e }
msg-650b47e1 = Alibaba Cloud Bailianは現在、画像入力をサポートしておらず、画像コンテンツは自動的に無視されます。

### astrbot/core/agent/runners/coze/coze_agent_runner.py

msg-448549b0 = Coze APIキーは空にできません。
msg-b88724b0 = Coze Bot IDは空にできません。
msg-ea5a135a = Coze APIのベースURL形式が正しくありません。http://またはhttps://で始める必要があります。
msg-55333301 = リクエストが設定されていません。最初にreset()を呼び出してください。
msg-d3b77736 = エージェント開始フックでのエラー:{ $e }
msg-5aa3eb1c = Cozeリクエストが失敗しました：{ $res }
msg-333354c6 = コンテキスト画像の処理に失敗しました：{ $e }
msg-2d9e1c08 = 画像の処理に失敗しました{ $url }翻訳対象のテキスト：{ $e }
msg-1f50979d = { $content }
msg-6fe5588b = Cozeメッセージ完了
msg-d2802f3b = Cozeチャット完了
msg-ba4afcda = Cozeエラー：{ $error_code }-{ $error_msg }
msg-ee300f25 = Cozeはコンテンツを返しませんでした
msg-8eb53be3 = エージェント完了フックでのエラー：{ $e }
msg-034c1858 = [Coze] キャッシュされたfile_idを使用中：{ $file_id }
msg-475d8a41 = [Coze] 画像のアップロードが成功し、キャッシュされました、ファイルID:{ $file_id }
msg-696dad99 = 画像の処理に失敗しました{ $image_url }翻訳するテキスト：{ $e }
msg-7793a347 = 画像処理に失敗しました：{ $e }

### astrbot/core/agent/runners/coze/coze_api_client.py

msg-76f97104 = Coze API認証に失敗しました。APIキーが正しいかご確認ください。
msg-3653b652 = ファイルアップロード応答ステータス:{ $res }, コンテンツ:{ $response_text }
msg-13fe060c = ファイルのアップロードに失敗しました、ステータスコード：{ $res }応答：{ $response_text }
msg-5604b862 = ファイルアップロード応答の解析に失敗しました：{ $response_text }
msg-c0373c50 = ファイルアップロードに失敗しました:{ $res }
msg-010e4299 = [Coze] 画像が正常にアップロードされました、ファイルID:{ $file_id }
msg-719f13cb = ファイルアップロードタイムアウト
msg-121c11fb = ファイルアップロードに失敗しました：{ $e }
msg-f6101892 = 画像のダウンロードに失敗しました、ステータスコード:{ $res }
msg-c09c56c9 = 画像のダウンロードに失敗しました{ $image_url }翻訳するテキスト：{ $e }
msg-15211c7c = 画像のダウンロードに失敗しました：{ $e }
msg-2245219f = Coze chat_messages ペイロード:{ $payload }, params:{ $params }
msg-d8fd415c = Coze APIストリーミングリクエストが失敗しました、ステータスコード:{ $res }
msg-f5cc7604 = Coze API ストリーミングリクエストタイムアウト{ $timeout }秒
msg-30c0a9d6 = Coze APIストリーミングリクエストが失敗しました:{ $e }
msg-11509aba = Coze APIリクエストが失敗しました、ステータスコード:{ $res }
msg-002af11d = Coze APIがJSON以外の形式を返しました
msg-c0b8fc7c = Coze APIリクエストタイムアウト
msg-a68a33fa = Coze APIリクエストが失敗しました：{ $e }
msg-c26e068e = Cozeメッセージリストの取得に失敗しました:{ $e }
msg-5bc0a49d = アップロード済みファイルID:{ $file_id }
msg-7c08bdaf = イベント：{ $event }

### astrbot/core/agent/runners/dify/dify_api_client.py

msg-cd6cd7ac = 無効なDify JSONデータを削除：{ $res }
msg-3654a12d = チャットメッセージペイロード：{ $payload }
msg-8e865c52 = Dify /chat-messages APIリクエストが失敗しました:{ $res }.{ $text }
msg-2d7534b8 = workflow_run ペイロード:{ $payload }
msg-89918ba5 = Dify /workflows/run インターフェースリクエストが失敗しました:{ $res }.{ $text }
msg-8bf17938 = file_pathとfile_dataは両方ともNoneにすることはできません
msg-b6ee8f38 = Difyファイルアップロードに失敗しました：{ $res }.{ $text }

### astrbot/core/agent/runners/dify/dify_agent_runner.py

msg-55333301 = リクエストが設定されていません。最初にreset()を呼び出してください。
msg-d3b77736 = エージェント開始フックでのエラー:{ $e }
msg-0d493427 = Difyリクエスト失敗：{ $res }
msg-fe594f21 = Dify 画像アップロードの応答:{ $file_response }
msg-3534b306 = 画像をアップロードした後に不明なDify応答を受け取りました。{ $file_response }, 画像は無視されます。
msg-08441fdf = 画像のアップロードに失敗しました：{ $e }
msg-3972f693 = dify resp chunk:{ $chunk }
msg-6c74267b = Difyメッセージ終了
msg-1ce260ba = Difyでエラーが発生しました:{ $chunk }
msg-a12417dd = Difyでエラーステータスが発生しました：{ $res }メッセージ:{ $res_2 }
msg-f8530ee9 = dify workflow resp chunk:{ $chunk }
msg-386a282e = Difyワークフロー (ID:{ $res }実行を開始します。
msg-0bc1299b = Difyワークフローノード (ID:{ $res }タイトル：{ $res_2 }) 実行が完了しました。
msg-5cf24248 = Difyワークフロー (ID:{ $res }実行完了
msg-e2c2159f = Difyワークフロー結果：{ $chunk }
msg-4fa60ef1 = Difyワークフローエラー：{ $res }
msg-1f786836 = Difyワークフローの出力に指定されたキー名が含まれていません：{ $res }
msg-c4a70ffb = 不明なDify APIタイプ:{ $res }
msg-51d321fd = Difyリクエスト結果が空です。デバッグログを確認してください。
msg-8eb53be3 = エージェント完了フックでのエラー：{ $e }

### astrbot/core/star/session_plugin_manager.py

msg-16cc2a7a = プラグイン{ $res }セッション中{ $session_id }無効化されました、プロセッサをスキップしています{ $res_2 }

### astrbot/core/star/star_manager.py

msg-bfa28c02 = watchfilesがインストールされていないため、プラグインのホットリロードは実現できません。
msg-f8e1c445 = プラグインのホットリロード監視タスクの例外:{ $e }
msg-78b9c276 = { $res }
msg-28aeca68 = ファイル変更が検出されました：{ $changes }
msg-aeec7738 = プラグインを検出しました{ $plugin_name }ファイルが変更されました、再読み込み中...
msg-4f989555 = プラグイン{ $d }main.pyが見つかりません{ $d }.py、スキップします。
msg-74b32804 = プラグインをインストール中{ $p }必要な依存関係：{ $pth }
msg-936edfca = プラグインを更新{ $p }依存関係の失敗。コード：{ $e }
msg-ebd47311 = プラグイン{ $root_dir_name }インポートに失敗しました。インストール済みの依存関係からの回復を試みています：{ $import_exc }
msg-1b6e94f1 = プラグイン{ $root_dir_name }依存関係は site-packages から復元されたため、再インストールをスキップします。
msg-81b7c9b9 = プラグイン{ $root_dir_name }インストールされた依存関係の復元に失敗しました。依存関係を再インストールします。{ $recover_exc }
msg-22fde75d = プラグインが存在しません。
msg-3a307a9e = プラグインのメタデータ情報が不完全です。name、desc、version、およびauthorは必須項目です。
msg-55e089d5 = モジュールを削除{ $key }
msg-64de1322 = モジュールを削除{ $module_name }
msg-66823424 = モジュール{ $module_name }読み込まれていません
msg-45c8df8d = プラグインをクリアしました{ $dir_name }In{ $key }モジュール
msg-f7d9aa9b = クリーンアッププロセッサー：{ $res }
msg-3c492aa6 = クリーンアップツール:{ $res }
msg-e0002829 = プラグイン{ $res }適切に終了していません:{ $e }このプラグインの誤動作を引き起こす可能性があります。
msg-0fe27735 = プラグインを読み込み中{ $root_dir_name }...
msg-b2ec4801 = { $error_trace }
msg-db351291 = プラグイン{ $root_dir_name }インポートに失敗しました。理由：{ $e }
msg-a3db5f45 = 失敗したプラグインはまだプラグインリストにあります。クリーンアップ中...
msg-58c66a56 = プラグイン{ $root_dir_name }メタデータの読み込みに失敗しました:{ $e }デフォルトのメタデータを使用します。
msg-da764b29 = { $metadata }
msg-17cd7b7d = プラグイン{ $res }無効になっています。
msg-4baf6814 = プラグイン{ $path }デコレータ経由で登録されていません。レガシーメソッドを使用して読み込みを試みます。
msg-840994d1 = プラグインが見つかりません{ $plugin_dir_path }メタデータの
msg-944ffff1 = 権限フィルターを挿入{ $cmd_type }へ{ $res }の{ $res_2 }方法。
msg-64edd12c = hook(on_plugin_loaded) ->{ $res }-{ $res_2 }
msg-db49f7a1 = ----- プラグイン{ $root_dir_name }読み込みに失敗しました
msg-26039659 = 翻訳対象テキスト：|{ $line }
msg-4292f44d = 翻訳対象テキスト：----------------------------------
msg-d2048afe = 同期化コマンドの設定に失敗しました:{ $e }
msg-df515dec = インストール失敗したプラグインディレクトリをクリーンアップしました:{ $plugin_path }
msg-1f2aa1a9 = 失敗したプラグインのインストールディレクトリをクリーンアップできませんでした：{ $plugin_path }理由：{ $e }
msg-1e947210 = 失敗したプラグインインストールの設定をクリーンアップしました：{ $plugin_config_path }
msg-7374541f = インストールに失敗したプラグインの構成のクリーンアップに失敗しました:{ $plugin_config_path }, 理由:{ $e }
msg-e871b08f = プラグインの読み込み{ $dir_name }README.mdファイルの読み取りに失敗しました：{ $e }
msg-70ca4592 = このプラグインはAstrBotの予約済みプラグインであり、アンインストールすることはできません。
msg-e247422b = プラグイン{ $plugin_name }通常終了していません{ $e }リソースリークやその他の問題を引き起こす可能性があります。
msg-0c25dbf4 = プラグイン{ $plugin_name }データが不完全なため、アンインストールできません。
msg-d6f8142c = プラグインは正常に削除されましたが、プラグインフォルダの削除に失敗しました:{ $e }addons/plugins/にあるこのフォルダを手動で削除できます。
msg-6313500c = 削除されたプラグイン{ $plugin_name }設定ファイル
msg-f0f01b67 = プラグイン設定ファイルの削除に失敗しました:{ $e }
msg-c4008b30 = 削除済みプラグイン{ $plugin_name }永続データ（plugin_data）
msg-88d1ee05 = プラグインの永続データ（plugin_data）の削除に失敗しました：{ $e }
msg-ba805469 = 削除されたプラグイン{ $plugin_name }永続データ（plugins_data）
msg-cf6eb821 = プラグインの永続データの削除に失敗しました（plugins_data）：{ $e }
msg-e1853811 = プラグインを削除しました{ $plugin_name }処理関数{ $res }翻訳するテキスト:{ $res_2 })
msg-95b20050 = プラグインを削除しました{ $plugin_name }プラットフォームアダプター{ $adapter_name }
msg-9f248e88 = このプラグインはAstrBot用の予約済みプラグインであり、アップデートできません。
msg-ff435883 = プラグインを終了しています{ $res }翻訳待ちのテキスト：...
msg-355187b7 = プラグイン{ $res }未アクティベート、終了不要、スキップします。
msg-4369864f = フック(on_plugin_unloaded) ->{ $res }-{ $res_2 }
msg-1b95e855 = プラグイン{ $plugin_name }それは存在しません。
msg-c1bc6cd6 = プラグインを検出しました{ $res }インストール済み、古いプラグインを終了中...
msg-4f3271db = 重複プラグインが検出されました{ $res }異なるディレクトリに存在します{ $res_2 }, 終了しています...
msg-d247fc54 = 新しいプラグインのmetadata.yamlの読み取りに失敗しました、重複名チェックをスキップします：{ $e }
msg-0f8947f8 = プラグインアーカイブの削除に失敗しました：{ $e }

### astrbot/core/star/session_llm_manager.py

msg-7b90d0e9 = セッション{ $session_id }TTSステータスが更新されました：{ $res }

### astrbot/core/star/config.py

msg-c2189e8d = 名前空間は空であってはなりません。
msg-97f66907 = 名前空間はinternal_で始めることはできません。
msg-09179604 = キーはstr型のみをサポートしています。
msg-1163e4f1 = 値は、str、int、float、bool、listタイプのみをサポートします。
msg-ed0f93e4 = 設定ファイル{ $namespace }.jsonは存在しません。
msg-e3b5cdfb = 構成項目{ $key }存在しません。

### astrbot/core/star/star_tools.py

msg-397b7bf9 = StarToolsが初期化されていません
msg-ca30e638 = アダプターが見つかりません: AiocqhttpAdapter
msg-77ca0ccb = サポートされていないプラットフォーム:{ $platform }
msg-3ed67eb2 = 呼び出し元モジュール情報を取得できません
msg-e77ccce6 = モジュールを取得できません{ $res }メタデータ情報
msg-76ac38ee = プラグイン名を取得できません
msg-751bfd23 = ディレクトリを作成できません{ $data_dir }権限が不十分です
msg-68979283 = ディレクトリを作成できません{ $data_dir }翻訳対象のテキスト：{ $e }

### astrbot/core/star/context.py

msg-60eb9e43 = プロバイダ{ $chat_provider_id }見つかりません
msg-da70a6fb = エージェントは最終的なLLM応答を生成しませんでした
msg-141151fe = プロバイダが見つかりません
msg-a5cb19c6 = IDが見つかりませんでした{ $provider_id }プロバイダー。これは、プロバイダー（モデル）IDを変更したことが原因である可能性があります。
msg-2a44300b = セッションソースの会話モデル（プロバイダ）タイプが不正です：{ $res }
msg-37c286ea = 返されたプロバイダーは TTSProvider タイプではありません。
msg-ff775f3b = 返されたプロバイダーはSTTProviderのタイプではありません
msg-fd8c8295 = セッションのプラットフォームが見つかりません{ $res }メッセージが送信されていません
msg-2b806a28 = plugin(module_path){ $module_path }) LLMツールを追加しました:{ $res }

### astrbot/core/star/updator.py

msg-66be72ec = プラグイン{ $res }リポジトリアドレスが指定されていません。
msg-7a29adea = プラグイン{ $res }ルートディレクトリ名が指定されていません。
msg-99a86f88 = プラグインを更新中、パス:{ $plugin_path }リポジトリアドレス:{ $repo_url }
msg-df2c7e1b = 古いバージョンのプラグインを削除{ $plugin_path }フォルダが失敗しました：{ $e }, 上書きインストールを使用して。
msg-b3471491 = アーカイブを解凍中:{ $zip_path }
msg-7197ad11 = 一時ファイルを削除：{ $zip_path }そして{ $res }
msg-f8a43aa5 = アップデートファイルの削除に失敗しました。手動で削除できます。{ $zip_path }および{ $res }

### astrbot/core/star/command_management.py

msg-011581bb = 指定されたハンドラ関数が存在しないか、または命令ではありません。
msg-a0c37004 = コマンド名は空にできません。
msg-ae8b2307 = コマンド名 '{ $candidate_full }はすでに別の命令によって使用されています。
msg-247926a7 = エイリアス{ $alias_full }他の命令によって既に占有されています。
msg-dbd19a23 = 権限タイプは管理者またはメンバーでなければなりません。
msg-9388ea1e = コマンドが見つからない場合のプラグイン
msg-0dd9b70d = 命令解析処理関数{ $res }失敗しました、この指示をスキップします。理由：{ $e }

### astrbot/core/star/base.py

msg-57019272 = get_config() 失敗しました:{ $e }

### astrbot/core/star/register/star.py

msg-64619f8e = 'register_star' デコレータは非推奨となり、将来のバージョンで削除されます。

### astrbot/core/star/register/star_handler.py

msg-7ff2d46e = 登録説明{ $command_name }サブコマンドの使用時に sub_command パラメータが指定されていませんでした。
msg-b68436e1 = ベア命令を登録する際にcommand_nameパラメータが指定されていません。
msg-1c183df2 = { $command_group_name }コマンドグループのサブコマンドが指定されていません。
msg-9210c7e8 = ルートコマンドグループの名前が指定されていません。
msg-678858e7 = 命令グループの登録に失敗しました。
msg-6c3915e0 = LLM機能ツール{ $res }_{ $llm_tool_name }のパラメーター{ $res_2 }型注釈がありません。
msg-1255c964 = LLM機能ツール{ $res }_{ $llm_tool_name }サポートされていないパラメータタイプ：{ $res_2 }

### astrbot/core/star/filter/command.py

msg-995944c2 = パラメータ '{ $param_name }(GreedyStr) は最後の引数でなければなりません。
msg-04dbdc3a = 必須パラメーターが不足しています。このコマンドの完全なパラメーター：{ $res }
msg-bda71712 = パラメーター{ $param_name }ブール値（true/false、yes/no、1/0）である必要があります。
msg-a9afddbf = パラメーター{ $param_name }型エラー。完全なパラメータ:{ $res }

### astrbot/core/star/filter/custom_filter.py

msg-8f3eeb6e = オペランドはCustomFilterのサブクラスでなければなりません。
msg-732ada95 = CustomFilterクラスは、他のCustomFilterとのみ連携して動作できます。
msg-51c0c77d = CustomFilterクラスは他のCustomFilterとのみ操作できます。

### astrbot/core/db/vec_db/faiss_impl/document_storage.py

msg-c2dc1d2b = データベース接続が初期化されていません。空の結果を返します。
msg-51fa7426 = データベース接続が初期化されていないため、削除操作をスキップします
msg-43d1f69f = データベース接続が初期化されていません、0を返します

### astrbot/core/db/vec_db/faiss_impl/embedding_storage.py

msg-8e5fe535 = faissがインストールされていません。'pip install faiss-cpu'または'pip install faiss-gpu'を使用してインストールしてください。
msg-9aa7b941 = ベクトル次元が一致しません、予想される次元：{ $res }, 実際:{ $res_2 }

### astrbot/core/db/vec_db/faiss_impl/vec_db.py

msg-9f9765dc = 埋め込みを生成中{ $res }コンテンツ...
msg-385bc50a = 生成された埋め込み{ $res }コンテンツの内容{ $res_2 }秒。

### astrbot/core/db/migration/migra_token_usage.py

msg-c3e53a4f = データベース移行を開始しています（conversations.token_usageカラムの追加中）...
msg-ccbd0a41 = token_usage 列は既に存在するため、マイグレーションをスキップします
msg-39f60232 = トークン使用量列が正常に追加されました
msg-4f9d3876 = token_usageマイグレーション完了
msg-91571aaf = 移行中にエラーが発生しました：{ $e }

### astrbot/core/db/migration/migra_3_to_4.py

msg-7805b529 = 移行{ $total_cnt }古いセッションデータを新しいテーブルに移行中...
msg-6f232b73 = 進捗状況:{ $progress }% ({ $res }翻訳対象のテキスト：{ $total_cnt })
msg-6b1def31 = この古いセッションの特定データが見つかりませんでした：{ $conversation }, スキップします。
msg-b008c93f = 古いセッションを移行する{ $res }失敗:{ $e }
msg-6ac6313b = 正常に移行されました{ $total_cnt }古いセッションデータを新しいテーブルに移行します。
msg-6b72e89b = 古いプラットフォームからのデータ移行、offset_sec:{ $offset_sec }秒。
msg-bdc90b84 = 移行{ $res }古いプラットフォームデータを新しいテーブルに移行中...
msg-e6caca5c = 古いプラットフォームデータが見つかりませんでした。移行をスキップします。
msg-1e824a79 = 進捗状況:{ $progress }% ({ $res }翻訳するテキスト：{ $total_buckets })
msg-813384e2 = 移行プラットフォーム統計に失敗しました：{ $platform_id },{ $platform_type }, タイムスタンプ:{ $bucket_end }
msg-27ab191d = 移行成功{ $res }古いプラットフォームのデータを新しいテーブルに移行します。
msg-8e6280ed = マイグレーション{ $total_cnt }古いWebChatセッションデータを新しいテーブルに移行中...
msg-cad66fe1 = 古いWebChatセッションを移行する{ $res }失敗しました
msg-63748a46 = 移行が成功しました{ $total_cnt }古いWebChatセッションデータを新しいテーブルに移行します。
msg-dfc93fa4 = 移行{ $total_personas }新しいテーブルへのPersona設定中...
msg-ff85e45c = 進捗状況:{ $progress }% ({ $res }翻訳対象テキスト：{ $total_personas })
msg-c346311e = マイグレートペルソナ{ $res }翻訳するテキスト：{ $res_2 }...) から新しいテーブルへの移行に成功しました。
msg-b6292b94 = Persona設定の解析に失敗しました：{ $e }
msg-90e5039e = グローバル設定の移行{ $key }成功、値:{ $value }
msg-d538da1c = セッションの移行{ $umo }ダイアログデータが新しいテーブルに正常に移行されました、プラットフォームID:{ $platform_id }
msg-ee03c001 = セッションの移行{ $umo }会話データの取得に失敗しました：{ $e }
msg-5c4339cd = セッションの移行{ $umo }サービス構成が新しいテーブルに正常に移行されました、プラットフォームID:{ $platform_id }
msg-4ce2a0b2 = 移行セッション{ $umo }サービス構成の失敗：{ $e }
msg-2e62dab9 = セッションの移行{ $umo }変数の設定に失敗しました：{ $e }
msg-afbf819e = 移行セッション{ $umo }プロバイダー設定が新しいテーブルに正常に移行されました、プラットフォームID:{ $platform_id }
msg-959bb068 = セッションの移行{ $umo }プロバイダーの設定に失敗しました：{ $e }

### astrbot/core/db/migration/helper.py

msg-a48f4752 = データベース移行を開始しています...
msg-45e31e8e = データベース移行が完了しました。

### astrbot/core/db/migration/migra_45_to_46.py

msg-782b01c1 = migrate_45_to_46: abconf_data は dict 型ではありません (type={ $res }). 値:{ $abconf_data }
msg-49e09620 = バージョン4.5から4.6への移行を開始しています
msg-791b79f8 = バージョン45から46への移行が正常に完了しました

### astrbot/core/db/migration/migra_webchat_session.py

msg-53fad3d0 = データベースマイグレーションの実行を開始しています（WebChatセッションの移行）...
msg-7674efb0 = 移行が必要なWebChatデータは見つかりませんでした。
msg-139e39ee = 検索{ $res }WebChatセッションの移行が必要です。
msg-cf287e58 = セッション{ $session_id }既に存在しています、スキップします
msg-062c72fa = WebChatセッションの移行が完了しました！正常に移行されました：{ $res }, スキップ:{ $skipped_count }
msg-a516cc9f = 移行が必要な新しいセッションはありません。
msg-91571aaf = 移行中にエラーが発生しました：{ $e }

### astrbot/core/knowledge_base/kb_helper.py

msg-7b3dc642 = - LLM呼び出しが試行で失敗しました{ $res }翻訳対象のテキスト：{ $res_2 }. エラー:{ $res_3 }
msg-4ba9530f = - チャンク処理に失敗しました{ $res }試行回数。原文を使用しています。
msg-77670a3a = ナレッジベース{ $res }Embeddingプロバイダーが設定されていません
msg-8e9eb3f9 = IDが見つかりませんでした{ $res }埋め込みプロバイダー
msg-3e426806 = IDが見つかりません{ $res }再ランクプロバイダー
msg-6e780e1e = 事前に分割されたテキストを使用してアップロード中、合計{ $res }ブロック
msg-f4b82f18 = pre_chunked_textが提供されていない場合、file_contentは空であってはなりません。
msg-975f06d7 = ドキュメントのアップロードに失敗しました:{ $e }
msg-969b17ca = マルチメディアファイルのクリーンアップに失敗しました{ $media_path }翻訳するテキスト：{ $me }
msg-18d25e55 = IDが見つかりません{ $doc_id }ドキュメンテーション
msg-f5d7c34c = エラー: Tavily APIキーがprovider_settingsで設定されていません。
msg-975d88e0 = URLからコンテンツを抽出できませんでした{ $url }翻訳対象テキスト：{ $e }
msg-cfe431b3 = URLからコンテンツが抽出されませんでした：{ $url }
msg-e7f5f836 = コンテンツクリーニング後に有効なテキストが抽出されませんでした。コンテンツクリーニング機能を無効にするか、より高性能なLLMモデルで再試行してください。
msg-693aa5c5 = コンテンツクリーニングが有効になっていないため、指定されたパラメータでチャンキングを行います：chunk_size={ $chunk_size }, chunk_overlap={ $chunk_overlap }
msg-947d8f46 = コンテンツクリーニングは有効ですが、cleaning_provider_idが提供されていないため、クリーニングをスキップし、デフォルトのチャンキングを使用します。
msg-31963d3f = IDが見つかりません{ $cleaning_provider_id }LLMプロバイダーまたはタイプが正しくありません。
msg-82728272 = 初期チャンキングが完了しました、生成中{ $res }修復するブロック。
msg-6fa5fdca = ブロック{ $i }例外の処理：{ $res }元のブロックにフォールバックします。
msg-6780e950 = テキスト修復完了：{ $res }オリジナルブロック{ $res_2 }最終ブロック。
msg-79056c76 = プロバイダー 'を使用{ $cleaning_provider_id }コンテンツのクリーンアップに失敗しました：{ $e }

### astrbot/core/knowledge_base/kb_mgr.py

msg-98bfa670 = ナレッジベースモジュールを初期化中...
msg-7da7ae15 = ナレッジベースモジュールのインポートに失敗しました:{ $e }
msg-842a3c65 = 必要な依存関係がインストールされていることを確認してください：pypdf、aiofiles、Pillow、rank-bm25
msg-c9e943f7 = ナレッジベースモジュールの初期化に失敗しました：{ $e }
msg-78b9c276 = { $res }
msg-9349e112 = ナレッジベースデータベースが初期化されました:{ $DB_PATH }
msg-7605893e = ナレッジベースを作成する際には、embedding_provider_id を指定する必要があります。
msg-0b632cbd = ナレッジベース名{ $kb_name }すでに存在します
msg-ca30330f = ナレッジベースを閉じる{ $kb_id }失敗しました:{ $e }
msg-00262e1f = ナレッジベースメタデータデータベースのクローズに失敗しました：{ $e }
msg-3fc9ef0b = ID付きのナレッジベース{ $kb_id }見つかりません。

### astrbot/core/knowledge_base/kb_db_sqlite.py

msg-b850e5d8 = ナレッジベースデータベースは閉鎖されています:{ $res }

### astrbot/core/knowledge_base/parsers/util.py

msg-398b3580 = 一時的にサポートされていないファイル形式:{ $ext }

### astrbot/core/knowledge_base/parsers/url_parser.py

msg-2de85bf5 = エラー：Tavily APIキーが設定されていません。
msg-98ed69f4 = エラー：URLは空でない文字列である必要があります。
msg-7b14cdb7 = Tavilyウェブ抽出失敗：{ $reason }、ステータス：{ $res }
msg-cfe431b3 = URLからコンテンツを抽出できませんでした：{ $url }
msg-b0897365 = URLの取得に失敗しました{ $url }翻訳対象テキスト：{ $e }
msg-975d88e0 = URLからコンテンツの抽出に失敗しました{ $url }翻訳対象テキスト:{ $e }

### astrbot/core/knowledge_base/parsers/text_parser.py

msg-70cbd40d = ファイルをデコードできません：{ $file_name }

### astrbot/core/knowledge_base/chunking/recursive.py

msg-21db456a = チャンクサイズは0より大きくなければなりません
msg-c0656f4e = チャンクオーバーラップは非負でなければなりません
msg-82bd199c = chunk_overlapはchunk_sizeより小さくなければなりません

### astrbot/core/knowledge_base/retrieval/manager.py

msg-fcc0dde2 = ナレッジベースID{ $kb_id }インスタンスが見つかりませんでした。このナレッジベースの取得はスキップされました。
msg-320cfcff = Dense retrieval across{ $res }ベースが取られました{ $res_2 }s が返されました{ $res_3 }結果
msg-90ffcfc8 = スパースリトリーバル全体で{ $res }ベースが取得しました{ $res_2 }sが返されました{ $res_3 }結果。
msg-12bcf404 = ランク融合がかかりました{ $res }s が返されました{ $res_2 }結果。
msg-28c084bc = vec_db for kb_id{ $kb_id }FaissVecDBではありません
msg-cc0230a3 = ナレッジベース{ $kb_id }高密度検索に失敗しました:{ $e }

### astrbot/core/skills/skill_manager.py

msg-ed9670ad = Zipファイルが見つかりません:{ $zip_path }
msg-73f9cf65 = アップロードされたファイルは有効なZIPアーカイブではありません。
msg-69eb5f95 = ZIPアーカイブは空です。
msg-9e9abb4c = { $top_dirs }
msg-20b8533f = Zipアーカイブには単一の最上位フォルダを含める必要があります。
msg-1db1caf7 = 無効なスキルフォルダ名です。
msg-d7814054 = Zipアーカイブには絶対パスが含まれています。
msg-179bd10e = ZIPアーカイブに無効な相対パスが含まれています。
msg-90f2904e = ZIPアーカイブに予期しないトップレベルエントリが含まれています。
msg-95775a4d = スキルフォルダ内にSKILL.mdが見つかりません。
msg-a4117c0b = 展開後のスキルフォルダが見つかりません。
msg-94041ef2 = スキルは既に存在します。

### astrbot/core/backup/importer.py

msg-c046b6e4 = { $msg }
msg-0e6f1f5d = スタート{ $zip_path }バックアップのインポート
msg-2bf97ca0 = バックアップのインポートが完了しました:{ $res }
msg-e67dda98 = バックアップファイルにバージョン情報がありません
msg-8f871d9f = バージョン差異警告：{ $res }
msg-2d6da12a = テーブルがクリアされました{ $table_name }
msg-7d21b23a = テーブルをクリア{ $table_name }失敗：{ $e }
msg-ab0f09db = ナレッジベーステーブルがクリアされました{ $table_name }
msg-7bcdfaee = ナレッジベーステーブルをクリア{ $table_name }失敗しました：{ $e }
msg-43f008f1 = ナレッジベースのクリーンアップ{ $kb_id }失敗しました:{ $e }
msg-985cae66 = 不明なテーブル：{ $table_name }
msg-dfa8b605 = レコードをインポート{ $table_name }失敗しました：{ $e }
msg-89a2120c = テーブルのインポート{ $table_name }翻訳するテキスト：{ $count }レコード
msg-f1dec753 = ナレッジベースのレコードをインポートする{ $table_name }失敗しました:{ $e }
msg-9807bcd8 = ドキュメントブロックのインポートに失敗しました：{ $e }
msg-98a66293 = 添付ファイルをインポート{ $name }失敗しました:{ $e }
msg-39f2325f = バックアップバージョンはディレクトリバックアップをサポートしていないため、ディレクトリのインポートをスキップします。
msg-689050b6 = 既存のディレクトリはバックアップされました{ $target_dir }宛先{ $backup_path }
msg-d51b3536 = インポート ディレクトリ{ $dir_name }翻訳対象テキスト：{ $file_count }ファイル

### astrbot/core/backup/exporter.py

msg-c7ed7177 = バックアップのエクスポートを開始する{ $zip_path }
msg-8099b694 = バックアップのエクスポートが完了しました:{ $zip_path }
msg-75a4910d = バックアップのエクスポートに失敗しました:{ $e }
msg-2821fc92 = テーブルをエクスポート{ $table_name }翻訳するテキスト：{ $res }レコード
msg-52b7c242 = テーブルをエクスポート{ $table_name }失敗しました:{ $e }
msg-56310830 = ナレッジベーステーブルのエクスポート{ $table_name }翻訳するテキスト:{ $res }レコード
msg-f4e8f57e = ナレッジベーステーブルのエクスポート{ $table_name }失敗しました：{ $e }
msg-8e4ddd12 = ナレッジベースドキュメントのエクスポートに失敗しました：{ $e }
msg-c1960618 = FAISSインデックスのエクスポート:{ $archive_path }
msg-314bf920 = FAISSインデックスのエクスポートに失敗しました：{ $e }
msg-528757b2 = ナレッジベースのメディアファイルのエクスポートに失敗しました:{ $e }
msg-d89d6dfe = ディレクトリが存在しません、スキップ中:{ $full_path }
msg-94527edd = ファイルをエクスポート{ $file_path }失敗：{ $e }
msg-cb773e24 = エクスポートディレクトリ{ $dir_name }翻訳対象のテキスト：{ $file_count }ファイル,{ $total_size }バイト
msg-ae929510 = エクスポートディレクトリ{ $dir_path }失敗しました：{ $e }
msg-93e331d2 = エクスポート添付ファイル失敗:{ $e }

### astrbot/core/computer/computer_client.py

msg-7cb974b8 = スキルバンドルをサンドボックスにアップロード中...
msg-130cf3e3 = サンドボックスへのスキルバンドルのアップロードに失敗しました。
msg-99188d69 = 一時的なスキルZIPの削除に失敗しました：{ $zip_path }
msg-3f3c81da = 不明なブータタイプ：{ $booter_type }
msg-e20cc33a = セッションのサンドボックス起動エラー{ $session_id }翻訳対象のテキスト：{ $e }

### astrbot/core/computer/tools/fs.py

msg-99ab0efe = アップロード結果：{ $result }
msg-bca9d578 = ファイル{ $local_path }サンドボックスにアップロードされました{ $file_path }
msg-da21a6a5 = ファイルのアップロードエラー{ $local_path }翻訳するテキスト：{ $e }
msg-93476abb = ファイル{ $remote_path }サンドボックスからダウンロードしました{ $local_path }
msg-079c5972 = ファイルメッセージ送信エラー：{ $e }
msg-ce35bb2c = ファイルのダウンロード中にエラーが発生しました{ $remote_path }翻訳対象のテキスト：{ $e }

### astrbot/core/computer/booters/local.py

msg-487d0c91 = パスは許可されたコンピュータルートの外にあります。
msg-e5eb5377 = ブロックされた安全でないシェルコマンド。
msg-9e1e117f = ローカルコンピューターのブーターがセッション用に初期化されました:{ $session_id }
msg-2d7f95de = ローカルコンピュータブーターのシャットダウンが完了しました。
msg-82a45196 = LocalBooterはupload_file操作をサポートしていません。代わりにshellを使用してください。
msg-0457524a = LocalBooterはdownload_file操作をサポートしていません。代わりにshellを使用してください。

### astrbot/core/computer/booters/shipyard.py

msg-b03115b0 = サンドボックスシップを取得しました：{ $res }セッション:{ $session_id }
msg-c5ce8bde = Shipyardサンドボックスの可用性をチェック中にエラーが発生しました。{ $e }

### astrbot/core/computer/booters/boxlite.py

msg-019c4d18 = 操作の実行に失敗しました：{ $res } { $error_text }
msg-b135b7bd = ファイルのアップロードに失敗しました：{ $e }
msg-873ed1c8 = ファイルが見つかりません：{ $path }
msg-f58ceec6 = ファイルのアップロード中に予期しないエラーが発生しました:{ $e }
msg-900ab999 = サンドボックスのヘルスチェック中{ $ship_id }オン{ $res }翻訳対象のテキスト：
msg-2a50d6f3 = サンドボックス{ $ship_id }健全です
msg-fbdbe32f = セッションのための起動中(Boxlite):{ $session_id }、これには時間がかかる場合があります...
msg-b1f13f5f = Boxliteブートストラップがセッションで開始されました：{ $session_id }
msg-e93d0c30 = 船のためのBoxliteブーターをシャットダウンしています：{ $res }
msg-6deea473 = 船舶用Boxliteブートローダ：{ $res }停止しました

### astrbot/core/cron/manager.py

msg-724e64a9 = ハンドラが不足しているため、基本のcronジョブ %s のスケジュールをスキップします。
msg-78ef135f = cronジョブ%sのタイムゾーン%sが無効です。システムのタイムゾーンにフォールバックします。
msg-e71c28d3 = 実行1回のみのジョブにrun_atタイムスタンプがありません
msg-dd46e69f = cronジョブのスケジュールに失敗しました{ $res }翻訳対象テキスト：{ $e }
msg-aa2e4688 = 未知のcronジョブタイプ:{ $res }
msg-186627d9 = Cronジョブ{ $job_id }失敗しました:{ $e }
msg-cb955de0 = 基本的cronジョブハンドラが見つかりません{ $res }
msg-2029c4b2 = ActiveAgentCronJobにセッションがありません。
msg-6babddc9 = Cronジョブの無効なセッション：{ $e }
msg-865a2b07 = cronジョブのメインエージェントの構築に失敗しました。
msg-27c9c6b3 = Cronジョブエージェントが応答を受け取りませんでした

### astrbot/utils/http_ssl_common.py

msg-7957c9b6 = 証明書信頼バンドルをSSLコンテキストに読み込めませんでした。システムの信頼ストアのみにフォールバックします: %s

### astrbot/cli/__main__.py

msg-fe494da6 = { $logo_tmpl }
msg-c8b2ff67 = AstrBot CLIへようこそ！
msg-78b9c276 = { $res }
msg-14dd710d = 不明なコマンド:{ $command_name }

### astrbot/cli/utils/basic.py

msg-f4e0fd7b = 管理パネルがインストールされていません
msg-2d090cc3 = 管理パネルをインストールしています...
msg-2eeb67e0 = 管理パネルのインストールが完了しました
msg-9c727dca = 管理パネルはすでに最新バージョンです。
msg-11b49913 = 管理者パネルバージョン:{ $version }
msg-f0b6145e = ダウンロード管理パネルの取得に失敗しました:{ $e }
msg-9504d173 = 管理者パネルディレクトリを初期化中...
msg-699e2509 = 管理パネルの初期化が完了しました

### astrbot/cli/utils/plugin.py

msg-e327bc14 = デフォルトブランチからダウンロード中{ $author }翻訳対象テキスト：{ $repo }
msg-c804f59f = リリース情報の取得に失敗しました：{ $e }提供されたURLは直接使用されます
msg-aa398bd5 = マスターブランチが存在しません、メインブランチをダウンロードしようとしています。
msg-5587d9fb = 読み取る{ $yaml_path }失敗しました:{ $e }
msg-8dbce791 = オンラインプラグインリストの取得に失敗しました：{ $e }
msg-6999155d = プラグイン{ $plugin_name }インストールされていません、更新できません
msg-fa5e129a = 読み込み中{ $repo_url } { $res }プラグイン{ $plugin_name }翻訳対象テキスト：...
msg-9ac1f4db = プラグイン{ $plugin_name } { $res }成功
msg-b9c719ae = { $res }プラグイン{ $plugin_name }エラーが発生しました:{ $e }

### astrbot/cli/commands/cmd_conf.py

msg-635b8763 = ログレベルは、DEBUG/INFO/WARNING/ERROR/CRITICALのいずれかでなければなりません。
msg-ebc250dc = ポートは1から65535の範囲内でなければなりません
msg-6ec400b6 = ポートは数値でなければなりません
msg-0b62b5ce = ユーザー名を空にすることはできません
msg-89b5d3d5 = パスワードは空にできません
msg-92e7c8ad = 無効なタイムゾーン:{ $value }有効なIANAタイムゾーン名を使用してください
msg-e470e37d = コールバックインターフェースのベースアドレスは、http://またはhttps://で始まる必要があります。
msg-6b615721 = { $root }有効なAstrBotルートディレクトリではありません。初期化が必要な場合は、astrbot init を使用してください。
msg-f74c517c = 設定ファイルの解析に失敗しました：{ $e }
msg-d7c58bcc = 設定パスの競合:{ $res }辞書ではありません
msg-e16816cc = サポートされていない設定項目:{ $key }
msg-e9cce750 = 設定が更新されました：{ $key }
msg-1ed565aa = 元の値: ********
msg-1bf9569a = 新しい値: ********
msg-f2a20ab3 = 元の値：{ $old_value }
msg-0c104905 = 新しい値:{ $validated_value }
msg-ea9b4e2c = 不明な設定項目：{ $key }
msg-4450e3b1 = 設定の設定に失敗しました:{ $e }
msg-ba464bee = { $key }翻訳するテキスト:{ $value }
msg-72aab576 = 設定の取得に失敗しました:{ $e }
msg-c1693d1d = 現在の設定：
msg-50be9b74 = { $key }翻訳するテキスト：{ $value }

### astrbot/cli/commands/cmd_init.py

msg-a90a250e = 現在のディレクトリ：{ $astrbot_root }
msg-4deda62e = これがAstrBotのルートディレクトリであることを確認した場合、現在のディレクトリに.astrbotファイルを作成し、AstrBotのデータディレクトリとしてマークする必要があります。
msg-3319bf71 = 作成済み{ $dot_astrbot }
msg-7054f44f = { $res }翻訳するテキスト：{ $path }
msg-b19edc8a = AstrBotを初期化中...
msg-eebc39e3 = ロックファイルを取得できません。別のインスタンスが実行中かどうかを確認してください。
msg-e16da80f = 初期化に失敗しました：{ $e }

### astrbot/cli/commands/cmd_run.py

msg-41ecc632 = { $astrbot_root }有効なAstrBotルートディレクトリではありません。必要に応じて'astrbot init'を使用して初期化してください。
msg-0ccaca23 = プラグインの自動リロードを有効にする
msg-220914e7 = AstrBotは閉鎖されました...
msg-eebc39e3 = ロックファイルを取得できません。別のインスタンスが実行中か確認してください。
msg-85f241d3 = ランタイムエラーが発生しました：{ $e }{ "\u000A" }{ $res }

### astrbot/cli/commands/cmd_plug.py

msg-cbd8802b = { $base }有効なAstrBotルートディレクトリではありません。初期化が必要な場合はastrbot initを使用してください。
msg-78b9c276 = { $res }
msg-83664fcf = { $val } { $val } { $val } { $val } { $val }
msg-56f3f0bf = { $res } { $res_2 } { $res_3 } { $res_4 } { $desc }
msg-1d802ff2 = プラグイン{ $name }既に存在します
msg-a7be9d23 = バージョン番号は x.y または x.y.z 形式である必要があります。
msg-4d81299b = リポジトリアドレスはhttpで始まる必要があります
msg-93289755 = プラグインテンプレートをダウンロード中...
msg-b21682dd = プラグイン情報を書き換えています...
msg-bffc8bfa = プラグイン{ $name }作成成功
msg-08eae1e3 = インストールされているプラグインはありません
msg-1a021bf4 = インストール可能なプラグインが見つかりません{ $name }、存在しないか、すでにインストールされている可能性があります。
msg-c120bafd = プラグイン{ $name }存在しないかインストールされていません
msg-63da4867 = プラグイン{ $name }アンインストール済み
msg-e4925708 = プラグインのアンインストール{ $name }失敗しました：{ $e }
msg-f4d15a87 = プラグイン{ $name }更新の必要がない、または更新できない
msg-94b035f7 = 更新が必要なプラグインはありません。
msg-0766d599 = 発見{ $res }プラグインを更新する必要があります
msg-bd5ab99c = プラグインを更新中{ $plugin_name }翻訳対象のテキスト：...
msg-e32912b8 = '{$query}' の一致する結果はありません{ $query }のプラグイン

### astrbot/dashboard/server.py

msg-e88807e2 = ルートが見つかりません
msg-06151c57 = APIキーがありません
msg-88dca3cc = 無効なAPIキー
msg-fd267dc8 = APIキーのスコープが不十分です
msg-076fb3a3 = 認証エラー
msg-6f214cc1 = トークンの有効期限が切れました
msg-5041dc95 = トークンが無効です
msg-1241c883 = ポートを確認してください{ $port }エラーが発生しました：{ $e }
msg-7c3ba89d = ダッシュボード用のランダムJWTシークレットを初期化しました。
msg-a3adcb66 = WebUIは無効になっています
msg-44832296 = WebUIを起動中、リスニングアドレス:{ $scheme }://{ $host }翻訳するテキスト：{ $port }
msg-3eed4a73 = ヒント：WebUIはすべてのネットワークインターフェースでリッスンしますので、セキュリティにご注意ください。（data/cmd_config.json内のdashboard.hostを設定することでホストを変更できます）
msg-289a2fe8 = エラー: ポート{ $port }使用中{ "\u000A" }使用情報：{ "\u000A" }           { $process_info }{ "\u000A" }必ず以下を確認してください：{ "\u000A" }1. 現在、他のAstrBotインスタンスは実行されていません。{ "\u000A" }2. ポート{ $port }他のプログラムに占有されていません{ "\u000A" }3. 他のポートを使用する場合は、設定ファイルを変更してください。
msg-6d1dfba8 = ポート{ $port }使用中
msg-228fe31e = { "\u000A" }✨✨✨{ "\u000A" }AstrBot v{ $VERSION }WebUIが起動しました、アクセス先:{ "\u000A" }{ "\u000A" }
msg-3749e149 = ➜  ローカル:{ $scheme }://localhost:{ $port }{ "\u000A" }
msg-3c2a1175 = ➜  ネットワーク:{ $scheme }://{ $ip }翻訳対象のテキスト：{ $port }{ "\u000A" }
msg-d1ba29cb = デフォルトのユーザー名とパスワード: astrbot{ "\u000A" }✨✨✨{ "\u000A" }
msg-d5182f70 = ダッシュボードへのリモートアクセスのために、data/cmd_config.json で dashboard.host を設定してください。
msg-c0161c7c = { $display }
msg-ac4f2855 = dashboard.ssl.enableがtrueの場合、cert_fileとkey_fileを設定する必要があります。
msg-3e87aaf8 = SSL証明書ファイルが存在しません：{ $cert_path }
msg-5ccf0a9f = SSL秘密鍵ファイルが存在しません：{ $key_path }
msg-5e4aa3eb = SSL CA証明書ファイルが存在しません：{ $ca_path }
msg-cb049eb2 = AstrBot WebUIは正常にシャットダウンされました。

### astrbot/dashboard/utils.py

msg-160bd44a = t-SNE可視化に必要なライブラリが不足しています。matplotlibとscikit-learnをインストールしてください：{ e }
msg-aa3a3dbf = ナレッジベースが見つかりません
msg-0e404ea3 = FAISSインデックスが存在しません:{ $index_path }
msg-8d92420c = インデックスが空です
msg-24c0450e = 抽出{ $res }可視化のためのベクトル...
msg-632d0acf = t-SNE次元削減を開始中...
msg-61f0449f = 視覚的チャートを生成中...
msg-4436ad2b = t-SNE可視化の生成エラー:{ $e }
msg-78b9c276 = { $res }

### astrbot/dashboard/routes/update.py

msg-a3503781 = 移行に失敗しました:{ $res }
msg-543d8e4d = 移行に失敗しました:{ $e }
msg-251a5f4a = アップデートのチェックに失敗しました:{ $e }（プロジェクトの更新を除き、通常の使用には影響しません）
msg-aa6bff26 = /api/update/releases:{ $res }
msg-c5170c27 = 管理パネルファイルのダウンロードに失敗しました：{ $e }.
msg-db715c26 = 依存関係を更新中...
msg-9a00f940 = 依存関係の更新に失敗しました：{ $e }
msg-6f96e3ba = /api/update_project:{ $res }
msg-3217b509 = 管理パネルファイルのダウンロードに失敗しました:{ $e }
msg-9cff28cf = /api/update_dashboard:{ $res }
msg-1198c327 = デモモードではこの操作は許可されていません
msg-38e60adf = パッケージパラメータが不足しているか無効です。
msg-a1191473 = /api/update_pip:{ $res }

### astrbot/dashboard/routes/lang_route.py

msg-0d18aac8 = [LangRoute] 言語:{ $lang }
msg-bf610e68 = langは必須パラメータです。

### astrbot/dashboard/routes/auth.py

msg-ee9cf260 = セキュリティのため、できるだけ早くデフォルトのパスワードを変更してください。
msg-87f936b8 = ユーザー名またはパスワードが正しくありません
msg-1198c327 = デモモードではこの操作は許可されていません
msg-25562cd3 = 元のパスワードが正しくありません
msg-d31087d2 = 新しいユーザー名と新しいパスワードは両方とも空にできません。
msg-b512c27e = 2回入力された新しいパスワードが一致しません
msg-7b947d8b = cmd_configにJWT秘密鍵が設定されていません。

### astrbot/dashboard/routes/backup.py

msg-6920795d = 期限切れのアップロードセッションをクリーンアップ:{ $upload_id }
msg-3e96548d = 期限切れのアップロードセッションのクリーンアップに失敗しました:{ $e }
msg-259677a9 = シャードディレクトリのクリーンアップに失敗しました:{ $e }
msg-d7263882 = バックアップマニフェストの読み取りに失敗しました：{ $e }
msg-40f76598 = 無効なバックアップファイルをスキップしています：{ $filename }
msg-18a49bfc = バックアップリストの取得に失敗しました：{ $e }
msg-78b9c276 = { $res }
msg-6e08b5a5 = バックアップ作成に失敗しました:{ $e }
msg-9cce1032 = バックグラウンドエクスポートタスク{ $task_id }失敗しました:{ $e }
msg-55927ac1 = バックアップファイルが見つかりません
msg-374cab8a = ZIP形式のバックアップファイルをアップロードしてください
msg-d53d6730 = アップロードされたバックアップファイルを保存しました：{ $unique_filename }(元の名前：{ $res })
msg-98e64c7f = バックアップファイルのアップロードに失敗しました:{ $e }
msg-49c3b432 = ファイル名パラメータが不足しています
msg-df33d307 = 無効なファイルサイズ
msg-162ad779 = マルチパートアップロードの初期化: upload_id={ $upload_id }, filename={ $unique_filename }、total_chunks={ $total_chunks }
msg-de676924 = マルチパートアップロードの初期化に失敗しました：{ $e }
msg-eecf877c = 必須パラメータが不足しています
msg-f175c633 = 無効なシャードインデックス
msg-ad865497 = シャードデータがありません
msg-947c2d56 = アップロードセッションは存在しないか、有効期限が切れています。
msg-f3a464a5 = シャードインデックスが範囲外です
msg-7060da1d = チャンク受信中: upload_id={ $upload_id }, チャンク={ $res }翻訳対象テキスト：{ $total_chunks }
msg-06c107c1 = チャンクのアップロードに失敗しました：{ $e }
msg-f040b260 = アップロードソースとしてバックアップをマークしました:{ $zip_path }
msg-559c10a8 = バックアップソースのマークに失敗しました：{ $e }
msg-d1d752ef = upload_idパラメータが見つかりません
msg-390ed49a = シャードが不完全で、不足しています：{ $res }翻訳テキスト：...
msg-8029086a = シャードのアップロードが完了しました:{ $filename }, size={ $file_size }, chunks={ $total }
msg-4905dde5 = マルチパートアップロードの完了に失敗しました:{ $e }
msg-b63394b1 = マルチパートアップロードのキャンセル:{ $upload_id }
msg-2b39da46 = アップロード失敗を取り消しました：{ $e }
msg-f12b1f7a = 無効なファイル名
msg-44bb3b89 = バックアップファイルが存在しません:{ $filename }
msg-b005980b = バックアップファイルの事前チェックに失敗しました：{ $e }
msg-65b7ede1 = まずインポートを確認してください。インポートにより既存データがクリアおよび上書きされ、この操作は取り消せません。
msg-b152e4bf = バックアップのインポートに失敗しました：{ $e }
msg-5e7f1683 = 背景インポートタスク{ $task_id }失敗：{ $e }
msg-6906aa65 = Missing parameter task_id
msg-5ea3d72c = タスクが見つかりません
msg-f0901aef = タスクの進行状況の取得に失敗しました:{ $e }
msg-8d23792b = パラメータfilenameが不足しています
msg-4188ede6 = 不足しているパラメータトークン
msg-0c708312 = サーバー構成エラー
msg-cc228d62 = トークンの有効期限が切れました。ページを更新してもう一度お試しください。
msg-5041dc95 = 無効なトークン
msg-96283fc5 = バックアップファイルが存在しません
msg-00aacbf8 = バックアップのダウンロードに失敗しました：{ $e }
msg-3ea8e256 = バックアップの削除に失敗しました:{ $e }
msg-e4a57714 = 新しい名前のパラメータが不足しています
msg-436724bb = 新しいファイル名が無効です
msg-9f9d8558 = ファイル名{ $new_filename }既に存在しています
msg-a5fda312 = バックアップファイル名変更:{ $filename }->{ $new_filename }
msg-e7c82339 = バックアップの名前変更に失敗しました:{ $e }

### astrbot/dashboard/routes/command.py

msg-1d47363b = handler_full_nameとenabledは両方とも必須です。
msg-35374718 = handler_full_nameとnew_nameの両方が必須です。
msg-f879f2f4 = ハンドラーのフルネームと権限は両方とも必須です。

### astrbot/dashboard/routes/subagent.py

msg-78b9c276 = { $res }
msg-eda47201 = サブエージェント設定の取得に失敗しました:{ $e }
msg-3e5b1fe0 = 構成はJSONオブジェクトである必要があります
msg-9f285dd3 = サブエージェント構成の保存に失敗しました:{ $e }
msg-665f4751 = 利用可能なツールの取得に失敗しました：{ $e }

### astrbot/dashboard/routes/config.py

msg-680e7347 = 設定項目{ $path }{ $key }型定義がありません、検証をスキップします
msg-ef2e5902 = 設定を保存中、is_core={ $is_core }
msg-78b9c276 = { $res }
msg-acef166d = 設定の検証中に例外が発生しました：{ $e }
msg-42f62db0 = フォーマット検証に失敗しました：{ $errors }
msg-3e668849 = 設定データがありません
msg-196b9b25 = Missing provider_source_id
msg-dbbbc375 = プロバイダーソースが見つかりません
msg-a77f69f4 = オリジナルIDがありません
msg-96f154c4 = 設定データが不足または誤っています
msg-c80b2c0f = プロバイダーソースID '{ $res }は既に存在します。別のIDをお試しください。
msg-537b700b = ルーティングテーブルデータが欠落しているか、または不正確です
msg-b5079e61 = ルーティングテーブルの更新に失敗しました：{ $e }
msg-cf97d400 = UMOまたは構成ファイルIDが見つかりません
msg-2a05bc8d = UMOが見つかりません
msg-7098aa3f = ルーティングテーブルエントリの削除に失敗しました:{ $e }
msg-902aedc3 = 設定ファイルIDがありません
msg-b9026977 = abconf_idはNoneにすることはできません
msg-acf0664a = 削除に失敗しました
msg-59c93c1a = 設定ファイルの削除に失敗しました:{ $e }
msg-930442e2 = 更新に失敗しました
msg-7375d4dc = 設定ファイルの更新に失敗しました:{ $e }
msg-53a8fdb2 = プロバイダーの確認を試みています:{ $res }(ID:{ $res_2 }, タイプ:{ $res_3 }, モデル:{ $res_4 })
msg-8b0a48ee = プロバイダ{ $res }(ID:{ $res_2 }) が利用可能です。
msg-7c7180a7 = プロバイダー{ $res }翻訳対象テキスト：(ID:{ $res_2 }) は利用できません。エラー：{ $error_message }
msg-1298c229 = トレースバック{ $res }翻訳対象テキスト：{ "\u000A" }{ $res_2 }
msg-d7f9a42f = { $message }
msg-cd303a28 = API呼び出し: /config/provider/check_one id={ $provider_id }
msg-55b8107a = IDが '{ $provider_id }プロバイダーマネージャーに見つかりません。
msg-d1a98a9b = IDが「{ $provider_id }見つかりません
msg-cb9c402c = パラメータprovider_typeが不足しています
msg-e092d4ee = パラメータ provider_id がありません
msg-1ff28fed = IDが見つかりません{ $provider_id }プロバイダー
msg-92347c35 = プロバイダー{ $provider_id }型はモデルリストの取得をサポートしていません
msg-d0845a10 = Missing parameter provider_config
msg-5657fea4 = プロバイダ設定にタイプフィールドがありません
msg-09ed9dc7 = プロバイダーアダプターの読み込みに失敗しました。プロバイダータイプの設定を確認するか、サーバーログを参照してください。
msg-1cce1cd4 = 該当なし{ $provider_type }プロバイダーアダプター
msg-8361e44d = 見つかりません{ $provider_type }クラス
msg-4325087c = プロバイダはEmbeddingProviderのタイプではありません。
msg-a9873ea4 = 検出済み{ $res }埋め込みベクトルの次元は{ $dim }
msg-d170e384 = 埋め込み次元の取得に失敗しました：{ $e }
msg-abfeda72 = ソースIDパラメータが不足しています
msg-0384f4c9 = IDが見つかりません{ $provider_source_id }プロバイダーソース
msg-aec35bdb = provider_source に type フィールドがありません
msg-cbb9d637 = プロバイダーアダプターの動的インポートに失敗しました：{ $e }
msg-468f64b3 = プロバイダー{ $provider_type }モデルリストの取得はサポートされていません。
msg-cb07fc1c = プロバイダーソースを取得する{ $provider_source_id }モデルリスト:{ $models }
msg-d2f6e16d = モデルリストの取得に失敗しました：{ $e }
msg-25ea8a96 = サポートされていないスコープ:{ $scope }
msg-23c8933f = 名前またはキーパラメータが不足しています
msg-536e77ae = プラグイン{ $name }見つからないか、設定がない
msg-1b6bc453 = 設定項目が見つからないか、ファイルタイプではありません
msg-fc0a457e = ファイルがアップロードされていません
msg-31c718d7 = 無効な名前パラメータ
msg-e1edc16e = 名前パラメータが不足しています
msg-8e634b35 = 無効なパスパラメータ
msg-0b52a254 = プラグイン{ $name }見つかりません
msg-bff0e837 = パラメーターエラー
msg-2f29d263 = ロボット名は変更できません
msg-1478800f = 対応するプラットフォームが見つかりません
msg-ca6133f7 = 不足しているパラメータID
msg-1199c1f9 = プラットフォーム用にキャッシュされたロゴトークンを使用中{ $res }
msg-889a7de5 = プラットフォームクラスが見つかりません{ $res }
msg-317f359c = プラットフォームに登録されたロゴトークン{ $res }
msg-323ec1e2 = プラットフォーム{ $res }ロゴファイルが見つかりません：{ $logo_file_path }
msg-bc6d0bcf = プラットフォームに必要なモジュールのインポートに失敗しました{ $res }翻訳するテキスト：{ $e }
msg-b02b538d = プラットフォームのファイルシステムエラー{ $res }ロゴ:{ $e }
msg-31123607 = プラットフォームのロゴ登録中に予期しないエラーが発生しました{ $res }翻訳するテキスト：{ $e }
msg-af06ccab = 設定ファイル{ $conf_id }存在しない
msg-082a5585 = プラグイン{ $plugin_name }存在しません
msg-ca334960 = プラグイン{ $plugin_name }登録設定なし

### astrbot/dashboard/routes/knowledge_base.py

msg-ce669289 = ドキュメントをアップロード{ $res }失敗しました：{ $e }
msg-87e99c2d = バックグラウンドアップロードタスク{ $task_id }失敗しました：{ $e }
msg-78b9c276 = { $res }
msg-d5355233 = ドキュメントをインポート{ $file_name }失敗：{ $e }
msg-5e7f1683 = 背景インポートタスク{ $task_id }失敗しました:{ $e }
msg-e1949850 = ナレッジベースリストの取得に失敗しました：{ $e }
msg-299af36d = ナレッジベース名は空にできません
msg-faf380ec = 不足しているパラメータ embedding_provider_id
msg-9015b689 = 埋め込みモデルが存在しないか、タイプが間違っています{ $res }翻訳対象テキスト：
msg-a63b3aa9 = 埋め込みベクトルの次元が一致しません、実際には{ $res }ただし、構成は{ $res_2 }
msg-9b281e88 = 埋め込みモデルのテストに失敗しました：{ $e }
msg-d3fb6072 = 並べ替えモデルが存在しません。
msg-fbec0dfd = 並べ替えモデルが異常な結果を返しました。
msg-872feec8 = テスト並べ替えモデルの失敗:{ $e }プラットフォームのログ出力を確認してください。
msg-a4ac0b9e = ナレッジベースの作成に失敗しました:{ $e }
msg-c8d487e9 = パラメータkb_idが不足しています
msg-978b3c73 = ナレッジベースが存在しません
msg-2137a3e6 = ナレッジベースの詳細の取得に失敗しました：{ $e }
msg-e7cf9cfd = 少なくとも1つの更新フィールドを指定する必要があります
msg-d3d82c22 = ナレッジベースの更新に失敗しました:{ $e }
msg-5d5d4090 = ナレッジベースの削除に失敗しました:{ $e }
msg-787a5dea = ナレッジベースの統計情報の取得に失敗しました:{ $e }
msg-97a2d918 = ドキュメントリストの取得に失敗しました：{ $e }
msg-b170e0fa = Content-Typeはmultipart/form-dataである必要があります
msg-5afbfa8e = ファイルが見つかりません
msg-6636fd31 = アップロードできるファイルは最大10個までです。
msg-975f06d7 = ドキュメントのアップロードに失敗しました：{ $e }
msg-35bacf60 = パラメータ文書の欠落または形式エラー
msg-6cc1edcd = 不正な文書形式です。file_nameとchunksを含める必要があります。
msg-376d7d5f = チャンクはリストである必要があります
msg-e7e2f311 = チャンクは空でない文字列のリストでなければなりません
msg-42315b8d = ドキュメントのインポートに失敗しました:{ $e }
msg-6906aa65 = タスクIDのパラメータが不足しています
msg-5ea3d72c = タスクが見つかりません
msg-194def99 = アップロード進捗の取得に失敗しました：{ $e }
msg-df6ec98e = Missing parameter doc_id
msg-7c3cfe22 = ドキュメントが存在しません
msg-b54ab822 = 文書詳細の取得に失敗しました:{ $e }
msg-0ef7f633 = ドキュメントの削除に失敗しました：{ $e }
msg-2fe40cbd = Missing parameter chunk_id
msg-fc13d42a = テキストブロックの削除に失敗しました:{ $e }
msg-4ef8315b = ブロックリストの取得に失敗しました:{ $e }
msg-b70a1816 = Missing parameter query
msg-82ee646e = パラメータkb_namesが不足しているか、形式が正しくありません
msg-07a61a9a = t-SNE可視化の生成に失敗しました：{ $e }
msg-20a3b3f7 = 検索に失敗しました：{ $e }
msg-1b76f5ab = Missing parameter url
msg-5dc86dc6 = URLからドキュメントをアップロードできませんでした:{ $e }
msg-890b3dee = バックグラウンドアップロードURLタスク{ $task_id }失敗：{ $e }

### astrbot/dashboard/routes/skills.py

msg-78b9c276 = { $res }
msg-1198c327 = デモモードではこの操作を実行することは許可されていません
msg-52430f2b = ファイルが見つかりません
msg-2ad598f3 = サポートされているのは .zip ファイルのみです
msg-a11f2e1c = 一時的なスキルファイルの削除に失敗しました:{ $temp_path }
msg-67367a6d = スキル名がありません

### astrbot/dashboard/routes/live_chat.py

msg-40f242d5 = [ライブチャット]{ $res }スタンプを話し始める{ $stamp }
msg-a168d76d = [ライブチャット]スタンプが一致しないか、発話状態ではありません。{ $stamp }vs{ $res }
msg-e01b2fea = [ライブチャット] 音声フレームデータなし
msg-33856925 = [ライブチャット] 音声ファイルが保存されました：{ $audio_path }, サイズ:{ $res }バイト
msg-9e9b7e59 = [ライブチャット] WAVファイルのアセンブルに失敗しました:{ $e }
msg-21430f56 = [ライブチャット] 一時ファイルが削除されました:{ $res }
msg-6b4f88bc = [Live Chat] 一時ファイルの削除に失敗しました：{ $e }
msg-0849d043 = [ライブチャット] WebSocket接続が確立されました：{ $username }
msg-5477338a = [ライブチャット] WebSocketエラー：{ $e }
msg-fdbfdba8 = [ライブチャット] WebSocket接続が閉じられました：{ $username }
msg-7be90ac0 = [ライブチャット] start_speaking スタンプが見つかりません
msg-8215062a = [ライブチャット] オーディオデータのデコードに失敗しました：{ $e }
msg-438980ea = [ライブチャット] end_speakingにスタンプがありません
msg-b35a375c = [ライブチャット] ユーザー割り込み：{ $res }
msg-2c3e7bbc = [ライブチャット] STTプロバイダーが設定されていません
msg-0582c8ba = [ライブチャット] STT認識結果が空です
msg-57c2b539 = [ライブチャット] STT結果:{ $user_text }
msg-6b7628c6 = [ライブチャット] ユーザー割り込みが検出されました
msg-2cab2269 = [ライブチャット] メッセージIDが一致しません：{ $result_message_id }等しくない{ $message_id }
msg-74c2470e = [ライブチャット] AgentStatsの解析に失敗しました：{ $e }
msg-4738a2b3 = [ライブチャット] TTSStatsの解析に失敗しました：{ $e }
msg-944d5022 = [ライブチャット] オーディオストリーム再生を開始中
msg-009104d8 = [ライブチャット] ボット応答完了：{ $bot_text }
msg-0c4c3051 = [ライブチャット] 音声処理に失敗しました：{ $e }
msg-140caa36 = [ライブチャット] 中断されたメッセージを保存：{ $interrupted_text }
msg-869f51ea = [ライブチャット] ユーザーメッセージ：{ $user_text }(session:{ $res }, ts:{ $timestamp }翻訳対象テキスト：
msg-d26dee52 = [ライブチャット] ボットメッセージ（中断）：{ $interrupted_text }(session:{ $res }, ts:{ $timestamp }翻訳するテキスト：
msg-1377f378 = [ライブチャット] メッセージの記録に失敗しました:{ $e }

### astrbot/dashboard/routes/log.py

msg-5bf500c1 = SSE再送信履歴のエラーをログに記録：{ $e }
msg-e4368397 = SSE接続エラーのログ:{ $e }
msg-547abccb = ログ履歴の取得に失敗しました:{ $e }
msg-cb5d4ebb = トレース設定の取得に失敗しました:{ $e }
msg-7564d3b0 = リクエストデータが空です
msg-d2a1cd76 = Trace設定の更新に失敗しました：{ $e }

### astrbot/dashboard/routes/conversation.py

msg-62392611 = データベースクエリエラー：{ $e }{ "\u000A" }{ $res }
msg-b21b052b = データベースクエリエラー：{ $e }
msg-10f72727 = { $error_msg }
msg-036e6190 = 会話リストの取得に失敗しました：{ $e }
msg-a16ba4b4 = 必須パラメータが不足しています：user_idとcid
msg-9a1fcec9 = 会話は存在しません
msg-73a8a217 = 会話の詳細の取得に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-976cd580 = 会話の詳細を取得できませんでした:{ $e }
msg-c193b9c4 = 会話情報の更新に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-9f96c4ee = 会話情報の更新に失敗しました：{ $e }
msg-e1cb0788 = バッチ削除中に会話パラメータを空にすることはできません。
msg-38e3c4ba = 会話の削除に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-ebf0371a = 会話の削除に失敗しました：{ $e }
msg-af54ee29 = 必須パラメータが不足しています: history
msg-b72552c8 = historyは有効なJSON文字列または配列でなければなりません
msg-fdf757f3 = 会話履歴の更新に失敗しました:{ $e }{ "\u000A" }{ $res }
msg-33762429 = 会話履歴の更新に失敗しました：{ $e }
msg-498f11f8 = エクスポートリストは空にできません
msg-98aa3644 = 会話のエクスポートに失敗しました: user_id={ $user_id }, cid={ $cid }, error={ $e }
msg-ed77aa37 = 会話のエクスポートが成功しませんでした。
msg-f07b18ee = 会話のバッチエクスポートに失敗しました:{ $e }{ "\u000A" }{ $res }
msg-85dc73fa = バッチ会話のエクスポートに失敗しました:{ $e }

### astrbot/dashboard/routes/cron.py

msg-fb5b419b = Cronマネージャーが初期化されていません
msg-78b9c276 = { $res }
msg-112659e5 = ジョブの一覧表示に失敗しました：{ $e }
msg-8bc87eb5 = 無効なペイロード
msg-29f616c2 = セッションが必要です
msg-ae7c99a4 = run_once=trueの場合、run_atは必須です。
msg-4bb8c206 = run_once=falseの場合、cron_expressionは必須です
msg-13fbf01e = run_atはISO日時でなければなりません
msg-da14d97a = ジョブ作成に失敗しました:{ $e }
msg-804b6412 = ジョブが見つかりません
msg-94b2248d = ジョブの更新に失敗しました:{ $e }
msg-42c0ee7a = ジョブの削除に失敗しました：{ $e }

### astrbot/dashboard/routes/tools.py

msg-78b9c276 = { $res }
msg-977490be = MCPサーバーリストの取得に失敗しました:{ $e }
msg-50a07403 = サーバー名は空にできません
msg-23d2bca3 = 有効なサーバー設定を提供する必要があります
msg-31252516 = サーバー{ $name }すでに存在します
msg-20b8309f = MCPサーバーを有効にする{ $name }タイムアウト
msg-fff3d0c7 = MCPサーバーを有効にする{ $name }失敗しました:{ $e }
msg-7f1f7921 = 設定の保存に失敗しました
msg-a7f06648 = MCPサーバーの追加に失敗しました:{ $e }
msg-278dc41b = サーバー{ $old_name }存在しない
msg-f0441f4b = MCPサーバーを有効にする前に無効にしてください{ $old_name }タイムアウト:{ $e }
msg-7c468a83 = 有効化する前にMCPサーバーを無効にしてください{ $old_name }失敗しました：{ $e }
msg-8a4c8128 = MCPサーバーを停止する{ $old_name }タイムアウト。
msg-9ac9b2fc = MCPサーバーを停止{ $old_name }失敗しました：{ $e }
msg-b988392d = MCPサーバーの更新に失敗しました:{ $e }
msg-c81030a7 = サーバー{ $name }存在しません
msg-4cdbd30d = MCPサーバーを無効化{ $name }タイムアウトしました。
msg-1ed9a96e = MCPサーバーの無効化{ $name }失敗しました：{ $e }
msg-a26f2c6a = MCPサーバーの削除に失敗しました:{ $e }
msg-bbc84cc5 = 無効なMCPサーバー設定
msg-aa0e3d0d = MCPサーバーの設定は空にできません
msg-d69cbcf2 = 一度に設定できるMCPサーバー構成は1つだけです。
msg-bd43f610 = MCP接続テスト失敗:{ $e }
msg-057a3970 = ツールリストの取得に失敗しました：{ $e }
msg-29415636 = 必須パラメータが不足しています：nameまたはaction
msg-75d85dc1 = ツールの有効化に失敗しました:{ $e }
msg-21a922b8 = ツール{ $tool_name }存在しないか、操作が失敗しました。
msg-20143f28 = 操作ツールが失敗しました：{ $e }
msg-295ab1fe = 不明:{ $provider_name }
msg-fe38e872 = 同期に失敗しました：{ $e }

### astrbot/dashboard/routes/chatui_project.py

msg-04827ead = 不足しているキー: title
msg-34fccfbb = 不足しているキー: project_id
msg-a7c08aee = プロジェクト{ $project_id }見つかりません
msg-c52a1454 = 許可が拒否されました
msg-dbf41bfc = Missing key: session_id
msg-d922dfa3 = セッション{ $session_id }見つかりません

### astrbot/dashboard/routes/open_api.py

msg-e41d65d5 = チャットセッション %s の作成に失敗しました: %s
msg-fc15cbcd = { $username_err }
msg-bc3b3977 = 無効なユーザー名
msg-2cd6e70f = { $ensure_session_err }
msg-53632573 = { $resolve_err }
msg-79b0c7cb = %sのチャット設定ルートを%sで更新できませんでした: %s
msg-7c7a9f55 = チャット設定ルートの更新に失敗しました：{ $e }
msg-74bff366 = pageとpage_sizeは整数でなければなりません
msg-1507569c = メッセージが空です
msg-1389e46a = messageは文字列またはリストでなければなりません
msg-697561eb = メッセージ部分はオブジェクトでなければなりません
msg-2c4bf283 = 返信部分にmessage_idがありません
msg-60ddb927 = サポートされていないメッセージパーツの種類：{ $part_type }
msg-cf310369 = 添付ファイルが見つかりません:{ $attachment_id }
msg-58e0b84a = { $part_type }添付ファイルIDがありません
msg-e565c4b5 = ファイルが見つかりません。{ $file_path }
msg-c6ec40ff = メッセージの内容が空です（返信のみは許可されていません）
msg-2b00f931 = Missing key: message
msg-a29d9adb = 欠落しているキー: umo
msg-4990e908 = 無効なumo:{ $e }
msg-45ac857c = Bot not found or not running for platform:{ $platform_id }
msg-ec0f0bd2 = Open API send_message 失敗:{ $e }
msg-d04109ab = メッセージ送信に失敗しました：{ $e }

### astrbot/dashboard/routes/session_management.py

msg-e1949850 = ナレッジベースリストの取得に失敗しました:{ $e }
msg-3cd6eb8c = ルールリストの取得に失敗しました:{ $e }
msg-363174ae = 必須パラメータが不足しています: umo
msg-809e51d7 = 必須パラメータが不足しています：rule_key
msg-ce203e7e = サポートされていないルールキー:{ $rule_key }
msg-2726ab30 = 会話ルールの更新に失敗しました:{ $e }
msg-f021f9fb = セッションルールの削除に失敗しました：{ $e }
msg-6bfa1fe5 = 必須パラメータが不足しています: umos
msg-4ce0379e = パラメータ umos は配列でなければなりません。
msg-979c6e2f = umoを削除{ $umo }ルールが失敗しました:{ $e }
msg-77d2761d = セッションルールの一括削除に失敗しました：{ $e }
msg-6619322c = UMOリストの取得に失敗しました：{ $e }
msg-b944697c = セッションステータスリストの取得に失敗しました：{ $e }
msg-adba3c3b = 変更するステータスを少なくとも1つ指定する必要があります。
msg-4a8eb7a6 = グループIDを指定してください
msg-67f15ab7 = グループ{ $group_id }存在しません
msg-50fbcccb = 一致する会話が見つかりません
msg-59714ede = アップデート{ $umo }サービスステータスが失敗しました：{ $e }
msg-31640917 = バッチ更新サービスのステータスが失敗しました：{ $e }
msg-4d83eb92 = 必須パラメータが不足しています: provider_type、provider_id
msg-5f333041 = サポートされていないプロバイダータイプ:{ $provider_type }
msg-6fa017d7 = 更新{ $umo }プロバイダーが失敗しました:{ $e }
msg-07416020 = プロバイダーの一括更新に失敗しました：{ $e }
msg-94c745e6 = グループリストの取得に失敗しました：{ $e }
msg-fb7cf353 = グループ名は空にできません
msg-ae3fce8a = グループの作成に失敗しました:{ $e }
msg-07de5ff3 = グループIDは空にできません
msg-35b8a74f = グループの更新に失敗しました:{ $e }
msg-3d41a6fd = グループの削除に失敗しました：{ $e }

### astrbot/dashboard/routes/persona.py

msg-4a12aead = パーソナリティリストの取得に失敗しました:{ $e }{ "\u000A" }{ $res }
msg-c168407f = パーソナリティリストの取得に失敗しました：{ $e }
msg-63c6f414 = 必須パラメータが不足しています：persona_id
msg-ce7da6f3 = パーソナリティは存在しない
msg-9c07774d = パーソナリティ詳細の取得に失敗しました:{ $e }{ "\u000A" }{ $res }
msg-ee3b44ad = パーソナリティ詳細の取得に失敗しました:{ $e }
msg-ad455c14 = Personality IDは空にできません
msg-43037094 = システムプロンプトは空にできません
msg-ec9dda44 = プリセットダイアログの数は偶数（ユーザーとアシスタントが交互になるように）でなければなりません。
msg-26b214d5 = ペルソナの作成に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-8913dfe6 = パーソナリティの作成に失敗しました：{ $e }
msg-3d94d18d = Failed to update persona:{ $e }{ "\u000A" }{ $res }
msg-f2cdfbb8 = パーソナリティの更新に失敗しました。{ $e }
msg-51d84afc = ペルソナの削除に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-8314a263 = ペルソナの削除に失敗しました：{ $e }
msg-b8ecb8f9 = パーソナリティの移動に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-ab0420e3 = ペルソナの移動に失敗しました：{ $e }
msg-e5604a24 = フォルダリストの取得に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-4d7c7f4a = フォルダリストの取得に失敗しました：{ $e }
msg-cf0ee4aa = フォルダーツリーの取得に失敗しました:{ $e }{ "\u000A" }{ $res }
msg-bb515af0 = フォルダーツリーの取得に失敗しました：{ $e }
msg-c92b4863 = 必須パラメータが不足しています: folder_id
msg-77cdd6fa = フォルダが存在しません
msg-2d34652f = フォルダーの詳細の取得に失敗しました:{ $e }{ "\u000A" }{ $res }
msg-650ef096 = フォルダ詳細の取得に失敗しました：{ $e }
msg-27c413df = フォルダ名を空にすることはできません
msg-b5866931 = フォルダの作成に失敗しました:{ $e }{ "\u000A" }{ $res }
msg-5e57f3b5 = フォルダーの作成に失敗しました:{ $e }
msg-9bd8f820 = フォルダーの更新に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-1eada044 = フォルダーの更新に失敗しました：{ $e }
msg-9cef0256 = フォルダの削除に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-22020727 = フォルダの削除に失敗しました：{ $e }
msg-7a69fe08 = アイテムは空にできません
msg-e71ba5c2 = 各項目には、id、type、およびsort_orderフィールドを含める必要があります。
msg-dfeb8320 = タイプフィールドは「persona」または「folder」である必要があります
msg-aec43ed3 = 並べ替えの更新に失敗しました：{ $e }{ "\u000A" }{ $res }
msg-75ec4427 = ソートの更新に失敗しました：{ $e }

### astrbot/dashboard/routes/platform.py

msg-bcc64513 = Webhook UUIDが見つかりません{ $webhook_uuid }プラットフォーム
msg-1478800f = 対応するプラットフォームが見つかりません
msg-378cb077 = プラットフォーム{ $res }webhook_callbackメソッドは実装されていません
msg-2d797305 = プラットフォームは統合Webhookモードをサポートしていません
msg-83f8dedf = Webhookコールバックの処理中にエラーが発生しました：{ $e }
msg-af91bc78 = コールバック処理に失敗しました
msg-136a952f = プラットフォーム統計の取得に失敗しました:{ $e }
msg-60bb0722 = 統計情報の取得に失敗しました:{ $e }

### astrbot/dashboard/routes/api_key.py

msg-8e0249fa = 少なくとも1つの有効なスコープが必要です
msg-1b79360d = 無効なスコープ
msg-d6621696 = expires_in_days は整数でなければなりません
msg-33605d95 = expires_in_days は 0 より大きくなければなりません
msg-209030fe = キーがありません: key_id
msg-24513a81 = APIキーが見つかりません

### astrbot/dashboard/routes/file.py

msg-78b9c276 = { $res }

### astrbot/dashboard/routes/chat.py

msg-a4a521ff = キーが不足しています：ファイル名
msg-c9746528 = 無効なファイルパス
msg-3c2f6dee = ファイルアクセスエラー
msg-e5b19b36 = 不足しているキー: attachment_id
msg-cfa38c4d = 添付ファイルが見つかりません
msg-377a7406 = 欠落キー: ファイル
msg-bae87336 = 添付ファイルの作成に失敗しました
msg-5c531303 = JSONボディがありません
msg-1c3efd8f = 欠落キー: メッセージまたはファイル
msg-04588d0f = Missing key: session_id または conversation_id
msg-c6ec40ff = メッセージの内容が空です（返信のみは許可されていません）
msg-2c3fdeb9 = メッセージが両方とも空です
msg-9bc95e22 = セッションIDが空です
msg-344a401b = [WebChat] ユーザー{ $username }チャットの長い接続を切断します。
msg-6b54abec = WebChatストリームエラー：{ $e }
msg-53509ecb = WebChatストリームメッセージID不一致
msg-1211e857 = [WebChat] ユーザー{ $username }チャットの長い接続を切断します。{ $e }
msg-be34e848 = ウェブ検索参照の抽出に失敗しました:{ $e }
msg-80bbd0ff = WebChatストリームの予期しないエラー：{ $e }
msg-dbf41bfc = 欠落キー：session_id
msg-d922dfa3 = セッション{ $session_id }見つかりません
msg-c52a1454 = 許可が拒否されました
msg-9d7a8094 = セッションクリーンアップ中にUMOルート %s の削除に失敗しました: %s
msg-44c45099 = 添付ファイルの削除に失敗しました{ $res }翻訳するテキスト：{ $e }
msg-f033d8ea = 添付ファイルの取得に失敗しました:{ $e }
msg-e6f655bd = 添付ファイルの削除に失敗しました：{ $e }
msg-a6ef3b67 = 欠落したキー: display_name

### astrbot/dashboard/routes/t2i.py

msg-76cc0933 = アクティブテンプレート取得エラー
msg-5350f35b = テンプレートが見つかりません
msg-d7b101c5 = 名前と内容は必須です。
msg-e910b6f3 = この名前のテンプレートは既に存在します。
msg-18cfb637 = コンテンツは必須です。
msg-2480cf2f = テンプレートが見つかりません。
msg-9fe026f1 = テンプレート名を空にすることはできません。
msg-eeefe1dc = テンプレート '{ $name }存在しないため、適用できません。
msg-0048e060 = set_active_templateでのエラー
msg-8fde62dd = デフォルトテンプレートのリセット中にエラーが発生しました

### astrbot/dashboard/routes/stat.py

msg-1198c327 = デモモードではこの操作は許可されていません。
msg-78b9c276 = { $res }
msg-0e5bb0b1 = proxy_urlは必須です
msg-f0e0983e = 失敗しました。ステータスコード：{ $res }
msg-68e65093 = エラー：{ $e }
msg-b5979fe8 = バージョンパラメータは必須です
msg-b88a1887 = 無効なバージョン形式
msg-8cb9bb6b = パストラバーサル試行が検出されました：{ $version }->{ $changelog_path }
msg-7616304c = バージョンの変更履歴{ $version }見つかりません

### astrbot/dashboard/routes/plugin.py

msg-1198c327 = デモモードではこの操作は許可されていません
msg-adce8d2f = プラグインディレクトリ名がありません
msg-2f1b67fd = オーバーロードに失敗しました:{ $err }
msg-71f9ea23 = /api/plugin/reload-failed:{ $res }
msg-27286c23 = /api/plugin/reload:{ $res }
msg-b33c0d61 = キャッシュのMD5が一致しているため、キャッシュされたプラグインマーケットプレースデータを使用しています。
msg-64b4a44c = リモートプラグインマーケットデータが空です：{ $url }
msg-fdbffdca = リモートプラグインマーケットデータを正常に取得しました。含まれる内容：{ $res }プラグイン
msg-48c42bf8 = リクエスト{ $url }失敗しました、ステータスコード:{ $res }
msg-6ac25100 = リクエスト{ $url }失敗しました、エラー:{ $e }
msg-7e536821 = リモートプラグインマーケットデータの取得に失敗しました。キャッシュデータを使用します。
msg-d4b4c53a = プラグインリストの取得に失敗し、キャッシュされたデータは利用できません
msg-37f59b88 = キャッシュMD5の読み込みに失敗しました。{ $e }
msg-8048aa4c = リモートMD5の取得に失敗しました:{ $e }
msg-593eacfd = キャッシュファイルにはMD5情報が含まれていません。
msg-dedcd957 = リモートMD5の取得に失敗しました、キャッシュを使用します
msg-21d7e754 = プラグインデータのMD5：ローカル={ $cached_md5 }, Remote={ $remote_md5 }, valid={ $is_valid }
msg-0faf4275 = キャッシュの有効性チェックに失敗しました：{ $e }
msg-e26aa0a5 = キャッシュファイルを読み込み中:{ $cache_file }, キャッシュ時間:{ $res }
msg-23d627a1 = プラグインマーケットプレイスのキャッシュの読み込みに失敗しました：{ $e }
msg-22d12569 = プラグインマーケットデータがキャッシュされました:{ $cache_file }, MD5:{ $md5 }
msg-478c99a9 = プラグイン市場のキャッシュの保存に失敗しました：{ $e }
msg-3838d540 = プラグインのロゴを取得できませんでした：{ $e }
msg-da442310 = プラグインのインストール{ $repo_url }
msg-e0abd541 = プラグインをインストール{ $repo_url }成功しました。
msg-78b9c276 = { $res }
msg-acfcd91e = ユーザーアップロードプラグインのインストール{ $res }
msg-48e05870 = プラグインのインストール{ $res }成功
msg-8af56756 = プラグインをアンインストール中{ $plugin_name }
msg-6d1235b6 = プラグインをアンインストール{ $plugin_name }成功
msg-7055316c = プラグインを更新中{ $plugin_name }
msg-d258c060 = プラグインを更新{ $plugin_name }成功。
msg-398370d5 = /api/plugin/update:{ $res }
msg-2d225636 = プラグインリストを空にすることはできません
msg-32632e67 = バッチアップデートプラグイン{ $name }
msg-08dd341c = /api/plugin/update-all: プラグインを更新する{ $name }失敗しました：{ $res }
msg-cb230226 = プラグインを無効化する{ $plugin_name }翻訳対象テキスト：
msg-abc710cd = /api/plugin/off:{ $res }
msg-06e2a068 = プラグインを有効にする{ $plugin_name }.
msg-82c412e7 = /api/plugin/on:{ $res }
msg-77e5d67e = プラグインを取得中です{ $plugin_name }READMEファイルの内容
msg-baed1b72 = プラグイン名が空です
msg-773cca0a = プラグイン名は空にできません
msg-082a5585 = プラグイン{ $plugin_name }存在しません
msg-ba106e58 = プラグイン{ $plugin_name }ディレクトリが存在しません
msg-e38e4370 = プラグインディレクトリが見つかりません：{ $plugin_dir }
msg-df027f16 = プラグインが見つかりません{ $plugin_name }ディレクトリ
msg-5f304f4b = プラグイン{ $plugin_name }READMEファイルがありません
msg-a3ed8739 = /api/plugin/readme:{ $res }
msg-2f9e2c11 = READMEファイルの読み込みに失敗しました：{ $e }
msg-dcbd593f = プラグインを取得中{ $plugin_name }更新ログ
msg-ea5482da = /api/plugin/changelog:{ $res }
msg-8e27362e = 変更ログの読み込みに失敗しました:{ $e }
msg-0842bf8b = プラグイン{ $plugin_name }変更履歴ファイルがありません
msg-8e36313d = ソースフィールドはリストである必要があります
msg-643e51e7 = /api/plugin/source/save:{ $res }

### astrbot/builtin_stars/session_controller/main.py

msg-b48bf3fe = LLM応答が失敗しました:{ $e }

### astrbot/builtin_stars/builtin_commands/commands/setunset.py

msg-8b56b437 = セッション{ $uid }変数{ $key }ストレージが正常に保存されました。解除には /unset を使用してください。
msg-dfd31d9d = そのような変数名は存在しません。形式: /unset 変数名。
msg-bf181241 = セッション{ $uid }変数{ $key }正常に削除されました。

### astrbot/builtin_stars/builtin_commands/commands/provider.py

msg-b435fcdc = プロバイダー到達可能性チェックが失敗しました：id=%s type=%s code=%s reason=%s
msg-f4cfd3ab = プロバイダ到達性テストを実行中、お待ちください...
msg-ed8dcc22 = { $ret }
msg-f3d8988e = シリアル番号を入力してください。
msg-284759bb = 無効なプロバイダー番号です。
msg-092d9956 = 正常に切り替えました{ $id_ }翻訳するテキスト：
msg-bf9eb668 = 無効なパラメータです。
msg-4cdd042d = LLMプロバイダーが見つかりません。まず設定を行ってください。
msg-cb218e86 = モデルのシリアル番号エラー。
msg-1756f199 = モデルの切り替えが正常に完了しました。現在のプロバイダー: [{ $res }現在のモデル: [{ $res_2 }翻訳対象テキスト：
msg-4d4f587f = モデルを切り替える{ $res }.
msg-584ca956 = キーシーケンス番号が正しくありません。
msg-f52481b8 = スイッチキー不明エラー：{ $e }
msg-7a156524 = 鍵切り替えに成功しました。

### astrbot/builtin_stars/builtin_commands/commands/conversation.py

msg-63fe9607 = イン{ $res }このシナリオでは、リセットコマンドには管理者権限が必要です。あなた（ID{ $res_2 }) 管理者ではありません。この操作を実行できません。
msg-6f4bbe27 = 会話が正常にリセットされました。
msg-4cdd042d = LLMプロバイダが見つかりません。まず設定してください。
msg-69ed45be = 現在は会話状態ではありません。 /switch で切り替えるか、/new で新規作成してください。
msg-ed8dcc22 = { $ret }
msg-772ec1fa = 停止要求{ $stopped_count }実行中のタスク。
msg-8d42cd8a = このセッションでは現在実行中のタスクはありません。
msg-efdfbe3e = { $THIRD_PARTY_AGENT_RUNNER_STR }会話リスト機能は現在サポートされていません。
msg-492c2c02 = 新しい会話が作成されました。
msg-c7dc838d = 新しい会話に切り替える: 新しい会話{ $res })。
msg-6da01230 = グループチャット{ $session }新しいチャットに切り替えました: 新規チャット{ $res }）。
msg-f356d65a = グループチャットIDを入力してください。 /groupnew グループチャットID。
msg-7e442185 = タイプエラー、数値の会話番号を入力してください。
msg-00dbe29c = 会話番号を入力。 /会話番号を切り替え。 /ls 会話を表示 /new 会話を作成
msg-a848ccf6 = ダイアログシリアル番号エラー、/lsを使用して表示してください。
msg-1ec33cf6 = 会話に切り替える：{ $title }翻訳するテキスト：{ $res })。
msg-68e5dd6c = 新しい会話名を入力してください。
msg-c8dd6158 = 会話名が正常に変更されました。
msg-1f1fa2f2 = セッションはグループチャット内にあり、独立セッションが有効化されておらず、あなた（ID{ $res }) は管理者ではないため、現在の会話を削除する権限がありません。
msg-6a1dc4b7 = 現在は会話状態ではありません、/switch number で切り替えるか、/new で作成してください。

### astrbot/builtin_stars/builtin_commands/commands/tts.py

msg-ef1b2145 = { $status_text }現在のセッションのテキスト読み上げ。ただし、TTS機能は設定で有効になっていません。WebUIで有効にしてください。
msg-deee9deb = { $status_text }現在のセッションのためのテキスト読み上げ機能。

### astrbot/builtin_stars/builtin_commands/commands/llm.py

msg-72cd5f57 = { $status }LLMチャット機能。

### astrbot/builtin_stars/builtin_commands/commands/persona.py

msg-4f52d0dd = 現在の会話は存在しません。最初に /new を使用して新しい会話を作成してください。
msg-e092b97c = [Persona]{ "\u000A" }{ "\u000A" }- ペルソナシナリオリスト：`/persona list`{ "\u000A" }- 人格シナリオ設定: `/persona personality`{ "\u000A" }- ペルソナシナリオ詳細: `/persona view persona`{ "\u000A" }- ペルソナをキャンセル: `/persona unset`{ "\u000A" }{ "\u000A" }デフォルトのパーソナリティシナリオ:{ $res }{ "\u000A" }現在の会話{ $curr_cid_title }人格シナリオ:{ $curr_persona_name }{ "\u000A" }{ "\u000A" }ペルソナシナリオを設定するには、管理パネルの設定ページに移動してください。{ "\u000A" }
msg-c046b6e4 = { $msg }
msg-99139ef8 = 人格シナリオ名を入力してください
msg-a44c7ec0 = 現在、会話はありません、ペルソナをキャンセルできません。
msg-a90c75d4 = パーソナリティの取り消しが成功しました。
msg-a712d71a = 現在、会話はありません。まず会話を開始するか、/new を使用して新しい会話を作成してください。
msg-4e4e746d = 設定に成功しました。別のペルソナに切り替える場合は、元のペルソナの会話が現在のペルソナに影響を与えないように、コンテキストをクリアするために /reset を使用してください。{ $force_warn_msg }
msg-ab60a2e7 = ペルソナシナリオは存在しません。すべてを表示するには /persona list を使用してください。

### astrbot/builtin_stars/builtin_commands/commands/t2i.py

msg-855d5cf3 = テキストから画像へのモードが無効化されました。
msg-64da24f4 = テキストから画像モードが有効になっています。

### astrbot/builtin_stars/builtin_commands/commands/admin.py

msg-ad019976 = 使用方法: /op <id> で管理者を承認; /deop <id> で管理者権限を削除。IDを取得するには /sid を使用してください。
msg-1235330f = 認証に成功しました。
msg-e78847e0 = 使用方法: /deop <id> で管理者権限を削除します。IDは /sid で確認できます。
msg-012152c1 = 認可が正常にキャンセルされました。
msg-5e076026 = このユーザーIDは管理者リストに含まれていません。
msg-7f8eedde = 使用方法: /wl <id> でホワイトリストに追加; /dwl <id> でホワイトリストから削除。 /sid で自分のIDを取得できます。
msg-de1b0a87 = ホワイトリストが正常に追加されました。
msg-59d6fcbe = 使用方法: /dwl <id> を実行してホワイトリストから削除します。IDを取得するには /sid を使用してください。
msg-4638580f = ホワイトリストの削除に成功しました。
msg-278fb868 = このSIDはホワイトリストに含まれていません。
msg-1dee5007 = 管理パネルの更新を試みています...
msg-76bea66c = 管理パネルの更新が完了しました。

### astrbot/builtin_stars/builtin_commands/commands/sid.py

msg-ed8dcc22 = { $ret }

### astrbot/builtin_stars/builtin_commands/commands/plugin.py

msg-9cae24f5 = { $plugin_list_info }
msg-3f3a6087 = デモモードではプラグインを無効にできません。
msg-90e17cd4 = /plugin off <plugin name> プラグインを無効化します。
msg-d29d6d57 = プラグイン{ $plugin_name }無効。
msg-f90bbe20 = デモモードではプラグインを有効にできません。
msg-b897048f = /plugin on <plugin名> プラグインを有効にします。
msg-ebfb93bb = プラグイン{ $plugin_name }有効。
msg-9cd74a8d = デモモードではプラグインをインストールできません。
msg-d79ad78d = /plugin get <plugin repository address> install plugin
msg-4f293fe1 = フェッチ準備中{ $plugin_repo }プラグインをインストールします。
msg-d40e7065 = プラグインが正常にインストールされました。
msg-feff82c6 = プラグインのインストールに失敗しました:{ $e }
msg-5bfe9d3d = プラグイン情報を表示するには /plugin help <plugin名> を使用してください。
msg-02627a9b = プラグインが見つかりません。
msg-ed8dcc22 = { $ret }

### astrbot/builtin_stars/builtin_commands/commands/help.py

msg-c046b6e4 = { $msg }

### astrbot/builtin_stars/builtin_commands/commands/alter_cmd.py

msg-d7a36c19 = このコマンドは、コマンドまたはコマンドグループの権限を設定するために使用されます。{ "\u000A" }フォーマット: /alter_cmd <コマンド名> <admin/member>{ "\u000A" }例1: /alter_cmd c1 admin はc1を管理者コマンドとして設定します{ "\u000A" }例2: /alter_cmd g1 c1 admin は、g1コマンドグループのc1サブコマンドを管理者コマンドに設定します。{ "\u000A" }/alter_cmd reset config opens reset permission configuration
msg-afe0fa58 = { $config_menu }
msg-0c85d498 = シーン番号と権限タイプは空にできません
msg-4e0afcd1 = シーン番号は1から3の間の数字でなければなりません
msg-830d6eb8 = 権限タイプエラー、管理者またはメンバーである必要があります
msg-d1180ead = リセットコマンドが実行されました{ $res }シナリオに設定された権限{ $perm_type }
msg-8d9bc364 = コマンドタイプエラー、利用可能なタイプは admin、member です。
msg-1f2f65e0 = コマンドが見つかりませんでした
msg-cd271581 = 「に変更されました。{ $cmd_name }翻訳対象テキスト:{ $cmd_group_str }権限レベルが調整されました{ $cmd_type }.

### astrbot/builtin_stars/web_searcher/main.py

msg-7f5fd92b = 従来のwebsearch_tavily_key（文字列形式）を検出しました。自動的にリスト形式に移行して保存しました。
msg-bed9def5 = web_searcher - ウェブスクレイピング:{ $res }翻訳対象テキスト：{ $res_2 }
msg-8214760c = Bing検索エラー：{ $e }次を試してみてください...
msg-8676b5aa = Bing検索に失敗しました
msg-3fb6d6ad = SOGO検索エラー:{ $e }
msg-fe9b336f = sogo検索に失敗しました
msg-c991b022 = エラー: AstrBotでTavily APIキーが設定されていません。
msg-b4fbb4a9 = Tavilyウェブ検索が失敗しました：{ $reason }、ステータス:{ $res }
msg-6769aba9 = エラー: Tavilyウェブ検索ツールが結果を返しませんでした。
msg-b4e7334e = このコマンドは非推奨となりました。WebUIでウェブ検索機能を有効または無効にしてください。
msg-b1877974 = web_searcher - search_from_search_engine:{ $query }
msg-2360df6b = 検索結果の処理中にエラーが発生しました：{ $processed_result }
msg-359d0443 = エラー: AstrBotでBaidu AI Search APIキーが設定されていません。
msg-94351632 = Baidu AI Search MCPサーバーの初期化に成功しました。
msg-5a7207c1 = web_searcher - search_from_tavily:{ $query }
msg-b36134c9 = エラー：AstrBotでTavily APIキーが設定されていません。
msg-98ed69f4 = エラー: urlは空でない文字列でなければなりません。
msg-51edd9ee = エラー：AstrBotでBoCha APIキーが設定されていません。
msg-73964067 = BoChaウェブ検索が失敗しました:{ $reason }ステータス:{ $res }
msg-34417720 = web_searcher - search_from_bocha:{ $query }
msg-b798883b = エラー：AstrBotにBoCha APIキーが設定されていません。
msg-22993708 = 百度AI検索MCPツールを取得できません。
msg-6f8d62a4 = Baidu AI Search MCPサーバーを初期化できません：{ $e }

### astrbot/builtin_stars/web_searcher/engines/bing.py

msg-e3b4d1e9 = Bing検索に失敗しました

### astrbot/builtin_stars/astrbot/main.py

msg-3df554a1 = チャット機能強化エラー:{ $e }
msg-5bdf8f5c = { $e }
msg-bb6ff036 = LLMプロバイダーが見つかりません。まず設定してください。能動的に返信できません。
msg-afa050be = 現在は会話状態ではありませんので、アクティブに返信することはできません。プラットフォーム設定->セッション分離(unique_session)が有効になっていないことを確認し、/switch 番号で切り替えるか、/new で新しいセッションを作成してください。
msg-9a6a6b2e = 会話が見つかりません、返信を開始できません。
msg-78b9c276 = { $res }
msg-b177e640 = アクティブ応答が失敗しました：{ $e }
msg-24d2f380 = ltm:{ $e }

### astrbot/builtin_stars/astrbot/long_term_memory.py

msg-5bdf8f5c = { $e }
msg-8e11fa57 = IDが見つかりません{ $image_caption_provider_id }プロバイダー
msg-8ebaa397 = プロバイダータイプエラー{ $res })、画像の説明を取得できません
msg-30954f77 = 画像URLが空です
msg-62de0c3e = 画像の説明を取得できませんでした:{ $e }
msg-d0647999 = ltm |{ $res }翻訳対象のテキスト：|{ $final_message }
msg-133c1f1d = 記録されたAI応答：{ $res }翻訳対象のテキスト：{ $final_message }

### astrbot/i18n/ftl_translate.py

msg-547c9cc5 = 環境変数DEEPSEEK_API_KEYが検出されませんでした。最初に設定してください。
msg-8654e4be = { "\u000A" }[エラー] API呼び出しに失敗しました：{ $e }
msg-75f207ed = ファイルが見つかりません:{ $ftl_path }
msg-dcfbbe82 = メッセージが見つかりません{ $ftl_path }
msg-ccd5a28f = 合計{ $res }テキスト、使用{ $max_workers }同時スレッド翻訳中...
msg-00b24d69 = { "\u000A" }[エラー] 翻訳に失敗しました、原文が保持されました：{ $e }
msg-ebcdd595 = { "\u000A" }翻訳完了、保存先：{ $ftl_path }
msg-d6c66497 = エラー：最初にDEEPSEEK_API_KEY環境変数を設定してください。
msg-09486085 = 例：export DEEPSEEK_API_KEY='sk-xxxxxx'

### scripts/generate_changelog.py

msg-a79937ef = 警告：openaiパッケージがインストールされていません。インストールするには：pip install openai
msg-090bfd36 = 警告：LLM APIの呼び出しに失敗しました：{ $e }
msg-a3ac9130 = シンプルな変更履歴生成にフォールバックしています...
msg-6f1011c5 = 最新タグ:{ $latest_tag }
msg-8c7f64d7 = エラー: リポジトリ内にタグが見つかりません
msg-a89fa0eb = {$var}以降のコミットは見つかりませんでした{ $latest_tag }
msg-846ebecf = 見つかりました{ $res }コミット数{ $latest_tag }
msg-9ad686af = 警告：タグからバージョンを解析できませんでした{ $latest_tag }
msg-f5d43a54 = 変更ログを生成中{ $version }...
msg-e54756e8 = { "\u000A" }✓ 変更履歴を生成しました:{ $changelog_file }
msg-82be6c98 = { "\u000A" }プレビュー:
msg-321ac5b1 = { $changelog_content }
