/**
 * Dynamic I18n Loader
 * 动态国际化加载器，支持按需加载和缓存机制
 */

export interface LoaderCache {
  [key: string]: any;
}

export interface ModuleInfo {
  name: string;
  path: string;
  loaded: boolean;
  data?: any;
}

export class I18nLoader {
  private cache: Map<string, any> = new Map();
  private moduleRegistry: Map<string, ModuleInfo> = new Map();
  
  constructor() {
    this.registerModules();
  }

  /**
   * 注册所有可用的翻译模块
   */
  private registerModules(): void {
    const modules = [
      // 核心模块
      { name: 'core/common', path: 'core/common.json' },
      { name: 'core/actions', path: 'core/actions.json' },
      { name: 'core/status', path: 'core/status.json' },
      { name: 'core/navigation', path: 'core/navigation.json' },
      { name: 'core/header', path: 'core/header.json' },
      
      // 功能模块
      { name: 'features/chat', path: 'features/chat.json' },
      { name: 'features/extension', path: 'features/extension.json' },
      { name: 'features/conversation', path: 'features/conversation.json' },
      { name: 'features/tooluse', path: 'features/tool-use.json' },
      { name: 'features/provider', path: 'features/provider.json' },
      { name: 'features/platform', path: 'features/platform.json' },
      { name: 'features/config', path: 'features/config.json' },
      { name: 'features/console', path: 'features/console.json' },
      { name: 'features/about', path: 'features/about.json' },
      { name: 'features/settings', path: 'features/settings.json' },
      { name: 'features/auth', path: 'features/auth.json' },
      { name: 'features/chart', path: 'features/chart.json' },
      { name: 'features/dashboard', path: 'features/dashboard.json' },
      { name: 'features/alkaid/index', path: 'features/alkaid/index.json' },
      { name: 'features/alkaid/knowledge-base', path: 'features/alkaid/knowledge-base.json' },
      { name: 'features/alkaid/memory', path: 'features/alkaid/memory.json' },
      
      // 消息模块
      { name: 'messages/errors', path: 'messages/errors.json' },
      { name: 'messages/success', path: 'messages/success.json' },
      { name: 'messages/validation', path: 'messages/validation.json' }
    ];

    modules.forEach(module => {
      this.moduleRegistry.set(module.name, {
        name: module.name,
        path: module.path,
        loaded: false
      });
    });
  }

  /**
   * 加载单个模块
   */
  async loadModule(locale: string, moduleName: string): Promise<any> {
    const cacheKey = `${locale}:${moduleName}`;
    
    // 检查缓存
    if (this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey);
    }

    const moduleInfo = this.moduleRegistry.get(moduleName);
    if (!moduleInfo) {
      console.warn(`模块 ${moduleName} 未注册`);
      return {};
    }

    try {
      // 使用动态import加载JSON文件，兼容构建和开发环境
      const modulePath = `../locales/${locale}/${moduleInfo.path}`;
      const module = await import(/* @vite-ignore */ modulePath);
      const data = module.default || module;

      // 缓存结果
      this.cache.set(cacheKey, data);
      
      // 更新模块信息
      moduleInfo.loaded = true;
      moduleInfo.data = data;

      return data;
    } catch (error) {
      console.error(`加载模块 ${moduleName} 失败:`, error);
      
      // 回退方案：尝试使用fetch（开发环境）
      try {
        const modulePath = `/src/i18n/locales/${locale}/${moduleInfo.path}`;
        const response = await fetch(modulePath);
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();

        // 缓存结果
        this.cache.set(cacheKey, data);
        
        // 更新模块信息
        moduleInfo.loaded = true;
        moduleInfo.data = data;

        return data;
      } catch (fetchError) {
        console.error(`回退fetch加载也失败:`, fetchError);
        return {};
      }
    }
  }

  /**
   * 通用模块加载器 - 减少重复代码，提高可维护性
   */
  private async loadModules(
    locale: string,
    prefix: string,
    overrideList: string[] = []
  ): Promise<any> {
    // 使用覆盖列表或从注册表中筛选符合前缀的模块名
    const moduleNames = overrideList.length > 0
      ? overrideList
      : Array.from(this.moduleRegistry.keys()).filter(key => key.startsWith(prefix));

    const results = await Promise.all(
      moduleNames.map(module => this.loadModule(locale, module))
    );

    return this.mergeModules(results, moduleNames);
  }

  /**
   * 加载核心模块（最高优先级）
   */
  async loadCoreModules(locale: string): Promise<any> {
    return this.loadModules(locale, 'core');
  }

  /**
   * 加载功能模块
   */
  async loadFeatureModules(locale: string, features?: string[]): Promise<any> {
    return this.loadModules(locale, 'features', features || []);
  }

  /**
   * 加载消息模块
   */
  async loadMessageModules(locale: string): Promise<any> {
    return this.loadModules(locale, 'messages');
  }

  /**
   * 加载所有模块
   */
  async loadAllModules(locale: string): Promise<any> {
    const [core, features, messages] = await Promise.all([
      this.loadCoreModules(locale),
      this.loadFeatureModules(locale),
      this.loadMessageModules(locale)
    ]);

    return {
      ...core,
      ...features,
      ...messages
    };
  }

  /**
   * 加载完整语言包（所有模块合并）
   */
  async loadLocale(locale: string): Promise<any> {
    return this.loadAllModules(locale);
  }

  /**
   * 合并多个模块数据
   */
  private mergeModules(modules: any[], moduleNames: string[]): any {
    const result: any = {};
    const pathRegistry = new Map<string, string>();
    
    modules.forEach((module, index) => {
      const moduleName = moduleNames[index];
      const nameParts = moduleName.split('/');
      
      // 构建嵌套对象结构（对所有模块统一处理）
      let current = result;
      for (let i = 0; i < nameParts.length - 1; i++) {
        if (!current[nameParts[i]]) {
          current[nameParts[i]] = {};
        }
        current = current[nameParts[i]];
      }
      
      // 冲突检测：检查最终键是否已存在
      const finalKey = nameParts[nameParts.length - 1];
      const fullPath = nameParts.join('.');
      
      if (current[finalKey] && pathRegistry.has(fullPath)) {
        const existingModule = pathRegistry.get(fullPath);
        console.warn(`⚠️ I18n模块路径冲突: "${fullPath}" 已被模块 "${existingModule}" 占用，模块 "${moduleName}" 可能会覆盖部分键值`);
      }
      
      // 记录路径和模块名的映射
      pathRegistry.set(fullPath, moduleName);
      
      // 设置最终值（保持原有的浅合并行为）
      current[finalKey] = { ...current[finalKey], ...module };
    });

    return result;
  }

  /**
   * 预加载关键模块
   */
  async preloadEssentials(locale: string): Promise<void> {
    const essentials = [
      'core/common',
      'core/navigation',
      'features/chat'
    ];

    await Promise.all(
      essentials.map(module => this.loadModule(locale, module))
    );
  }

  /**
   * 清理缓存
   */
  clearCache(locale?: string): void {
    if (locale) {
      // 清理特定语言的缓存
      const keys = Array.from(this.cache.keys()).filter((key: string) => key.startsWith(`${locale}:`));
      keys.forEach((key: string) => this.cache.delete(key));
    } else {
      // 清理所有缓存
      this.cache.clear();
    }
  }

  /**
   * 获取加载状态
   */
  getLoadingStatus(): { total: number; loaded: number; modules: ModuleInfo[] } {
    const modules = Array.from(this.moduleRegistry.values());
    const loaded = modules.filter(m => m.loaded).length;
    
    return {
      total: modules.length,
      loaded,
      modules
    };
  }

  /**
   * 热重载模块
   */
  async reloadModule(locale: string, moduleName: string): Promise<any> {
    const cacheKey = `${locale}:${moduleName}`;
    this.cache.delete(cacheKey);
    
    const moduleInfo = this.moduleRegistry.get(moduleName);
    if (moduleInfo) {
      moduleInfo.loaded = false;
    }
    
    return this.loadModule(locale, moduleName);
  }


} 