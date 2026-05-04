/**
 * I18n Validator
 * 国际化验证器，用于检查翻译完整性、使用情况分析和错误检测
 */

import type { ValidationResult, ValidationError, UsageReport, TranslationStats } from './types';

export class I18nValidator {
  private baseLocale: string = 'zh-CN';
  private supportedLocales: string[] = ['zh-CN', 'en-US'];

  /**
   * 验证翻译完整性
   */
  validateCompleteness(localeData: Record<string, any>): ValidationResult {
    const errors: ValidationError[] = [];
    const missingKeys: string[] = [];
    const extraKeys: string[] = [];

    // 获取基准语言数据
    const baseData = localeData[this.baseLocale];
    if (!baseData) {
      errors.push({
        type: 'missing',
        key: this.baseLocale,
        message: `基准语言 ${this.baseLocale} 数据缺失`,
        severity: 'error'
      });
      return { isValid: false, missingKeys, extraKeys, errors };
    }

    // 获取所有键
    const baseKeys = this.getAllKeys(baseData);

    // 验证每种语言
    for (const locale of this.supportedLocales) {
      if (locale === this.baseLocale) continue;

      const targetData = localeData[locale];
      if (!targetData) {
        errors.push({
          type: 'missing',
          key: locale,
          message: `语言 ${locale} 数据缺失`,
          severity: 'error'
        });
        continue;
      }

      const targetKeys = this.getAllKeys(targetData);
      
      // 检查缺失的键
      const missing = baseKeys.filter(key => !targetKeys.includes(key));
      missingKeys.push(...missing.map(key => `${locale}.${key}`));

      // 检查多余的键
      const extra = targetKeys.filter(key => !baseKeys.includes(key));
      extraKeys.push(...extra.map(key => `${locale}.${key}`));

      // 添加详细错误信息
      missing.forEach(key => {
        errors.push({
          type: 'missing',
          key: `${locale}.${key}`,
          message: `${locale} 中缺失键: ${key}`,
          severity: 'error'
        });
      });

      extra.forEach(key => {
        errors.push({
          type: 'extra',
          key: `${locale}.${key}`,
          message: `${locale} 中存在多余键: ${key}`,
          severity: 'warning'
        });
      });
    }

    return {
      isValid: errors.filter(e => e.severity === 'error').length === 0,
      missingKeys,
      extraKeys,
      errors
    };
  }

  /**
   * 验证翻译值的有效性
   */
  validateValues(localeData: Record<string, any>): ValidationError[] {
    const errors: ValidationError[] = [];

    for (const [locale, data] of Object.entries(localeData)) {
      this.validateNestedValues(data, locale, '', errors);
    }

    return errors;
  }

  /**
   * 递归验证嵌套值
   */
  private validateNestedValues(
    obj: any, 
    locale: string, 
    parentKey: string, 
    errors: ValidationError[]
  ): void {
    for (const [key, value] of Object.entries(obj)) {
      const fullKey = parentKey ? `${parentKey}.${key}` : key;

      if (typeof value === 'object' && value !== null) {
        this.validateNestedValues(value, locale, fullKey, errors);
      } else if (typeof value === 'string') {
        // 检查空值
        if (!value.trim()) {
          errors.push({
            type: 'empty_value',
            key: `${locale}.${fullKey}`,
            message: `空翻译值: ${locale}.${fullKey}`,
            severity: 'warning'
          });
        }

        // 检查插值占位符
        const placeholders = value.match(/\{[^}]+\}/g) || [];
        for (const placeholder of placeholders) {
          if (!/^{[a-zA-Z_][a-zA-Z0-9_]*}$/.test(placeholder)) {
            errors.push({
              type: 'type_mismatch',
              key: `${locale}.${fullKey}`,
              message: `无效的插值占位符: ${placeholder} in ${locale}.${fullKey}`,
              severity: 'warning'
            });
          }
        }
      } else {
        errors.push({
          type: 'type_mismatch',
          key: `${locale}.${fullKey}`,
          message: `翻译值应为字符串，实际为: ${typeof value}`,
          severity: 'error'
        });
      }
    }
  }

  /**
   * 分析翻译使用情况
   */
  validateUsage(translationKeys: string[], usedKeys: string[]): UsageReport {
    const unusedKeys = translationKeys.filter(key => !usedKeys.includes(key));
    const undefinedKeys = usedKeys.filter(key => !translationKeys.includes(key));

    return {
      unusedKeys,
      undefinedKeys,
      coverage: (usedKeys.length / translationKeys.length) * 100,
      totalKeys: translationKeys.length,
      usedKeys: usedKeys.length
    };
  }

  /**
   * 生成翻译统计信息
   */
  generateStats(localeData: Record<string, any>): TranslationStats {
    const stats: TranslationStats = {
      modules: {},
      locales: {},
      overall: {
        totalKeys: 0,
        averageCoverage: 0,
        lastSync: new Date().toISOString()
      }
    };

    // 分析每种语言
    for (const [locale, data] of Object.entries(localeData)) {
      const keys = this.getAllKeys(data);
      const translatedKeys = keys.filter(key => {
        const value = this.getValueByKey(data, key);
        return typeof value === 'string' && value.trim() !== '';
      });

      stats.locales[locale] = {
        totalKeys: keys.length,
        translatedKeys: translatedKeys.length,
        coverage: (translatedKeys.length / keys.length) * 100
      };

      // 分析模块
      this.analyzeModules(data, locale, stats.modules);
    }

    // 计算总体统计
    const locales = Object.values(stats.locales);
    stats.overall.totalKeys = Math.max(...locales.map(l => l.totalKeys));
    stats.overall.averageCoverage = locales.reduce((sum, l) => sum + l.coverage, 0) / locales.length;

    return stats;
  }

  /**
   * 分析模块统计
   */
  private analyzeModules(data: any, locale: string, modules: TranslationStats['modules']): void {
    for (const [moduleName, moduleData] of Object.entries(data)) {
      if (typeof moduleData === 'object' && moduleData !== null) {
        const moduleKey = `${locale}.${moduleName}`;
        const keys = this.getAllKeys(moduleData);
        const translatedKeys = keys.filter(key => {
          const value = this.getValueByKey(moduleData, key);
          return typeof value === 'string' && value.trim() !== '';
        });

        if (!modules[moduleKey]) {
          modules[moduleKey] = {
            keys: 0,
            coverage: 0,
            lastUpdated: new Date().toISOString()
          };
        }

        modules[moduleKey].keys = keys.length;
        modules[moduleKey].coverage = (translatedKeys.length / keys.length) * 100;
      }
    }
  }

  /**
   * 获取对象的所有键路径
   */
  private getAllKeys(obj: any, prefix: string = ''): string[] {
    const keys: string[] = [];

    for (const [key, value] of Object.entries(obj)) {
      const fullKey = prefix ? `${prefix}.${key}` : key;

      if (typeof value === 'object' && value !== null) {
        keys.push(...this.getAllKeys(value, fullKey));
      } else {
        keys.push(fullKey);
      }
    }

    return keys;
  }

  /**
   * 根据键路径获取值
   */
  private getValueByKey(obj: any, keyPath: string): any {
    return keyPath.split('.').reduce((current, key) => {
      return current && current[key];
    }, obj);
  }

  /**
   * 检查插值一致性
   */
  validateInterpolation(localeData: Record<string, any>): ValidationError[] {
    const errors: ValidationError[] = [];
    const baseData = localeData[this.baseLocale];
    
    if (!baseData) return errors;

    const baseKeys = this.getAllKeys(baseData);

    for (const key of baseKeys) {
      const baseValue = this.getValueByKey(baseData, key);
      if (typeof baseValue !== 'string') continue;

      const basePlaceholders = (baseValue.match(/\{[^}]+\}/g) || []).sort();

      for (const locale of this.supportedLocales) {
        if (locale === this.baseLocale) continue;

        const targetData = localeData[locale];
        if (!targetData) continue;

        const targetValue = this.getValueByKey(targetData, key);
        if (typeof targetValue !== 'string') continue;

        const targetPlaceholders = (targetValue.match(/\{[^}]+\}/g) || []).sort();

        if (JSON.stringify(basePlaceholders) !== JSON.stringify(targetPlaceholders)) {
          errors.push({
            type: 'type_mismatch',
            key: `${locale}.${key}`,
            message: `插值占位符不匹配: ${locale}.${key}，期望 ${basePlaceholders.join(', ')}，实际 ${targetPlaceholders.join(', ')}`,
            severity: 'error'
          });
        }
      }
    }

    return errors;
  }

  /**
   * 验证键命名规范
   */
  validateKeyNaming(localeData: Record<string, any>): ValidationError[] {
    const errors: ValidationError[] = [];
    const keyNamingPattern = /^[a-z][a-zA-Z0-9]*$/;

    for (const [locale, data] of Object.entries(localeData)) {
      this.validateKeyNamingRecursive(data, locale, '', keyNamingPattern, errors);
    }

    return errors;
  }

  /**
   * 递归验证键命名
   */
  private validateKeyNamingRecursive(
    obj: any,
    locale: string,
    parentKey: string,
    pattern: RegExp,
    errors: ValidationError[]
  ): void {
    for (const key of Object.keys(obj)) {
      const fullKey = parentKey ? `${parentKey}.${key}` : key;

      if (!pattern.test(key)) {
        errors.push({
          type: 'type_mismatch',
          key: `${locale}.${fullKey}`,
          message: `键名不符合命名规范: ${key}，应使用小驼峰命名`,
          severity: 'warning'
        });
      }

      if (typeof obj[key] === 'object' && obj[key] !== null) {
        this.validateKeyNamingRecursive(obj[key], locale, fullKey, pattern, errors);
      }
    }
  }

  /**
   * 验证多个语言包
   */
  async validateLocales(locales: string[]): Promise<{
    summary: {
      totalLocales: number;
      totalKeys: number;
      missingKeys: number;
      emptyValues: number;
      invalidInterpolations: number;
      completeness: number;
    };
    details: ValidationResult[];
    recommendations: string[];
  }> {
    const results: ValidationResult[] = [];
    
    for (const locale of locales) {
      try {
        // 这里应该从实际的翻译文件中加载，暂时创建基本结构
        const localeData = { [locale]: {} };
        const result = this.validateCompleteness(localeData);
        results.push(result);
             } catch (error) {
         console.error(`验证语言包 ${locale} 时出错:`, error);
         // 创建错误结果
         const errorResult: ValidationResult = {
           isValid: false,
           missingKeys: [],
           extraKeys: [],
           errors: [
             {
               type: 'missing',
               key: locale,
               message: error instanceof Error ? error.message : '未知错误',
               severity: 'error'
             }
           ]
         };
         results.push(errorResult);
       }
    }
    
        // 生成汇总报告
    const totalKeys = results.length * 100; // 估算的总键数
    const missingKeys = results.reduce((sum, r) => sum + r.missingKeys.length, 0);
    
    return {
      summary: {
        totalLocales: results.length,
        totalKeys,
        missingKeys,
        emptyValues: 0, // 暂时设为0
        invalidInterpolations: 0, // 暂时设为0
        completeness: totalKeys > 0 ? ((totalKeys - missingKeys) / totalKeys) * 100 : 100
      },
      details: results,
      recommendations: [
        '建议优先翻译核心模块的缺失键',
        '检查所有空值并提供适当的翻译',
        '确保插值占位符在所有语言中保持一致'
      ]
    };
  }

  /**
   * 生成验证报告
   */
  generateReport(localeData: Record<string, any>, usedKeys: string[] = []): {
    completeness: ValidationResult;
    values: ValidationError[];
    interpolation: ValidationError[];
    naming: ValidationError[];
    usage: UsageReport | null;
    stats: TranslationStats;
  } {
    const completeness = this.validateCompleteness(localeData);
    const values = this.validateValues(localeData);
    const interpolation = this.validateInterpolation(localeData);
    const naming = this.validateKeyNaming(localeData);
    const stats = this.generateStats(localeData);

    let usage: UsageReport | null = null;
    if (usedKeys.length > 0) {
      const allKeys = this.getAllKeys(localeData[this.baseLocale] || {});
      usage = this.validateUsage(allKeys, usedKeys);
    }

    return {
      completeness,
      values,
      interpolation,
      naming,
      usage,
      stats
    };
  }
} 