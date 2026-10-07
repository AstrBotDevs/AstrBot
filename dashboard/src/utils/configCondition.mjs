// 配置项 `condition` 可见性求值。
//
// 设计目标：在保持旧语义（原始值 = 严格相等）的前提下，补充"为空 / 非空"
// 运算符，使插件能在某项被留空时自动隐藏依赖它的其它配置项。
//
// `condition` 形如：
//   { "other_key": <原始值> }            // 旧写法：other_key 严格等于该值才显示
//   { "other_key": { "empty": true } }   // other_key 为空时才显示
//   { "other_key": { "notEmpty": true } }// other_key 非空时才显示
//   { "other_key": { "empty": false } }  // 等价于 { "notEmpty": true }
//
// 求值结果决定配置项（或整个 section）是否在面板中显示，仅影响 UI，不改变保存值。

/**
 * 判断配置值是否视为"空"。
 * 覆盖：undefined / null / 空字符串 / 空数组 / 空对象。
 * 注意：数字 0、布尔 false 不视为空，避免误隐依赖它们的配置项。
 *
 * @param {*} value
 * @returns {boolean}
 */
export function isConfigValueEmpty(value) {
  return (
    value === undefined ||
    value === null ||
    value === '' ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === 'object' && Object.keys(value).length === 0)
  )
}

/**
 * 判断单条 condition 规则是否成立。
 *
 * - expected 为原始值（非对象）：保持旧语义，actualValue 必须严格相等。
 * - expected 为对象：按运算符求值，支持 `empty` / `notEmpty`。
 * - expected 为对象但不含已知运算符：退回深度相等，避免误显/误隐。
 *
 * @param {*} actualValue 配置中实际取到的值（缺路径时为 undefined）
 * @param {*} expected condition 中声明的值或运算符对象
 * @returns {boolean}
 */
export function conditionRuleMatches(actualValue, expected) {
  if (typeof expected !== 'object' || expected === null) {
    return actualValue === expected
  }
  if ('empty' in expected) {
    return expected.empty ? isConfigValueEmpty(actualValue) : !isConfigValueEmpty(actualValue)
  }
  if ('notEmpty' in expected) {
    return expected.notEmpty ? !isConfigValueEmpty(actualValue) : isConfigValueEmpty(actualValue)
  }
  // 未知运算符对象：退回深度相等
  return JSON.stringify(actualValue) === JSON.stringify(expected)
}

/**
 * 判断整组 condition 是否满足（全部规则成立才显示）。
 *
 * @param {Object|undefined} condition condition 声明对象
 * @param {(key: string) => *} resolveValue 按配置键解析实际值的回调
 * @returns {boolean}
 */
export function evaluateCondition(condition, resolveValue) {
  if (!condition) {
    return true
  }
  for (const [key, expected] of Object.entries(condition)) {
    if (!conditionRuleMatches(resolveValue(key), expected)) {
      return false
    }
  }
  return true
}
