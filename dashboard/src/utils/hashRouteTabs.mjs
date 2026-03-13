import { EXTENSION_ROUTE_NAME } from '../router/routeConstants.mjs';

export function getValidHashTab(routeHash, validTabs) {
  const tab = String(routeHash || '').replace(/^#/, '');
  return validTabs.includes(tab) ? tab : null;
}

export function createTabRouteLocation(route, tab, fallbackRouteName = EXTENSION_ROUTE_NAME) {
  const query = route?.query ? { ...route.query } : {};

  if (route?.path) {
    return {
      path: route.path,
      query,
      hash: `#${tab}`,
    };
  }

  return {
    name: route?.name || fallbackRouteName,
    query,
    hash: `#${tab}`,
  };
}
