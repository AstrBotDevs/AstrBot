/**
 * 提供商相关的工具函数
 */

/**
 * 获取提供商类型对应的图标
 * @param {string} type - 提供商类型
 * @returns {string} 图标 URL
 */
export function getProviderIcon(type) {
  const icons = {
    'openai': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/openai.svg',
    'azure': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/azure.svg',
    'xai': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/xai.svg',
    'anthropic': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/anthropic.svg',
    'ollama': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/ollama.svg',
    'google': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/gemini-color.svg',
    'deepseek': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/deepseek.svg',
    'modelscope': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/modelscope.svg',
    'zhipu': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/zhipu.svg',
    'nvidia': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/nvidia-color.svg',
    'siliconflow': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/siliconcloud.svg',
    'moonshot': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/kimi.svg',
    'kimi': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/kimi.svg',
    'kimi-code': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/kimi.svg',
    'ppio': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/ppio.svg',
    'dify': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/dify-color.svg',
    "coze": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.66.0/icons/coze.svg",
    'dashscope': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/alibabacloud-color.svg',
    'deerflow': 'https://cdn.jsdelivr.net/gh/bytedance/deer-flow@main/frontend/public/images/deer.svg',
    'fastgpt': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/fastgpt-color.svg',
    'lm_studio': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/lmstudio.svg',
    'fishaudio': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/fishaudio.svg',
    'minimax': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/minimax.svg',
    'mimo': 'https://platform.xiaomimimo.com/favicon.874c9507.png',
    '302ai': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.53.0/icons/ai302-color.svg',
    'microsoft': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/microsoft.svg',
    'vllm': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/vllm.svg',
    'groq': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/groq.svg',
    'aihubmix': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/aihubmix-color.svg',
    'openrouter': 'https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@latest/icons/openrouter.svg',
    "tokenpony": "https://tokenpony.cn/tokenpony-web/logo.png",
    "compshare": "https://compshare.cn/favicon.ico"
  };
  return icons[type] || '';
}

/**
 * 获取提供商简介
 * @param {Object} template - 模板对象
 * @param {string} name - 提供商名称
 * @param {Function} tm - 翻译函数
 * @returns {string} 提供商描述
 */
export function getProviderDescription(template, name, tm) {
  if (name === 'OpenAI') {
    return tm('providers.description.openai', { type: template.type });
  } else if (template.provider === 'kimi-code') {
    return tm('providers.description.kimi_code');
  } else if (name === 'vLLM Rerank') {
    return tm('providers.description.vllm_rerank', { type: template.type });
  }
  return tm('providers.description.default', { type: template.type });
}
