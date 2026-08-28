import { describe, expect, it } from 'vitest';
import {
  getPlatformColor,
  getPlatformDisplayName,
  getPlatformIcon,
  getTutorialLink,
} from '@/utils/platformUtils';

describe('platformUtils', () => {
  it('exposes NapCat tutorial, icon, and display name mappings', () => {
    expect(getTutorialLink('napcat')).toBe('/help/platform/napcat.html');
    expect(getTutorialLink('napcat', 'en-US')).toBe(
      '/help/en/platform/napcat.html',
    );
    expect(getPlatformDisplayName('napcat')).toBe('napcat (NapCat WebSocket)');
    expect(getPlatformIcon('napcat')).toBeTruthy();
    expect(getPlatformColor('napcat')).toBe('blue');
  });
});
