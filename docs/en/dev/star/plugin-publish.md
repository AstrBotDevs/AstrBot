# Publishing Plugins to the Plugin Marketplace

After completing your plugin development, you can choose to publish it to the AstrBot Plugin Marketplace, allowing more users to benefit from your work.

AstrBot uses GitHub to host plugins, so you'll need to push your plugin code to the GitHub plugin repository you created earlier.

You can submit your plugin by visiting the [AstrBot Plugin Marketplace](https://plugins.astrbot.app). Once on the website, click the `+` button in the bottom-right corner, fill in the basic information, author details, repository information, and other required fields. Then click the `Submit to GITHUB` button. You will be redirected to the AstrBot repository's Issue submission page. Please verify that all information is correct, then click the `Create` button to complete the plugin publication process.

![fill out the form](https://files.astrbot.app/docs/source/images/plugin-publish/image.png)

> ⚠️ **Size Limit**: The plugin zip package submitted to the marketplace **must not exceed 16MB**. If it exceeds this limit, the CI/CD pipeline will automatically reject the submission.
>
> To ensure your plugin passes review and publication smoothly, we recommend the following:
>
> - **Compress static assets**: Compress images, audio, and other resource files in your plugin to reduce their size.
> - **Clean up unnecessary files**: Avoid including directories like `.git`, `__pycache__`, `node_modules`, or development configuration files in your plugin repository. Add a `.gitignore` file to your repository root to exclude them.
> - **Optimize dependency size**: If your plugin depends on large libraries, consider trimming them down or importing only what is needed.
> - **Use `.gitattributes` or a release branch**: Reduce the zip package size by including only the files necessary for distribution.
>
> If your plugin truly cannot be compressed to under 16MB due to business requirements, please contact the maintainer to manually bypass this limit.
