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
// 运算符对象必须是"恰好单一 empty / notEmpty 布尔键"的形状；带其它键或值非布尔的对象
// 一律按字面值走深度相等，避免与真实配置值（恰好含同名键）混淆。
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
 * 递归深度相等：对象按键集合比较（顺序无关），数组按元素顺序比较（顺序有意义）。
 * 用于 condition 未知运算符对象的回退判定。
 *
 * @param {*} a
 * @param {*} b
 * @returns {boolean}
 */
export function deepEqual(a, b) {
  if (a === b) {
    return true
  }
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') {
    return false
  }
  if (Array.isArray(a) !== Array.isArray(b)) {
    return false
  }
  if (Array.isArray(a)) {
    if (a.length !== b.length) {
      return false
    }
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) {
        return false
      }
    }
    return true
  }
  const keysA = Object.keys(a)
  if (keysA.length !== Object.keys(b).length) {
    return false
  }
  for (const key of keysA) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) {
      return false
    }
    if (!deepEqual(a[key], b[key])) {
      return false
    }
  }
  return true
}

/**
 * 判定 expected 是否为"运算符对象"。
 *
 * 仅当对象**恰好**包含一个键、且该键为 `empty` / `notEmpty`、其值为布尔时，才视为运算符；
 * 其余对象（含额外键、值非布尔、数组、空对象）一律当作字面配置值走深度相等。
 * 这样可区分"运算符指令"与"恰好带 empty / notEmpty 键的真实配置值"。
 *
 * @param {*} expected
 * @returns {boolean}
 */
export function isOperatorObject(expected) {
  if (expected === null || typeof expected !== 'object' || Array.isArray(expected)) {
    return false
  }
  const keys = Object.keys(expected)
  if (keys.length !== 1) {
    return false
  }
  const key = keys[0]
  if (key !== 'empty' && key !== 'notEmpty') {
    return false
  }
  return typeof expected[key] === 'boolean'
}

/**
 * 判断单条 condition 规则是否成立。
 *
 * - expected 为原始值（非对象）：保持旧语义，actualValue 必须严格相等。
 * - expected 为"运算符对象"（恰好单一 empty / notEmpty 布尔键）：按运算符求值。
 * - 其它对象 / 数组：退回深度相等（对象键序无关、数组序有意义），避免误显/误隐。
 *
 * @param {*} actualValue 配置中实际取到的值（缺路径时为 undefined）
 * @param {*} expected condition 中声明的值或运算符对象
 * @returns {boolean}
 */
export function conditionRuleMatches(actualValue, expected) {
  if (typeof expected !== 'object' || expected === null) {
    return actualValue === expected
  }
  if (isOperatorObject(expected)) {
    if ('empty' in expected) {
      return expected.empty ? isConfigValueEmpty(actualValue) : !isConfigValueEmpty(actualValue)
    }
    return expected.notEmpty ? !isConfigValueEmpty(actualValue) : isConfigValueEmpty(actualValue)
  }
  // 字面对象 / 数组：深度相等（对象键序无关，数组序有意义）
  return deepEqual(actualValue, expected)
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
