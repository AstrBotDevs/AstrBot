# Configure Custom Model Parameters

You can configure model parameters in the WebUI:

1. Open `Providers` and select the provider containing your model.
2. In its configured models list, click the model name or its settings icon to open the model configuration dialog.
3. Edit reasoning effort, temperature, Top-p, and the output token limit, or add other request parameters. Preset values shown in empty fields are suggestions and are omitted when saving.
4. Click `Save`.

Available fields depend on the provider. Refer to your provider's documentation for supported parameters and values.

For models supporting reasoning effort, `Reasoning Effort` appears before `Model context window size`.

The old **Model configuration → Custom request body parameters → Modify** dialog is now part of **Model configuration**. For native Gemini 3 and Gemini 4 models, set **Reasoning Effort** in each model's configuration. The provider-level **Thinking Level** setting has been removed. Leave **Reasoning Effort** blank or select `auto` to use the model's default.
