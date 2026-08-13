import { generatedOptions, generatedQuery, openApiV1, typed } from './shared';
import type {
  AxiosRequestConfig,
  AxiosResponse,
  ConversationBatchDeleteRequest,
  ConversationExportRequest,
  ConversationMessagesReplaceRequest,
  ConversationPatchRequest,
  ListConversationsData,
} from './shared';
import type {
  ConversationBatchDeleteData,
  ConversationListResponseData,
  ConversationRecordData,
  OpenConfig,
} from './types';

type ListConversationsQuery = NonNullable<ListConversationsData['query']>;

export const conversationApi = {
  list(params?: ListConversationsQuery, requestConfig?: AxiosRequestConfig) {
    return typed<ConversationListResponseData>(
      openApiV1.listConversations(
        generatedOptions({ query: generatedQuery(params) }, requestConfig),
      ),
    );
  },
  get(userId: string, cid: string) {
    return typed<ConversationRecordData>(
      openApiV1.getConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
      }),
    );
  },
  update(userId: string, cid: string, payload: ConversationPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
        body: payload,
      }),
    );
  },
  replaceMessages(
    userId: string,
    cid: string,
    payload: ConversationMessagesReplaceRequest,
  ) {
    return typed<OpenConfig>(
      openApiV1.replaceConversationMessages({
        path: { conversation_id: cid },
        query: { user_id: userId },
        body: payload,
      }),
    );
  },
  delete(userId: string, cid: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConversation({
        path: { conversation_id: cid },
        query: { user_id: userId },
      }),
    );
  },
  batchDelete(payload: ConversationBatchDeleteRequest) {
    return typed<ConversationBatchDeleteData>(
      openApiV1.batchDeleteConversations({ body: payload }),
    );
  },
  export(payload: ConversationExportRequest, stepUp: string) {
    return openApiV1.exportConversations({
      body: payload,
      responseType: 'blob',
      headers: { 'X-AstrBot-Step-Up': stepUp },
    }) as Promise<AxiosResponse<Blob>>;
  },
};
