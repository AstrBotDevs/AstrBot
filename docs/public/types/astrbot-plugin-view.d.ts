/** Public iframe bridge declarations. The host injects the runtime SDK. */
// #region base
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type Unsubscribe = () => void;
export type QueryParams = Record<string, JsonValue | undefined>;
export type SSEParams = Record<
  string,
  string | number | boolean | null | undefined
>;
export type I18nResources = Record<string, JsonObject>;
// #endregion base

// #region context
export interface ThemeColors {
  primary?: string;
  secondary?: string;
  "on-primary"?: string;
  primaryText?: string;
  "on-surface"?: string;
  secondaryText?: string;
  background?: string;
  surface?: string;
  border?: string;
  error?: string;
  [name: string]: string | undefined;
}

export interface BaseContext {
  pluginName: string;
  displayName: string;
  pageName: string;
  pageTitle: string;
  locale: string;
  i18n: I18nResources;
  isDark: boolean;
  themeColors: ThemeColors;
}

export interface ViewSnapshot<TData = JsonObject> {
  id: string;
  revision: number;
  data: TData;
}

export interface StandalonePageContext extends BaseContext {
  target: "plugin_page";
  sessionId: null;
  view?: never;
}

export interface MessageViewContext<TData = JsonObject> extends BaseContext {
  target: "chat_message" | "chat_workbench" | "chat_workbench_with_launcher";
  view: ViewSnapshot<TData>;
  sessionId?: never;
}

export interface ResidentWorkbenchContext extends BaseContext {
  target: "chat_workbench_with_launcher";
  sessionId: string | null;
  view?: never;
}

export type BridgeContext<TData = JsonObject> =
  | StandalonePageContext
  | MessageViewContext<TData>
  | ResidentWorkbenchContext;
// #endregion context

// #region sse
export interface SSEMessage<TData = unknown> {
  raw: string;
  parsed: TData | string;
  eventType: string;
  lastEventId: string;
}

export interface SSEHandlers<TData = unknown> {
  onOpen?: () => void;
  onMessage?: (event: SSEMessage<TData>) => void;
  onClose?: () => void;
  onError?: () => void;
}
// #endregion sse

// #region results
export interface UploadFile {
  arrayBuffer(): Promise<ArrayBuffer>;
  name?: string;
  type?: string;
  lastModified?: number;
}

export interface DownloadResult {
  filename: string;
}

export interface ChatResult {
  sessionId: string | null;
}

export interface UnsubscribeSSEResult {
  subscriptionId: string;
}

export interface BridgeError extends Error {
  code?: string;
}
// #endregion results

// #region bridge
export interface AstrBotPluginViewBridge<TViewData = JsonObject> {
  ready(): Promise<BridgeContext<TViewData>>;
  getContext(): BridgeContext<TViewData> | null;
  getLocale(): string;
  getI18n(): I18nResources;
  t(key: string, fallback?: string): string;
  onContext(handler: (context: BridgeContext<TViewData>) => void): Unsubscribe;

  view: {
    subscribe(
      handler: (snapshot: ViewSnapshot<TViewData>) => void,
    ): Unsubscribe;
    action(actionId: string, data?: JsonValue): Promise<void>;
  };

  chat: {
    fill(text: string): Promise<ChatResult>;
    send(text: string): Promise<ChatResult>;
  };

  apiGet<TResult = unknown>(
    endpoint: string,
    params?: QueryParams,
  ): Promise<TResult>;
  apiPost<TResult = unknown>(
    endpoint: string,
    body?: JsonValue,
  ): Promise<TResult>;
  upload<TResult = unknown>(
    endpoint: string,
    file: UploadFile,
  ): Promise<TResult>;
  download(
    endpoint: string,
    params?: QueryParams,
    filename?: string,
  ): Promise<DownloadResult>;
  subscribeSSE<TData = unknown>(
    endpoint: string,
    handlers?: SSEHandlers<TData>,
    params?: SSEParams,
  ): Promise<string>;
  unsubscribeSSE(subscriptionId: string): Promise<UnsubscribeSSEResult>;
}
// #endregion bridge

declare global {
  interface Window {
    AstrBotPluginView: AstrBotPluginViewBridge;
    /** Compatibility alias of AstrBotPluginView. */
    AstrBotPluginPage: AstrBotPluginViewBridge;
  }
}
