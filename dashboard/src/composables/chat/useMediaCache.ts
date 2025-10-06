export function createMediaCache(getFile: (filename: string) => Promise<Blob>) {
  const cache: Record<string, string> = {};

  async function getMediaUrl(filename: string): Promise<string> {
    if (cache[filename]) return cache[filename];
    const blob = await getFile(filename);
    const url = URL.createObjectURL(blob);
    cache[filename] = url;
    return url;
  }

  function cleanup() {
    Object.values(cache).forEach((url) => {
      if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
    });
    Object.keys(cache).forEach((k) => delete cache[k]);
  }

  return { getMediaUrl, cleanup };
}
