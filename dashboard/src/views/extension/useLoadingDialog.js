const createDefaultProgress = () => ({
  enabled: false,
  current: 0,
  total: 0,
  label: "",
});

export const useLoadingDialog = (loadingDialog, tm) => {
  const reset = () => {
    loadingDialog.show = false;
    loadingDialog.title = tm("dialogs.loading.title");
    loadingDialog.statusCode = 0;
    loadingDialog.result = "";
    loadingDialog.progress = createDefaultProgress();
  };

  const start = (title) => {
    reset();
    loadingDialog.title = title;
    loadingDialog.show = true;
  };

  const startProgress = (title, total) => {
    start(title);
    loadingDialog.progress.enabled = true;
    loadingDialog.progress.current = 0;
    loadingDialog.progress.total = total;
    loadingDialog.progress.label = "";
  };

  const updateProgress = (current, total, label) => {
    loadingDialog.progress.current = current;
    loadingDialog.progress.total = total;
    loadingDialog.progress.label = label;
  };

  const finish = (statusCode, result, timeToClose = 2000) => {
    loadingDialog.statusCode = statusCode;
    loadingDialog.result = result;
    loadingDialog.progress.enabled = false;
    if (timeToClose === -1) return;
    setTimeout(reset, timeToClose);
  };

  return {
    reset,
    start,
    startProgress,
    updateProgress,
    finish,
  };
};
