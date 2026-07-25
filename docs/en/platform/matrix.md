# Connecting to Matrix

> [!TIP]
> This platform adapter is maintained by the community ([stevessr](https://github.com/stevessr)). If you find it helpful, please support the developer by giving the repository a Star. ❤️

## Deploying a Matrix Server

Matrix is an IM protocol with a rich set of server implementations.

Please refer to [Matrix Server](https://matrix.org/ecosystem/servers/) to view available server implementations.

## Supported Message Types

| Message Type | Receive | Send | Notes |
| ------------ | ------- | ---- | ----- |
| Text         | Yes     | Yes  |       |
| Image*       | Yes     | Yes  |       |
| Audio*       | Yes     | Yes  |       |
| Video*       | Yes     | Yes  |       |
| File*        | Yes     | Yes  |       |
| Poll         | Yes     | No   |       |

\*: Will be persisted locally. The plugin will clean up according to configuration. Files will be uploaded before sending; uploads exceeding the server's size limit will fail.

## Installing the astrbot_plugin_matrix_adapter Plugin

Go to the AstrBot WebUI plugin marketplace, search for `astrbot_plugin_matrix_adapter`, and click Install.

After installation, navigate to Messaging Platforms (older versions: `Bot`) → Add Adapter → Select Matrix (if the option is missing, try restarting AstrBot or check the plugin installation status).

Click `Enable` in the configuration dialog that appears.

## Configuration

- **`matrix_homeserver` (required)**: The full URL of your Matrix server instance, supports delegation-based auto-discovery. For example, the official instance: `https://matrix.org`
- **`matrix_user_id`**: Your full Matrix username, e.g. `@username:homeserver.com`
- **`matrix_auth_method` (required)**: Your login method. Options: `password`, `token`, `oauth2`, `qr`. It is recommended to use `password` or `oauth2/qr` mode (in oauth2/qr mode, please ensure the device used for authentication/scanning can reach the public address configured in AstrBot)

For more configuration options, please refer to the repository's [README.md](https://github.com/stevessr/astrbot_plugin_matrix_adapter?tab=readme-ov-file#astrbot-matrix-adapter-%E6%8F%92%E4%BB%B6).

## Issue Reporting

If you have any questions, please submit an issue to the [plugin repository](https://github.com/stevessr/astrbot_plugin_matrix_adapter/issues).
