"""Translations for built-in LLM request failures."""

LLM_ERROR_MESSAGES = {
    "zh-CN": {
        "invalidSessionProviderType": "该会话来源的对话模型（提供商）的类型不正确: {provider_type}",
        "noProvider": "LLM 请求失败：未找到任何可用的对话模型（提供商）。请先在 WebUI 中配置并启用可用模型。",
        "providerNotFound": "LLM 请求失败：未找到指定的提供商 `{provider}`。请检查提供商配置或重新选择可用模型。",
        "invalidProviderType": "LLM 请求失败：选择的提供商类型无效（{provider_type}），已跳过本次请求。",
        "requestFailed": "LLM 请求失败：{detail}",
        "blockedProvider": "LLM 请求失败：Provider API base `{api_base}` 因安全原因被拦截，请更换可用的 AI 提供商。",
    },
    "en-US": {
        "invalidSessionProviderType": "The chat model (provider) for this session has an invalid type: {provider_type}",
        "noProvider": "LLM request failed: No available chat model (provider) was found. Configure and enable a model in WebUI first.",
        "providerNotFound": "LLM request failed: Provider `{provider}` was not found. Check the provider configuration or select an available model.",
        "invalidProviderType": "LLM request failed: The selected provider type ({provider_type}) is invalid. This request was skipped.",
        "requestFailed": "LLM request failed: {detail}",
        "blockedProvider": "LLM request failed: Provider API base `{api_base}` was blocked for security reasons. Use another AI provider.",
    },
    "ru-RU": {
        "invalidSessionProviderType": "Модель чата (провайдер) для этой сессии имеет недопустимый тип: {provider_type}",
        "noProvider": "Ошибка запроса к LLM: доступная модель чата (провайдер) не найдена. Сначала настройте и включите модель в WebUI.",
        "providerNotFound": "Ошибка запроса к LLM: провайдер `{provider}` не найден. Проверьте настройки провайдера или выберите доступную модель.",
        "invalidProviderType": "Ошибка запроса к LLM: выбран недопустимый тип провайдера ({provider_type}). Запрос пропущен.",
        "requestFailed": "Ошибка запроса к LLM: {detail}",
        "blockedProvider": "Ошибка запроса к LLM: базовый URL API провайдера `{api_base}` заблокирован по соображениям безопасности. Используйте другого провайдера ИИ.",
    },
    "ja-JP": {
        "invalidSessionProviderType": "このセッションのチャットモデル（プロバイダー）の種類が無効です: {provider_type}",
        "noProvider": "LLM リクエストに失敗しました：利用可能なチャットモデル（プロバイダー）が見つかりません。先に WebUI でモデルを設定し、有効にしてください。",
        "providerNotFound": "LLM リクエストに失敗しました：プロバイダー `{provider}` が見つかりません。プロバイダー設定を確認するか、利用可能なモデルを選択してください。",
        "invalidProviderType": "LLM リクエストに失敗しました：選択されたプロバイダーの種類（{provider_type}）が無効なため、このリクエストはスキップされました。",
        "requestFailed": "LLM リクエストに失敗しました：{detail}",
        "blockedProvider": "LLM リクエストに失敗しました：プロバイダーの API ベース URL `{api_base}` はセキュリティ上の理由でブロックされました。別の AI プロバイダーを使用してください。",
    },
}
