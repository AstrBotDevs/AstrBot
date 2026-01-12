<template>
    <v-dialog v-model="showDialog" max-width="450px" persistent>
        <v-card>
            <v-card-title>
                <v-icon class="mr-2">mdi-folder-plus</v-icon>
                {{ tm('folder.createDialog.title') }}
            </v-card-title>
            <v-card-text>
                <v-form ref="form" v-model="formValid">
                    <v-text-field v-model="formData.name" :label="tm('folder.form.name')"
                        :rules="[v => !!v || tm('folder.validation.nameRequired')]" variant="outlined"
                        density="comfortable" autofocus class="mb-3" />

                    <v-textarea v-model="formData.description" :label="tm('folder.form.description')" variant="outlined"
                        rows="3" density="comfortable" hide-details />
                </v-form>
            </v-card-text>
            <v-card-actions>
                <v-spacer />
                <v-btn variant="text" @click="closeDialog">
                    {{ tm('buttons.cancel') }}
                </v-btn>
                <v-btn color="primary" variant="flat" @click="submitForm" :loading="loading" :disabled="!formValid">
                    {{ tm('buttons.create') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapActions } from 'pinia';

export default {
    name: 'CreateFolderDialog',
    props: {
        modelValue: {
            type: Boolean,
            default: false
        },
        parentFolderId: {
            type: String,
            default: null
        }
    },
    emits: ['update:modelValue', 'created', 'error'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    data() {
        return {
            formValid: false,
            loading: false,
            formData: {
                name: '',
                description: ''
            }
        };
    },
    computed: {
        showDialog: {
            get() {
                return this.modelValue;
            },
            set(value) {
                this.$emit('update:modelValue', value);
            }
        }
    },
    watch: {
        modelValue(newValue) {
            if (newValue) {
                this.resetForm();
            }
        }
    },
    methods: {
        ...mapActions(usePersonaStore, ['createFolder']),

        resetForm() {
            this.formData = {
                name: '',
                description: ''
            };
            if (this.$refs.form) {
                this.$refs.form.resetValidation();
            }
        },

        closeDialog() {
            this.showDialog = false;
        },

        async submitForm() {
            if (!this.formValid) return;

            this.loading = true;
            try {
                await this.createFolder({
                    name: this.formData.name,
                    description: this.formData.description || undefined,
                    parent_id: this.parentFolderId
                });
                this.$emit('created', this.tm('folder.messages.createSuccess'));
                this.closeDialog();
            } catch (error) {
                this.$emit('error', error.message || this.tm('folder.messages.createError'));
            } finally {
                this.loading = false;
            }
        }
    }
};
</script>
