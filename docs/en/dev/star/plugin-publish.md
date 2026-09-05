# Publishing Plugins to the Plugin Marketplace

After completing your plugin development, you can choose to publish it to the AstrBot Plugin Marketplace, allowing more users to benefit from your work.

AstrBot uses GitHub to host plugins, so you'll need to push your plugin code to the GitHub plugin repository you created earlier.

You can publish your plugin by visiting the [AstrBot Plugin Publish Page](https://cloud.astrbot.app/publish), You need to register an AstrBot Cloud account to publish plugins.

<!-- ![fill out the form](https://files.astrbot.app/docs/source/images/plugin-publish/image.png) -->

Here is a complete plugin metadata example (`metadata.yaml`) that the system will automatically parse:

```yaml
name: astrbot_plugin_example                 # Plugin identifier, English, unique
display_name: Plugin Display Name            # Plugin display name
# short_desc: A one-line summary of your plugin # (Optional) Short description for compact UI
desc: Detailed description of your plugin's features, usage, etc.  # Detailed plugin description
  Supports multi-line text with Markdown formatting.
version: 1.0.0                               # Plugin version (follow semantic versioning)
author: Author Name                          # Author name
repo: https://github.com/your-name/repo      # Plugin repository URL
# astrbot_version: ">=4.17.0"                # (Optional) AstrBot version range
# support_platforms:                         # (Optional) Supported platform adapter list
#   - aiocqhttp
#   - qq_official
# social_link: https://github.com/your-web   # (Optional) Your personal website, GitHub profile, etc.
# tags:                                      # (Optional) Tag list for marketplace categorization and search
  # - example
```

[Supported platform adapters](plugin-new.md#declare-supported-platforms-optional)

::: warning Size Limit
The plugin zip package submitted to the marketplace **must not exceed 16MB**.

If it exceeds this limit, the CI/CD pipeline will automatically reject the submission.
::: details To ensure your plugin passes review and publication smoothly, we recommend the following:

- **Compress static assets**: Compress images, audio, and other resource files in your plugin to reduce their size.
- **Clean up unnecessary files**: Avoid including directories like `.git`, `__pycache__`, `node_modules`, or development configuration files in your plugin repository. Add a `.gitignore` file to your repository root to exclude them.
- **Optimize dependency size**: If your plugin depends on large libraries, consider trimming them down or importing only what is needed.
- **Use `.gitattributes` or a release branch**: Reduce the zip package size by including only the files necessary for distribution.

If your plugin truly cannot be compressed to under 16MB due to business requirements, please contact the maintainer to manually bypass this limit.
:::
