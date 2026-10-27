# Configure Custom Model Parameters

You can configure model parameters in the WebUI:

1. Open `Providers` and select the provider containing your model.
2. In its configured models list, click the model name or its settings icon to open the model configuration dialog.
3. Under `Custom request body parameters` (`custom_extra_body`), add the parameters required by your model, such as `temperature`, `top_p`, or `max_tokens`.
4. Click `Save`.

Available fields depend on the provider. For example, Gemini exposes its own generation settings instead of the generic `custom_extra_body` field. Refer to your provider's documentation for supported parameters and values.
