// 自定义插件源可能没有 download_count 字段，因此未知下载量在升序和降序中都始终置底
const normalizeDownloadCount = (value) => {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return undefined;
  }
  return Math.max(0, Math.trunc(parsed));
};

export const sortMarketPluginsByDownloads = (plugins, order = "desc") => {
  const direction = order === "asc" ? 1 : -1;
  return (Array.isArray(plugins) ? plugins : [])
    .map((plugin, index) => ({ plugin, index }))
    .sort((left, right) => {
      const countA = normalizeDownloadCount(left.plugin?.download_count);
      const countB = normalizeDownloadCount(right.plugin?.download_count);
      if (countA === undefined && countB === undefined) {
        return left.index - right.index;
      }
      if (countA === undefined) return 1;
      if (countB === undefined) return -1;
      const diff = (countA - countB) * direction;
      return diff !== 0 ? diff : left.index - right.index;
    })
    .map((item) => item.plugin);
};
