<template>
    <BaseCreateFolderDialog v-model="showDialog" :parent-folder-id="parentFolderId" :labels="labels"
        @create="handleCreate" ref="baseDialog" />
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapActions } from 'pinia';
import BaseCreateFolderDialog from '@/components/folder/BaseCreateFolderDialog.vue';
import type { CreateFolderData } from '@/components/folder/types';

export default defineComponent({
    name: 'CreateFolderDialog',
    components: {
        BaseCreateFolderDialog
    },
    props: {
        modelValue: {
            type: Boolean,
            default: false
        },
        parentFolderId: {
            type: String as PropType<string | null>,
            default: null
        }
    },
    emits: ['update:modelValue', 'created', 'error'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    computed: {
        showDialog: {
            get(): boolean {
                return this.modelValue;
            },
            set(value: boolean) {
                this.$emit('update:modelValue', value);
            }
        },
        labels() {
            return {
                title: this.tm('folder.createDialog.title'),
                nameLabel: this.tm('folder.form.name'),
                descriptionLabel: this.tm('folder.form.description'),
                nameRequired: this.tm('folder.validation.nameRequired'),
                cancelButton: this.tm('buttons.cancel'),
                createButton: this.tm('folder.createDialog.createButton')
            };
        }
    },
    methods: {
        ...mapActions(usePersonaStore, ['createFolder']),

        async handleCreate(data: CreateFolderData) {
            const baseDialog = this.$refs.baseDialog as InstanceType<typeof BaseCreateFolderDialog>;
            baseDialog.setLoading(true);
            
            try {
                await this.createFolder({
                    name: data.name,
                    description: data.description,
                    parent_id: data.parent_id
                });
                this.$emit('created', this.tm('folder.messages.createSuccess'));
                this.showDialog = false;
            } catch (error: any) {
                this.$emit('error', error.message || this.tm('folder.messages.createError'));
            } finally {
                baseDialog.setLoading(false);
            }
        }
    }
});
</script>
