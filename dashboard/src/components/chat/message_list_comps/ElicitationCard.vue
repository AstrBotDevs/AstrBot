<template>
    <div class="elicitation-card" :class="{ 'is-dark': isDark, 'is-disabled': !interactive || submitted }">
        <div class="elicitation-header">
            <v-icon size="18" class="me-2">mdi-form-select</v-icon>
            <span class="elicitation-title">
                {{ tm('elicitation.title', { server: payload.server_name || 'MCP' }) }}
            </span>
        </div>

        <p v-if="payload.message" class="elicitation-message">{{ payload.message }}</p>
        <p v-else-if="payload.prompt" class="elicitation-message">{{ payload.prompt }}</p>

        <template v-if="payload.kind === 'url'">
            <a
                v-if="payload.url"
                :href="payload.url"
                target="_blank"
                rel="noopener noreferrer"
                class="elicitation-link"
            >
                {{ payload.url }}
            </a>

            <div class="elicitation-actions">
                <v-btn
                    size="small"
                    variant="tonal"
                    color="primary"
                    :disabled="!interactive || submitting || submitted"
                    @click="submitSimpleReply('done', tm('elicitation.done'))"
                >
                    {{ tm('elicitation.done') }}
                </v-btn>
                <v-btn
                    size="small"
                    variant="text"
                    color="warning"
                    :disabled="!interactive || submitting || submitted"
                    @click="submitSimpleReply('decline', tm('elicitation.decline'))"
                >
                    {{ tm('elicitation.decline') }}
                </v-btn>
                <v-btn
                    size="small"
                    variant="text"
                    color="grey-darken-1"
                    :disabled="!interactive || submitting || submitted"
                    @click="submitSimpleReply('cancel', tm('elicitation.cancel'))"
                >
                    {{ tm('elicitation.cancel') }}
                </v-btn>
            </div>
        </template>

        <template v-else>
            <div
                v-for="field in payload.fields || []"
                :key="field.name"
                class="elicitation-field"
            >
                <div class="field-title-row">
                    <span class="field-title">{{ field.label || field.name }}</span>
                    <span v-if="field.required" class="field-required">*</span>
                </div>
                <div v-if="field.description" class="field-description">
                    {{ field.description }}
                </div>

                <div v-if="field.enum && field.enum.length" class="field-options">
                    <v-btn
                        v-for="option in field.enum"
                        :key="`${field.name}-${option}`"
                        size="small"
                        :variant="selectedOption[field.name] === option && !customInput[field.name]?.trim() ? 'tonal' : 'outlined'"
                        color="primary"
                        :disabled="!interactive || submitting || submitted"
                        @click="selectOption(field.name, option)"
                    >
                        {{ option }}
                    </v-btn>
                </div>

                <v-switch
                    v-if="field.type === 'boolean' && !(field.enum && field.enum.length)"
                    v-model="booleanInput[field.name]"
                    color="primary"
                    hide-details
                    inset
                    :label="tm('elicitation.booleanLabel')"
                    :disabled="!interactive || submitting || submitted"
                />

                <v-textarea
                    v-else-if="field.type === 'array'"
                    v-model="customInput[field.name]"
                    :label="field.enum && field.enum.length ? tm('elicitation.otherInput') : field.label || field.name"
                    :placeholder="tm('elicitation.arrayPlaceholder')"
                    auto-grow
                    rows="2"
                    variant="outlined"
                    hide-details="auto"
                    class="mt-2"
                    :disabled="!interactive || submitting || submitted"
                />

                <v-text-field
                    v-else
                    v-model="customInput[field.name]"
                    :label="field.enum && field.enum.length ? tm('elicitation.otherInput') : field.label || field.name"
                    variant="outlined"
                    hide-details="auto"
                    class="mt-2"
                    :disabled="!interactive || submitting || submitted"
                />
            </div>

            <div class="elicitation-actions">
                <v-btn
                    size="small"
                    variant="tonal"
                    color="primary"
                    :disabled="!interactive || submitting || submitted"
                    @click="submitFormReply"
                >
                    {{ tm('elicitation.submit') }}
                </v-btn>
                <v-btn
                    size="small"
                    variant="text"
                    color="grey-darken-1"
                    :disabled="!interactive || submitting || submitted"
                    @click="submitSimpleReply('cancel', tm('elicitation.cancel'))"
                >
                    {{ tm('elicitation.cancel') }}
                </v-btn>
            </div>
        </template>

        <div v-if="statusText" class="elicitation-status">
            {{ statusText }}
        </div>
    </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';

import { useModuleI18n } from '@/i18n/composables';
import { useToast } from '@/utils/toast';

import type { ElicitationField, ElicitationPayload } from '@/composables/useMessages';

interface Props {
    payload: ElicitationPayload;
    isDark?: boolean;
    interactive?: boolean;
    submitElicitation?: (replyText: string, displayText: string) => Promise<void>;
}

const props = withDefaults(defineProps<Props>(), {
    isDark: false,
    interactive: false,
    submitElicitation: undefined
});

const { tm } = useModuleI18n('features/chat');
const { error: showError, success: showSuccess } = useToast();

const customInput = reactive<Record<string, string>>({});
const selectedOption = reactive<Record<string, string>>({});
const booleanInput = reactive<Record<string, boolean>>({});
const submitting = ref(false);
const submitted = ref(false);
const statusText = ref('');

function selectOption(fieldName: string, option: string) {
    selectedOption[fieldName] = option;
    customInput[fieldName] = '';
}

function getFieldValue(field: ElicitationField): string | boolean | undefined {
    if (field.type === 'boolean' && !(field.enum && field.enum.length)) {
        return booleanInput[field.name];
    }

    const customValue = (customInput[field.name] || '').trim();
    if (customValue) {
        return customValue;
    }

    const optionValue = (selectedOption[field.name] || '').trim();
    if (optionValue) {
        return optionValue;
    }

    return undefined;
}

function buildFormReply(): { replyText: string; displayText: string } {
    const fields = props.payload.fields || [];
    if (!fields.length) {
        return {
            replyText: 'accept',
            displayText: tm('elicitation.accepted')
        };
    }

    const formPayload: Record<string, string | boolean> = {};
    for (const field of fields) {
        const value = getFieldValue(field);
        if (value === undefined || value === '') {
            if (field.required) {
                throw new Error(tm('elicitation.requiredField', { field: field.label || field.name }));
            }
            continue;
        }
        formPayload[field.name] = value;
    }

    if (!Object.keys(formPayload).length) {
        throw new Error(tm('elicitation.emptyReply'));
    }

    if (Object.keys(formPayload).length === 1) {
        const [fieldName, value] = Object.entries(formPayload)[0];
        return {
            replyText: String(value),
            displayText: `${fieldName}: ${String(value)}`
        };
    }

    return {
        replyText: JSON.stringify(formPayload),
        displayText: Object.entries(formPayload)
            .map(([fieldName, value]) => `${fieldName}: ${String(value)}`)
            .join('\n')
    };
}

async function submitSimpleReply(replyText: string, displayText: string) {
    if (!props.submitElicitation || !props.interactive || submitting.value || submitted.value) {
        return;
    }

    submitting.value = true;
    try {
        await props.submitElicitation(replyText, displayText);
        submitted.value = true;
        statusText.value = tm('elicitation.submitted');
        showSuccess(tm('elicitation.submitted'));
    } catch (err) {
        console.error('Failed to submit elicitation reply:', err);
        showError(tm('elicitation.submitFailed'));
    } finally {
        submitting.value = false;
    }
}

async function submitFormReply() {
    try {
        const { replyText, displayText } = buildFormReply();
        await submitSimpleReply(replyText, displayText);
    } catch (err) {
        const message = err instanceof Error ? err.message : tm('elicitation.submitFailed');
        showError(message);
    }
}
</script>

<style scoped>
.elicitation-card {
    border: 1px solid rgba(82, 106, 220, 0.18);
    border-radius: 16px;
    padding: 14px;
    margin: 10px 0;
    background: linear-gradient(180deg, rgba(82, 106, 220, 0.08), rgba(82, 106, 220, 0.03));
}

.elicitation-card.is-dark {
    border-color: rgba(129, 164, 255, 0.22);
    background: linear-gradient(180deg, rgba(129, 164, 255, 0.14), rgba(129, 164, 255, 0.05));
}

.elicitation-card.is-disabled {
    opacity: 0.8;
}

.elicitation-header {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
    font-weight: 600;
}

.elicitation-title {
    line-height: 1.3;
}

.elicitation-message {
    margin: 0 0 10px;
    white-space: pre-wrap;
    line-height: 1.5;
}

.elicitation-link {
    display: inline-flex;
    margin-bottom: 12px;
    word-break: break-all;
}

.elicitation-field {
    margin-top: 12px;
}

.field-title-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
}

.field-required {
    color: rgb(var(--v-theme-error));
}

.field-description {
    margin-top: 4px;
    font-size: 13px;
    opacity: 0.76;
    white-space: pre-wrap;
}

.field-options {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
}

.elicitation-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 14px;
}

.elicitation-status {
    margin-top: 10px;
    font-size: 13px;
    opacity: 0.72;
}
</style>
