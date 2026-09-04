import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveRelativeUrls } from '../src/utils/markdownUrls.mjs';

const GITHUB_REPO = 'https://github.com/AstrBotDevs/AstrBot';

function createNode(attrs = {}) {
  const attributes = { ...attrs };
  return {
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attributes, name)
        ? attributes[name]
        : null;
    },
    setAttribute(name, value) {
      attributes[name] = value;
    },
    attr(name) {
      return attributes[name];
    },
  };
}

function createRoot({ images = [], links = [] } = {}) {
  return {
    querySelectorAll(selector) {
      if (selector === 'img[src]') return images;
      if (selector === 'a[href]') return links;
      return [];
    },
  };
}

test('resolves relative image src against the raw GitHub base', () => {
  const img = createNode({ src: 'docs/demo.png' });
  resolveRelativeUrls(createRoot({ images: [img] }), { repoUrl: GITHUB_REPO });

  assert.equal(
    img.attr('src'),
    'https://raw.githubusercontent.com/AstrBotDevs/AstrBot/HEAD/docs/demo.png',
  );
});

test('treats a leading slash as repo-root-relative', () => {
  const img = createNode({ src: '/docs/demo.png' });
  resolveRelativeUrls(createRoot({ images: [img] }), { repoUrl: GITHUB_REPO });

  assert.equal(
    img.attr('src'),
    'https://raw.githubusercontent.com/AstrBotDevs/AstrBot/HEAD/docs/demo.png',
  );
});

test('resolves relative link href against the GitHub blob base', () => {
  const link = createNode({ href: 'CHANGELOG.md' });
  resolveRelativeUrls(createRoot({ links: [link] }), { repoUrl: GITHUB_REPO });

  assert.equal(
    link.attr('href'),
    'https://github.com/AstrBotDevs/AstrBot/blob/HEAD/CHANGELOG.md',
  );
});

test('leaves anchor, absolute, and protocol-relative URLs unchanged', () => {
  const anchor = createNode({ href: '#install' });
  const absolute = createNode({ href: 'https://example.com/a.png' });
  const protocolRelative = createNode({ src: '//example.com/a.png' });

  resolveRelativeUrls(
    createRoot({ images: [protocolRelative], links: [anchor, absolute] }),
    { repoUrl: GITHUB_REPO },
  );

  assert.equal(anchor.attr('href'), '#install');
  assert.equal(absolute.attr('href'), 'https://example.com/a.png');
  assert.equal(protocolRelative.attr('src'), '//example.com/a.png');
});

test('uses docUrl as the base for everything when provided', () => {
  const img = createNode({ src: 'docs/demo.png' });
  const link = createNode({ href: 'CHANGELOG.md' });
  resolveRelativeUrls(createRoot({ images: [img], links: [link] }), {
    repoUrl: GITHUB_REPO,
    docUrl: 'https://raw.githubusercontent.com/someone/other/main/README.md',
  });

  assert.equal(
    img.attr('src'),
    'https://raw.githubusercontent.com/someone/other/main/docs/demo.png',
  );
  assert.equal(
    link.attr('href'),
    'https://raw.githubusercontent.com/someone/other/main/CHANGELOG.md',
  );
});

test('leaves relative URLs untouched for a non-GitHub repo', () => {
  const img = createNode({ src: 'docs/demo.png' });
  const link = createNode({ href: 'CHANGELOG.md' });
  resolveRelativeUrls(createRoot({ images: [img], links: [link] }), {
    repoUrl: 'https://gitlab.com/team/project',
  });

  assert.equal(img.attr('src'), 'docs/demo.png');
  assert.equal(link.attr('href'), 'CHANGELOG.md');
});

test('ignores empty repoUrl and docUrl', () => {
  const img = createNode({ src: 'docs/demo.png' });
  resolveRelativeUrls(createRoot({ images: [img] }), {});

  assert.equal(img.attr('src'), 'docs/demo.png');
});
