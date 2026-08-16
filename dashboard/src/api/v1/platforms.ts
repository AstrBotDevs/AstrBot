import { botConfig, generatedQuery, openApiV1, typed } from './shared';
import type {
  BotActionRequest,
  BotRegistrationRequest,
  EnabledPatch,
} from './shared';
import type { BotListParams, BotRegistrationData, OpenConfig } from './types';

export const botApi = {
  types() {
    return typed<{ bot_types: OpenConfig[] }>(openApiV1.listBotTypes());
  },
  list(params?: BotListParams) {
    return typed<{ bots: OpenConfig[] }>(
      openApiV1.listBots({ query: generatedQuery(params) }),
    );
  },
  stats() {
    return typed<{ platforms: OpenConfig[] }>(openApiV1.listBotStats());
  },
  registration(botType: string, payload: BotRegistrationRequest) {
    return typed<BotRegistrationData>(
      openApiV1.registerBotType({
        path: { bot_type: botType },
        body: payload,
      }),
    );
  },
  create(config: OpenConfig, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.createBot({
        body: botConfig(config),
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  get(botId: string) {
    return typed<{ bot: OpenConfig }>(
      openApiV1.getBot({ path: { bot_id: botId } }),
    );
  },
  update(botId: string, config: OpenConfig, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.updateBot({
        path: { bot_id: botId },
        body: botConfig(config),
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  setEnabled(botId: string, payload: EnabledPatch, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.setBotEnabled({
        path: { bot_id: botId },
        body: payload,
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  invokeAction(botId: string, payload: BotActionRequest, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.invokeBotAction({
        path: { bot_id: botId },
        body: payload,
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
  delete(botId: string, stepUp?: string) {
    return typed<OpenConfig>(
      openApiV1.deleteBot({
        path: { bot_id: botId },
        headers: stepUp ? { 'X-AstrBot-Step-Up': stepUp } : undefined,
      }),
    );
  },
};
