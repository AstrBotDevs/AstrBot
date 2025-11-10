/**
 * Tauri 环境检测工具
 * 用于区分 Web 端和桌面端环境
 */

/**
 * 检测是否在 Tauri 环境中运行
 * @returns {boolean} 如果在 Tauri 环境中返回 true，否则返回 false
 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && 
         (window as any).__TAURI_INTERNALS__ !== undefined;
}

/**
 * 检测是否在 Web 环境中运行
 * @returns {boolean} 如果在 Web 环境中返回 true，否则返回 false
 */
export function isWeb(): boolean {
  return !isTauri();
}

/**
 * 获取 Tauri API（仅在 Tauri 环境中可用）
 * @returns {any} Tauri API 对象或 null
 */
export function getTauriAPI(): any {
  if (isTauri()) {
    // Tauri 2.0 建议使用 @tauri-apps/api 包而不是全局对象
    return (window as any).__TAURI_INTERNALS__;
  }
  return null;
}

/**
 * 平台特定的 API 调用包装器
 * 在 Web 环境中使用 HTTP API，在 Tauri 环境中可以使用本地 API
 */
export class PlatformAPI {
  /**
   * 根据平台选择合适的 API 端点
   * @param webEndpoint Web 端 API 地址
   * @param tauriEndpoint Tauri 端 API 地址（可选，默认使用 webEndpoint）
   */
  static getEndpoint(webEndpoint: string, tauriEndpoint?: string): string {
    if (isTauri() && tauriEndpoint) {
      return tauriEndpoint;
    }
    return webEndpoint;
  }

  /**
   * 获取基础 URL
   * Web 端使用相对路径，Tauri 端使用完整的后端地址
   */
  static getBaseURL(): string {
    if (isTauri()) {
      // Tauri 环境中，需要连接到本地运行的后端服务
      return 'http://127.0.0.1:6185';
    }
    // Web 环境中使用相对路径，由 Vite 代理处理
    return '';
  }
}

export default {
  isTauri,
  isWeb,
  getTauriAPI,
  PlatformAPI
};
