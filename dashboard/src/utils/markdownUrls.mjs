const GITHUB_REPO_PATTERN = /^https?:\/\/github\.com\/([^/\s]+)\/([^/\s#?]+?)\/?$/i;
const ABSOLUTE_URL_PATTERN = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

/**
 * Rewrite relative URLs in rendered markdown HTML against their true source.
 *
 * Plugin README files are read from the local plugin directory, so relative
 * references such as `docs/demo.png` would otherwise resolve against the
 * dashboard origin and break. They are resolved against the plugin's
 * repository instead, mirroring GitHub's own rendering: images point to
 * raw.githubusercontent.com, links point to github.com blob pages, both under
 * the HEAD symbolic ref which follows the default branch. When the document
 * was fetched from a remote URL (`docUrl`), it is used as the source instead:
 * directory-relative references resolve against the document location, while
 * leading-slash references resolve against the origin host root.
 *
 * @param {HTMLElement} root Rendered markdown container.
 * @param {object} options
 * @param {string} options.repoUrl Plugin repository URL (e.g. GitHub repo).
 * @param {string} options.docUrl URL the markdown document was fetched from.
 */
export function resolveRelativeUrls(root, { repoUrl = "", docUrl = "" } = {}) {
  const documentUrl = String(docUrl || "").trim();
  const repoMatch = GITHUB_REPO_PATTERN.exec(String(repoUrl || "").trim());
  const rawBase = repoMatch
    ? `https://raw.githubusercontent.com/${repoMatch[1]}/${repoMatch[2]}/HEAD/`
    : "";
  const blobBase = repoMatch
    ? `https://github.com/${repoMatch[1]}/${repoMatch[2]}/blob/HEAD/`
    : "";

  const resolve = (value, repoBase) => {
    const url = String(value || "").trim();
    if (!url || ABSOLUTE_URL_PATTERN.test(url) || url.startsWith("#")) {
      return value;
    }
    const base = documentUrl || repoBase;
    if (!base) return value;
    try {
      if (url.startsWith("/")) {
        // Leading slashes are origin/repo-root-relative, not document-relative.
        if (documentUrl) return new URL(url, new URL(documentUrl).origin).href;
        // With a GitHub repo base, strip the slash so the path lands at the
        // repository root (the base already ends with the default-branch ref).
        return new URL(url.replace(/^\/+/, ""), repoBase).href;
      }
      return new URL(url, base).href;
    } catch {
      return value;
    }
  };

  root.querySelectorAll("img[src]").forEach((img) => {
    img.setAttribute("src", resolve(img.getAttribute("src"), rawBase));
  });

  root.querySelectorAll("a[href]").forEach((link) => {
    link.setAttribute("href", resolve(link.getAttribute("href"), blobBase));
  });
}
