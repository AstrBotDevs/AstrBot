import test from 'node:test';
import assert from 'node:assert/strict';

import { getPlatformIcon } from '../src/utils/platformUtils.js';

test('VoceChat uses the generic platform fallback instead of a missing asset', () => {
  assert.equal(getPlatformIcon('vocechat'), undefined);
});
