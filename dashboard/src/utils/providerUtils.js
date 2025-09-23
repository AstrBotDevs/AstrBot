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
    'openai': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/openai.svg',
    'azure': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/azure.svg',
    'xai': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/xai.svg',
    'anthropic': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/anthropic.svg',
    'ollama': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/ollama.svg',
    'google': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/gemini-color.svg',
    'deepseek': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/deepseek.svg',
    'modelscope': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/modelscope.svg',
    'zhipu': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/zhipu.svg',
    'siliconflow': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/siliconcloud.svg',
    'moonshot': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/kimi.svg',
    'ppio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/ppio.svg',
    'dify': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/dify-color.svg',
    'dashscope': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/alibabacloud-color.svg',
    'fastgpt': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/fastgpt-color.svg',
    'lm_studio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/lmstudio.svg',
    'fishaudio': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/fishaudio.svg',
    'minimax': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/minimax.svg',
    '302ai': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/1.53.0/files/icons/ai302-color.svg',
    'microsoft': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/microsoft.svg',
    'vllm': 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons/vllm.svg',
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
  if (name == 'OpenAI') {
    return tm('providers.description.openai', { type: template.type });
  } else if (name == 'vLLM Rerank') {
    return tm('providers.description.vllm_rerank', { type: template.type });
  }
  return tm('providers.description.default', { type: template.type });
}
