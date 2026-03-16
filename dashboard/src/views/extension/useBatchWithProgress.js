export const runBatchWithProgress = async (items, worker, onProgress) => {
  const results = [];
  let completed = 0;
  const total = items.length;

  for (const item of items) {
    try {
      const value = await worker(item);
      results.push({ status: "fulfilled", value });
    } catch (reason) {
      results.push({ status: "rejected", reason });
    } finally {
      completed += 1;
      onProgress?.({ current: completed, total, item });
    }
  }

  return { results };
};
