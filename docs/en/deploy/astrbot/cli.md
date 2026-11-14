# Deploy AstrBot from Source Code

> [!WARNING]
> You are deploying this project directly from source code. This tutorial requires you to have some technical background.
>
> This tutorial assumes Python is already installed on your device with version `>=3.12`


## Download/Clone Repository

If you have `git` installed on your computer, you can download the source code with the following command:

```bash
git clone https://github.com/AstrBotDevs/AstrBot.git
# The above code will pull the latest commit of the source code, if you need to pull the latest stable release version of the source code, you can use the following command:
# git clone --depth=1 --branch $(git ls-remote --tags --sort='-v:refname' https://github.com/AstrBotDevs/AstrBot.git | head -n1 | awk -F/ '{print $3}') https://github.com/AstrBotDevs/AstrBot.git
cd AstrBot
```

If you don't have `git` installed, please download and install it first.

Alternatively, download the source code directly from GitHub and extract it:

![image](https://files.astrbot.app/docs/source/images/cli/image.png)

## Install Dependencies and Run

::: details 【🥳Recommended】Use `uv` to Manage Dependencies

> If `uv` is not installed, please refer to [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) for installation.

2. Execute in terminal (in the AstrBot directory)
```bash
uv sync
uv run main.py
```

If you have installed some plugins, it is recommended to add the `--no-sync` parameter for subsequent startups to avoid reinstalling plugin dependencies. We are working on solving this issue, so stay tuned.

```bash
uv run --no-sync main.py
```
:::

::: details Install Dependencies with Python Built-in venv

In the AstrBot source code directory, run the following command in the terminal:

> If on Windows and you downloaded and extracted the source code directly, please open the extracted folder and enter in the address bar:
> ![image](https://files.astrbot.app/docs/source/images/cli/image-1.png)

```bash
python3 -m venv ./venv
```

> It might be `python` instead of `python3`
 
The above steps will create and activate a virtual environment (to avoid disrupting your local Python environment).

Next, install the dependencies with the following command, which may take some time:

Execute on Mac/Linux/WSL:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
python main.py
```

Execute on Windows:

```bash
venv\Scripts\activate
python -m pip install -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
python main.py
```
:::


## Optional PostgreSQL backend

SQLite remains the default. For the main application database, PostgreSQL can be selected at startup:

```bash
uv sync --extra postgres
export ASTRBOT_DATABASE_URL='postgresql://user:password@localhost:5432/astrbot'
uv run main.py
```

On PowerShell, set the variable with `$env:ASTRBOT_DATABASE_URL = 'postgresql://user:password@localhost:5432/astrbot'` before starting. For a pip installation, install `psycopg[binary]>=3.2,<4` in the same environment. Create the database and grant its account permission to create tables and indexes beforehand. URL-encode special characters in credentials.

The backend creates its schema on startup. Changing the URL does not copy an existing SQLite database: export an AstrBot backup first, stop the old instance, then restore the backup in the new instance. Keep the original database until the restored history is verified. Unset the variable to use SQLite again.

This setting covers the main database, including conversation events, preferences and display history. Knowledge-base storage, button callback tokens and local trace files retain their existing local storage. Plugins that use the database API remain compatible; plugins issuing SQLite-specific SQL or directly opening `data_v4.db` need adaptation. This does not enable multiple AstrBot instances to share runtime state.

Backend integration tests can use `ASTRBOT_TEST_POSTGRES_URL`; each test creates and removes its own schema, so use a dedicated test database whose account can create schemas.

## 🎉 All Done!

If everything goes well, you will see logs printed by AstrBot.

If there are no errors, you will see a log message similar to `🌈 Dashboard started, accessible at` with several links. Open one of the links to access the AstrBot dashboard. The link is `http://localhost:6185`.

> [!TIP]
> If you are deploying AstrBot on a server, you need to replace `localhost` with your server's IP address.
>
> New users must use the random password printed in the startup logs to log in for the first time. Use the username shown in the logs (usually `astrbot`) and change it after first login.


Next, you need to deploy any messaging platform to use AstrBot on that platform.
