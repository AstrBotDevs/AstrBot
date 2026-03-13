export function waitForRouterReadyInBackground(router, logger = console) {
  router.isReady().catch((error) => {
    logger.warn?.('Router did not become ready after fallback mount:', error);
  });
}
