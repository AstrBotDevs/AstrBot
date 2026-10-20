# Installation via System Package Manager

> [!WARNING]
> Currently, only the AUR version is provided.
> If you are a Windows/macOS user, it is recommended to install via `uv`.
> If you are a Linux user, it is highly recommended to install via a package manager.

# Preparation

## What is AUR?
AUR (Arch User Repository) allows users to install software from community-maintained software repositories. AUR packages are typically maintained by community members rather than official maintainers.
Common AUR helpers include `yay` and `paru`.
The following tutorial uses `paru` as an example; `yay` works similarly, just replace `paru` with `yay`.

# Installation Process

## AUR
```bash
paru -S astrbot-git
# Note:
# The review step will begin; press 'q' to exit review and continue installation.
# After installation, the data directory is fixed at: ~/.local/share/astrbot
```

# Starting
>[!TIP]
> You can directly use `astrbot init` (for the first run) to initialize.
> Use `astrbot run` to run the bot.
> However, it is highly recommended to use `systemctl` for starting, as it provides features like automatic restart and log rotation.

```bash
systemctl --user start astrbot.service
```

# Auto-start on Boot
```bash
# For security reasons, it is designed to run as a user.
systemctl --user enable astrbot.service
# If you need to start it immediately, add --now
# systemctl --user enable --now astrbot.service
```
