export type GitHubProxyMode = '0' | '1';

export interface GitHubProxyState {
  radioValue: GitHubProxyMode;
  control: string;
  selectedProxy: string;
}

const GITHUB_PROXY_KEY = 'selectedGitHubProxy';
const GITHUB_PROXY_RADIO_KEY = 'githubProxyRadioValue';
const GITHUB_PROXY_CONTROL_KEY = 'githubProxyRadioControl';

function getLocalStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function normalizeRadioValue(value: string | null): GitHubProxyMode {
  return value === '1' ? '1' : '0';
}

export function readGitHubProxyState(): GitHubProxyState {
  const storage = getLocalStorage();
  if (!storage) {
    return {
      radioValue: '0',
      control: '0',
      selectedProxy: '',
    };
  }

  return {
    radioValue: normalizeRadioValue(storage.getItem(GITHUB_PROXY_RADIO_KEY)),
    control: String(storage.getItem(GITHUB_PROXY_CONTROL_KEY) || '0'),
    selectedProxy: String(storage.getItem(GITHUB_PROXY_KEY) || ''),
  };
}

export function readSelectedGitHubProxy(): string {
  return '';
}

export function writeSelectedGitHubProxy(value: string): void {
  const storage = getLocalStorage();
  if (storage) {
    storage.setItem(GITHUB_PROXY_KEY, value);
  }
}

export function writeGitHubProxyRadioValue(value: string): void {
  const storage = getLocalStorage();
  if (storage) {
    storage.setItem(GITHUB_PROXY_RADIO_KEY, normalizeRadioValue(value));
  }
}

export function writeGitHubProxyControl(value: string): void {
  const storage = getLocalStorage();
  if (storage) {
    storage.setItem(GITHUB_PROXY_CONTROL_KEY, String(value));
  }
}
