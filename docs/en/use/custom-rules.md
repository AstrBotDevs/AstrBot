# Custom Rules

> [!NOTE]
> The "unified message origin" mentioned below refers to UMO. A UMO uniquely identifies a specific conversation on a messaging platform.

Since version v4.7.0, we have refactored AstrBot's original "Session Management" feature into the "Custom Rules" feature to reduce conflicts with configuration files.

You can think of custom rules as more flexible, mandatory processing rules for specified message sources, which have higher priority than configuration files.

For example, if a messaging platform originally uses the "default" configuration file, all conversations under this platform are processed according to the rules in the configuration file. If you want to apply special processing to a specific session source A, previously you would need to create a separate configuration file and bind A to it. Now, you simply need to create a custom rule in the WebUI's Custom Rules page and select message source A. You can define the following rules:

1. Whether to enable message processing for this unified message origin. If disabled, the effect is equivalent to blacklisting this unified message origin.
2. Whether to enable LLM for messages from this unified message origin. If disabled, AI capabilities will not be used.
3. Whether to enable TTS for messages from this unified message origin. If disabled, TTS capabilities will not be used.
4. Configure specific chat models, speech recognition models (STT), and text-to-speech models (TTS) for this unified message origin.
5. Configure a specific persona for this unified message origin.

