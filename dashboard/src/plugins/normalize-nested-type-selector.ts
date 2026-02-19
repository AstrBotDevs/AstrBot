type RuleNode = {
  parent?: { type?: string };
  selector?: string;
  source?: { input?: { file?: string; from?: string } };
};

const normalizeNestedTypeSelectorPlugin = {
  postcssPlugin: 'normalize-nested-type-selector',
  Rule(rule: RuleNode) {
    if (rule.parent?.type !== 'rule' || typeof rule.selector !== 'string') {
      return;
    }

    const sourceFile = String(rule.source?.input?.file || rule.source?.input?.from || '')
      .replace(/\\/g, '/')
      .toLowerCase();
    const isProjectSource = sourceFile.includes('/dashboard/src/');
    const isMonacoVendor = sourceFile.includes('/node_modules/monaco-editor/');
    if (!isProjectSource && !isMonacoVendor) {
      return;
    }

    const segments = rule.selector
      .split(',')
      .map((segment) => segment.trim())
      .filter(Boolean);
    if (!segments.length) {
      return;
    }

    const typeOnlyPattern = /^[a-zA-Z][\w-]*$/;
    if (!segments.every((segment) => typeOnlyPattern.test(segment))) {
      return;
    }

    rule.selector = segments.map((segment) => `:is(${segment})`).join(', ');
  },
};

export default normalizeNestedTypeSelectorPlugin;
