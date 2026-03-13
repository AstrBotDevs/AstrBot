export function getValidHashTab(routeHash, validTabs) {
  const tab = String(routeHash || '').replace(/^#/, '');
  return validTabs.includes(tab) ? tab : null;
}

export function createTabRouteLocation(route, tab, fallbackPath = '/extension') {
  return {
    path: route?.path || fallbackPath,
    query: route?.query || {},
    hash: `#${tab}`,
  };
}
