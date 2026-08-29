import { generatedQuery, openApiV1, typed } from './shared';
import type {
  ChatMessagePatchRequest,
  ChatMessageRegenerateRequest,
  ChatProjectRequest,
  ChatRequest,
  ChatSessionBatchDeleteRequest,
  ChatSessionPatchRequest,
  ChatThreadCreateRequest,
  ChatThreadMessageRequest,
} from './shared';
import type {
  ChatBatchDeleteData,
  ChatMessageMutationData,
  ChatSessionDetailData,
  ChatSessionListParams,
  ChatSessionSummary,
  ChatThreadData,
  ChatThreadDetailData,
  OpenConfig,
  ProjectData,
} from './types';

export const chatApi = {
  send(payload: ChatRequest) {
    return typed<OpenConfig>(openApiV1.sendChatMessage({ body: payload }));
  },
  sendStreamUrl() {
    return '/api/v1/chat';
  },
  resumeRunStreamUrl(runId: string) {
    return `/api/v1/chat/runs/${encodeURIComponent(runId)}/stream`;
  },
  unifiedWebSocketUrl(token: string, host = window.location.host) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${host}/api/v1/unified-chat/ws?token=${encodeURIComponent(token)}`;
  },
  listSessions(params?: ChatSessionListParams) {
    return typed<ChatSessionSummary[]>(
      openApiV1.listChatSessions({ query: generatedQuery(params) }),
    );
  },
  createSession(platformId?: string) {
    return typed<ChatSessionSummary>(
      openApiV1.createChatSession({
        query: platformId ? { platform_id: platformId } : undefined,
      }),
    );
  },
  getSession(sessionId: string) {
    return typed<ChatSessionDetailData>(
      openApiV1.getChatSession({ path: { session_id: sessionId } }),
    );
  },
  updateSession(sessionId: string, payload: ChatSessionPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateChatSession({
        path: { session_id: sessionId },
        body: payload,
      }),
    );
  },
  deleteSession(sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteChatSession({ path: { session_id: sessionId } }),
    );
  },
  batchDeleteSessions(payload: ChatSessionBatchDeleteRequest) {
    return typed<ChatBatchDeleteData>(
      openApiV1.batchDeleteChatSessions({ body: payload }),
    );
  },
  stopSession(sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.stopChatSession({ path: { session_id: sessionId } }),
    );
  },
  updateMessage(
    sessionId: string,
    messageId: string | number,
    payload: ChatMessagePatchRequest,
  ) {
    return typed<ChatMessageMutationData>(
      openApiV1.updateChatMessage({
        path: { session_id: sessionId, message_id: String(messageId) },
        body: payload,
      }),
    );
  },
  regenerateMessage(
    sessionId: string,
    messageId: string | number,
    payload?: ChatMessageRegenerateRequest,
  ) {
    return typed<ChatMessageMutationData>(
      openApiV1.regenerateChatMessage({
        path: { session_id: sessionId, message_id: String(messageId) },
        body: payload,
      }),
    );
  },
  regenerateMessageUrl(sessionId: string, messageId: string | number) {
    return `/api/v1/chat/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(String(messageId))}/regenerate`;
  },
  createThread(payload: ChatThreadCreateRequest) {
    return typed<ChatThreadData>(openApiV1.createChatThread({ body: payload }));
  },
  getThread(threadId: string) {
    return typed<ChatThreadDetailData>(
      openApiV1.getChatThread({ path: { thread_id: threadId } }),
    );
  },
  deleteThread(threadId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteChatThread({ path: { thread_id: threadId } }),
    );
  },
  sendThreadMessage(threadId: string, payload: ChatThreadMessageRequest) {
    return typed<OpenConfig>(
      openApiV1.sendChatThreadMessage({
        path: { thread_id: threadId },
        body: payload,
      }),
    );
  },
  sendThreadMessageUrl(threadId: string) {
    return `/api/v1/chat/threads/${encodeURIComponent(threadId)}/messages`;
  },
  listProjects() {
    return typed<ProjectData[]>(openApiV1.listChatProjects());
  },
  createProject(payload: ChatProjectRequest) {
    return typed<ProjectData>(openApiV1.createChatProject({ body: payload }));
  },
  getProject(projectId: string) {
    return typed<ProjectData>(
      openApiV1.getChatProject({ path: { project_id: projectId } }),
    );
  },
  updateProject(projectId: string, payload: ChatProjectRequest) {
    return typed<ProjectData>(
      openApiV1.updateChatProject({
        path: { project_id: projectId },
        body: payload,
      }),
    );
  },
  deleteProject(projectId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteChatProject({ path: { project_id: projectId } }),
    );
  },
  listProjectSessions(projectId: string) {
    return typed<ChatSessionSummary[]>(
      openApiV1.listChatProjectSessions({ path: { project_id: projectId } }),
    );
  },
  addProjectSession(projectId: string, sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.addChatProjectSession({
        path: { project_id: projectId, session_id: sessionId },
      }),
    );
  },
  removeProjectSession(sessionId: string) {
    return typed<OpenConfig>(
      openApiV1.removeChatProjectSession({ path: { session_id: sessionId } }),
    );
  },
  listProjectWorkspaceFiles(projectId: string, path = '') {
    return typed<{
      path: string;
      entries: Array<{
        name: string;
        path: string;
        type: 'directory' | 'file';
        size: number;
        readable: boolean;
      }>;
    }>(
      openApiV1.listChatProjectWorkspaceFiles({
        path: { project_id: projectId },
        query: { path },
      }),
    );
  },
  previewProjectWorkspaceFile(projectId: string, path: string) {
    return typed<{
      path: string;
      content?: string;
      size: number;
      binary: boolean;
    }>(
      openApiV1.getChatProjectWorkspaceFile({
        path: { project_id: projectId },
        query: { path },
      }),
    );
  },
  downloadProjectWorkspaceFileUrl(projectId: string, path: string) {
    return `/api/v1/chat/projects/${encodeURIComponent(projectId)}/workspace/file/download?path=${encodeURIComponent(path)}`;
  },
};
