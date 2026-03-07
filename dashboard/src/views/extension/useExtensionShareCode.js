import {
  compressToEncodedURIComponent,
  decompressFromEncodedURIComponent,
} from "lz-string";

const SHARE_CODE_LZ_PREFIX = "astrbot-share:";

const normalizeRepos = (repos = []) =>
  repos
    .filter((repo) => typeof repo === "string")
    .map((repo) => repo.trim())
    .filter((repo) => repo.length > 0);

export const useExtensionShareCode = () => {
  const encode = (repos = []) => {
    const normalizedRepos = [...new Set(normalizeRepos(repos))].sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" }),
    );
    const rawJson = JSON.stringify({
      repos: normalizedRepos,
    });
    const compressed = compressToEncodedURIComponent(rawJson);
    if (!compressed) {
      return rawJson;
    }
    return `${SHARE_CODE_LZ_PREFIX}${compressed}`;
  };

  const decode = (code = "") => {
    const rawCode = typeof code === "string" ? code : "";
    let decodedContent = rawCode;

    if (rawCode.startsWith(SHARE_CODE_LZ_PREFIX)) {
      const encodedPart = rawCode.slice(SHARE_CODE_LZ_PREFIX.length);
      const decompressed = decompressFromEncodedURIComponent(encodedPart);
      if (!decompressed) {
        throw new Error("Invalid lz share code");
      }
      decodedContent = decompressed;
    }

    const parsed = JSON.parse(decodedContent);
    const repos = Array.isArray(parsed?.repos) ? parsed.repos : [];
    return normalizeRepos(repos);
  };

  return {
    encode,
    decode,
  };
};
