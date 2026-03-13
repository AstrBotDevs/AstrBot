import { EXTENSION_ROUTE_NAME } from '../router/routeConstants.mjs';

export function getValidHashTab(routeHash, validTabs) {
  const hash = String(routeHash || '');
  const tab = hash.includes('#') ? hash.slice(hash.lastIndexOf('#') + 1) : hash;
  return validTabs.includes(tab) ? tab : null;
}

export function createTabRouteLocation(route, tab, fallbackRouteName = EXTENSION_ROUTE_NAME) {
  const query = route?.query ? { ...route.query } : {};
  const params = route?.params ? { ...route.params } : undefined;

  if (route?.name) {
    return {
      name: route.name,
      ...(params ? { params } : {}),
      query,
      hash: `#${tab}`,
    };
  }

  if (route?.path) {
    return {
      path: route.path,
      ...(params ? { params } : {}),
      query,
      hash: `#${tab}`,
    };
  }

  return {
    name: fallbackRouteName,
    ...(params ? { params } : {}),
    query,
    hash: `#${tab}`,
  };
}

export async function replaceTabRoute(router, route, tab, logger = console) {
  try {
    await router.replace(createTabRouteLocation(route, tab));
    return true;
  } catch (error) {
    logger.debug?.('Failed to update extension tab route:', error);
    return false;
  }
}
