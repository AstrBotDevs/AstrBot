# syntax=docker/dockerfile:1.7
# Runtime feature groups are selected with the BuildKit argument
# ASTRBOT_FEATURES. `full` expands to all groups; `minimal` keeps only the
# Python application and core shell utilities. Comma-separated group names may
# be used for a tailored image:
#   browser  Chromium and Playwright system libraries
#   documents  Pandoc, Poppler, and TeX
#   media  FFmpeg, ImageMagick, Ghostscript, and codecs
#   ocr  Tesseract language data
#   fonts  fontconfig and runtime font families
#   node  Node.js, npm, npx, and pnpm
#   docker  Docker CLI and Compose plugin
ARG ASTRBOT_FEATURES=full
ARG GITHUB_RELEASE_BASES="https://github.com https://ghproxy.net/https://github.com https://gh-proxy.com/https://github.com https://ghfast.top/https://github.com"
FROM python:3.14.6-slim@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144 AS builder
WORKDIR /AstrBot

ARG ASTRBOT_FEATURES
ARG GITHUB_RELEASE_BASES

# Enable pipefail so failures in install pipes abort the build.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV UV_INSTALL_DIR=/usr/local/bin \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    NVM_DIR=/root/.nvm \
    BASH_ENV=/root/.bash_env \
    PATH=/usr/local/cargo/bin:${PATH} \
    XDG_BIN_HOME=/usr/local/bin \
    UV_LINK_MODE=copy \
    SHFMT_VERSION=3.13.1 \
    HADOLINT_VERSION=2.14.0 \
    PLAYWRIGHT_VERSION=1.61.0 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    TYPST_VERSION=0.15.0 \
    YQ_VERSION=4.53.3 \
    QUARTO_VERSION=1.9.38 \
    PNPM_STORE_DIR=/pnpm/store \
    UV_CACHE_DIR=/root/.cache/uv \
    NPM_CONFIG_CACHE=/root/.npm \
    DEBIAN_FRONTEND=noninteractive \
    APT_LISTCHANGES_FRONTEND=none

COPY pyproject.toml requirements.txt .python-version ./
COPY dashboard/package.json dashboard/pnpm-lock.yaml /AstrBot/dashboard/
COPY docs/package.json docs/pnpm-lock.yaml /AstrBot/docs/
COPY .docker-local /tmp/docker-local

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    printf '%s\n' \
        'Acquire::Retries "5";' \
        'Acquire::Languages "none";' \
        'Acquire::PDiffs "false";' \
        'APT::Install-Recommends "0";' \
        'APT::Install-Suggests "0";' \
        'Dpkg::Use-Pty "0";' \
        >/etc/apt/apt.conf.d/99astrbot \
    && install -m 0755 -d /etc/apt/keyrings \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        eatmydata \
        gnupg \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && curl -fsSL https://downloads.claude.ai/keys/claude-code.asc \
        -o /etc/apt/keyrings/claude-code.asc \
    && chmod a+r /etc/apt/keyrings/claude-code.asc \
    && . /etc/os-release \
    && echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list \
    && echo \
        "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
        > /etc/apt/sources.list.d/claude-code.list \
    && eatmydata apt-get update \
    && eatmydata apt-get install -y --no-install-recommends \
        bash \
        bat \
        build-essential \
        claude-code \
        cmake \
        dnsutils \
        docker-ce-cli \
        docker-compose-plugin \
        eza \
        fd-find \
        ffmpeg \
        file \
        fontconfig \
        fonts-croscore \
        fonts-crosextra-caladea \
        fonts-crosextra-carlito \
        fonts-dejavu-core \
        fonts-dejavu-extra \
        fonts-freefont-otf \
        fonts-firacode \
        fonts-inter \
        fonts-liberation \
        fonts-liberation2 \
        fonts-noto-cjk \
        fonts-noto-color-emoji \
        fonts-noto-core \
        fonts-noto-extra \
        fonts-noto-mono \
        fonts-roboto \
        fonts-texgyre \
        fonts-texgyre-math \
        fonts-wqy-microhei \
        fonts-wqy-zenhei \
        fzf \
        gcc \
        ghostscript \
        gh \
        git \
        git-lfs \
        iproute2 \
        iputils-ping \
        imagemagick \
        jq \
        less \
        libavcodec-extra \
        libbz2-dev \
        libffi-dev \
        libgdbm-dev \
        libicu-dev \
        libjpeg62-turbo-dev \
        liblzma-dev \
        libmagic-dev \
        libncurses-dev \
        libpng-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        lmodern \
        lsof \
        latexmk \
        mtr-tiny \
        netcat-openbsd \
        ninja-build \
        openssh-client \
        pandoc \
        pkg-config \
        poppler-utils \
        procps \
        psmisc \
        python3-dev \
        ripgrep \
        rsync \
        shellcheck \
        sqlite3 \
        strace \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng \
        texlive-fonts-recommended \
        texlive-lang-chinese \
        texlive-latex-extra \
        texlive-latex-recommended \
        texlive-pictures \
        texlive-xetex \
        tree \
        unzip \
        vim-common \
        wget \
        xxd \
        zip \
        zlib1g-dev \
        zsh \
        biber \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && fc-cache -f \
    && git lfs install --system \
    && docker --version \
    && docker compose version \
    && rm -f /etc/apt/apt.conf.d/99astrbot

# Try the official release host first, then configured mirrors. Mirrors are a
# network fallback only; callers still validate every downloaded asset.
RUN <<'EOF'
cat > /usr/local/bin/download-github-release <<'SCRIPT'
#!/bin/bash
set -euo pipefail

path="$1"
output="$2"
kind="$3"
bases="$4"
tmp="${output}.part"

validate() {
    case "$1" in
        elf)
            file -b "$2" | grep -q 'ELF '
            ;;
        tar-gzip)
            tar -tzf "$2" >/dev/null
            ;;
        tar-xz)
            tar -tJf "$2" >/dev/null
            ;;
        deb)
            dpkg-deb --info "$2" >/dev/null
            ;;
        *)
            echo "Unsupported GitHub release asset type: $1" >&2
            return 2
            ;;
    esac
}

for base in ${bases}; do
    if [[ "$base" != https://* ]]; then
        echo "Refusing non-HTTPS GitHub release base: $base" >&2
        continue
    fi
    url="${base%/}/${path#/}"
    if curl --proto '=https' --tlsv1.2 --http1.1 -fsSL \
        --retry 5 --retry-all-errors --retry-delay 2 \
        --connect-timeout 30 "$url" -o "$tmp" \
        && test -s "$tmp" \
        && validate "$kind" "$tmp"; then
        mv "$tmp" "$output"
        exit 0
    fi
    echo "GitHub release download failed or failed validation: $url" >&2
    rm -f "$tmp"
done

echo "Unable to download a valid GitHub release asset: $path" >&2
exit 1
SCRIPT
chmod 0755 /usr/local/bin/download-github-release
EOF

RUN touch "${BASH_ENV}" \
    && echo '. "${BASH_ENV}"' >> ~/.bashrc \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.5/install.sh | PROFILE="${BASH_ENV}" bash \
    && source "${BASH_ENV}" \
    && nvm install 26.5.0 \
    && nvm alias default 26.5.0 \
    && npm install -g npm@12.0.2 pnpm@11.21.0 \
    && current_node_dir="$(dirname "$(dirname "$(nvm which current)")")" \
    && for tool in node npm npx pnpm; do \
        if [[ -x "${current_node_dir}/bin/${tool}" ]]; then \
            ln -sf "${current_node_dir}/bin/${tool}" "/usr/local/bin/${tool}"; \
        fi; \
    done \
    && node --version \
    && npm --version \
    && pnpm --version

RUN --mount=type=cache,target=/usr/local/cargo/registry,sharing=locked \
    --mount=type=cache,target=/usr/local/cargo/git,sharing=locked \
    curl --proto '=https' --tlsv1.2 -sSf \
    --retry 5 --retry-all-errors --retry-delay 2 --connect-timeout 30 \
    https://sh.rustup.rs | \
    sh -s -- -y --profile minimal --default-toolchain stable \
    && cargo --version \
    && arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) cargo_binstall_arch="x86_64-unknown-linux-musl" ;; \
        arm64) cargo_binstall_arch="aarch64-unknown-linux-musl" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac \
    && tmpdir="$(mktemp -d)" \
    && download-github-release \
        "cargo-bins/cargo-binstall/releases/latest/download/cargo-binstall-${cargo_binstall_arch}.tgz" \
        "${tmpdir}/cargo-binstall.tgz" tar-gzip "${GITHUB_RELEASE_BASES}" \
    && tar -C "$tmpdir" -xzf "${tmpdir}/cargo-binstall.tgz" \
    && install -m 0755 "$tmpdir/cargo-binstall" /usr/local/cargo/bin/cargo-binstall \
    && rm -rf "$tmpdir" \
    && cargo binstall --no-confirm \
        git-delta \
        du-dust \
        procs \
        tokei \
        hyperfine \
        sd \
        xh \
        tealdeer

RUN arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) shfmt_arch="linux_amd64"; hadolint_arch="Linux-x86_64" ;; \
        arm64) shfmt_arch="linux_arm64"; hadolint_arch="Linux-arm64" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac \
    && tmpdir="$(mktemp -d)" \
    && download-github-release \
        "mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_${shfmt_arch}" \
        "${tmpdir}/shfmt" elf "${GITHUB_RELEASE_BASES}" \
    && install -m 0755 "${tmpdir}/shfmt" /usr/local/bin/shfmt \
    && download-github-release \
        "hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-${hadolint_arch}" \
        "${tmpdir}/hadolint" elf "${GITHUB_RELEASE_BASES}" \
    && install -m 0755 "${tmpdir}/hadolint" /usr/local/bin/hadolint \
    && rm -rf "${tmpdir}" \
    && shfmt --version \
    && hadolint --version

RUN arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) yq_arch="amd64" ;; \
        arm64) yq_arch="arm64" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac \
    && tmpdir="$(mktemp -d)" \
    && download-github-release \
        "mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_${yq_arch}" \
        "${tmpdir}/yq" elf "${GITHUB_RELEASE_BASES}" \
    && install -m 0755 "${tmpdir}/yq" /usr/local/bin/yq \
    && rm -rf "${tmpdir}" \
    && yq --version

# GitHub release downloads can occasionally terminate TLS connections early.
RUN arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) typst_arch="x86_64-unknown-linux-musl" ;; \
        arm64) typst_arch="aarch64-unknown-linux-musl" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac \
    && tmpdir="$(mktemp -d)" \
    && download-github-release \
        "typst/typst/releases/download/v${TYPST_VERSION}/typst-${typst_arch}.tar.xz" \
        "${tmpdir}/typst.tar.xz" tar-xz "${GITHUB_RELEASE_BASES}" \
    && tar -xJf "${tmpdir}/typst.tar.xz" -C "${tmpdir}" \
    && install -m 0755 \
        "$(find "${tmpdir}" -type f -name typst | head -n 1)" \
        /usr/local/bin/typst \
    && rm -rf "${tmpdir}" \
    && typst --version

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) quarto_arch="amd64" ;; \
        arm64) quarto_arch="arm64" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac \
    && tmpdir="$(mktemp -d)" \
    && download-github-release \
        "quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-${quarto_arch}.deb" \
        "${tmpdir}/quarto.deb" deb "${GITHUB_RELEASE_BASES}" \
    && apt-get update \
    && eatmydata apt-get install -y --no-install-recommends "${tmpdir}/quarto.deb" \
    && rm -rf "${tmpdir}" \
    && quarto --version

RUN --mount=type=cache,target=/root/.cache,sharing=locked \
    curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv --version \
    && echo "3.14.6" > .python-version

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv pip install -r requirements.txt --no-cache-dir --system \
    && uv pip install socksio pilk --no-cache-dir --system

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv pip install \
        bandit[toml] \
        commitizen \
        pip-audit \
        pyright \
        pytest \
        pytest-asyncio \
        pytest-cov \
        radon \
        ruff \
        yamllint \
        --no-cache-dir --system

WORKDIR /AstrBot/dashboard
RUN --mount=type=cache,target=/pnpm/store,sharing=locked \
    pnpm fetch --trust-lockfile

WORKDIR /AstrBot/docs
RUN --mount=type=cache,target=/pnpm/store,sharing=locked \
    pnpm fetch --trust-lockfile

WORKDIR /AstrBot

COPY . /AstrBot/

RUN curl https://mise.run | sh \
    && ln -sf /root/.local/bin/mise /usr/local/bin/mise \
    && mise --version

RUN claude --version

RUN npm install -g @openai/codex --no-fund --no-audit \
    && current_node_dir="$(dirname "$(dirname "$(nvm which current)")")" \
    && test -x "${current_node_dir}/bin/codex" \
    && ln -sf "${current_node_dir}/bin/codex" /usr/local/bin/codex \
    && codex --version

RUN cp -a /tmp/docker-local/. /root/

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    if [[ "${ASTRBOT_FEATURES}" == "full" || ",${ASTRBOT_FEATURES}," == *,browser,* ]]; then \
        uv pip install "playwright==${PLAYWRIGHT_VERSION}" --no-cache-dir --system \
        && PLAYWRIGHT_NODEJS_PATH=/usr/local/bin/node \
           PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000 \
           playwright install --with-deps chromium; \
    else \
        mkdir -p /ms-playwright; \
    fi

RUN arch="$(dpkg --print-architecture)" \
    && case "${arch}" in \
        amd64) powershell_arch="x64" ;; \
        arm64) powershell_arch="arm64" ;; \
        *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac \
    && mkdir -p /opt/microsoft/powershell/7 \
    && tmpdir="$(mktemp -d)" \
    && download-github-release \
        "PowerShell/PowerShell/releases/download/v7.6.3/powershell-7.6.3-linux-${powershell_arch}.tar.gz" \
        "${tmpdir}/powershell.tar.gz" tar-gzip "${GITHUB_RELEASE_BASES}" \
    && tar -xzf "${tmpdir}/powershell.tar.gz" -C /opt/microsoft/powershell/7 \
    && rm -rf "${tmpdir}" \
    && chmod +x /opt/microsoft/powershell/7/pwsh \
    && ln -sf /opt/microsoft/powershell/7/pwsh /usr/local/bin/pwsh \
    && ln -sf /opt/microsoft/powershell/7/pwsh /usr/local/bin/powershell \
    && pwsh -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()' \
    && pwsh -NoLogo -NoProfile -Command "Set-PSRepository PSGallery -InstallationPolicy Trusted; Install-Module PSScriptAnalyzer -Scope AllUsers -Force -SkipPublisherCheck" \
    && pwsh -NoLogo -NoProfile -Command "Get-Module -ListAvailable PSScriptAnalyzer | Select-Object -First 1 Name, Version"

WORKDIR /AstrBot/dashboard
RUN --mount=type=cache,target=/pnpm/store,sharing=locked \
    pnpm install --frozen-lockfile --offline --prefer-offline --trust-lockfile \
    && pnpm build \
    && rm -rf /AstrBot/astrbot/dashboard/dist \
    && mkdir -p /AstrBot/astrbot/dashboard \
    && cp -r dist /AstrBot/astrbot/dashboard/

WORKDIR /AstrBot/docs
RUN --mount=type=cache,target=/pnpm/store,sharing=locked \
    CI=true pnpm install --frozen-lockfile --offline --prefer-offline --trust-lockfile

WORKDIR /AstrBot

RUN mkdir -p /etc/profile.d \
    && cat <<'EOF' >/etc/profile.d/astrbot-dev-tools.sh
export PATH=/usr/local/cargo/bin:$PATH
export NVM_DIR=/root/.nvm
if [ -s "$NVM_DIR/nvm.sh" ]; then
  . "$NVM_DIR/nvm.sh"
fi
alias fd='fdfind'
alias bat='batcat'
if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate bash)"
fi
export PATH="$HOME/.local/bin:$PATH"
if [ -S /var/run/docker.sock ]; then
  export DOCKER_HOST="${DOCKER_HOST:-unix:///var/run/docker.sock}"
fi
EOF

FROM builder AS runtime-assets

ARG ASTRBOT_FEATURES

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN set -eux; \
    features="${ASTRBOT_FEATURES}"; \
    case "${features}" in \
        full) features="browser,documents,media,ocr,fonts,node,docker" ;; \
        minimal) features="" ;; \
    esac; \
    for feature in ${features//,/ }; do \
        case "${feature}" in \
            browser|documents|media|ocr|fonts|node|docker) ;; \
            *) echo "Unknown AstrBot feature: ${feature}" >&2; exit 1 ;; \
        esac; \
    done; \
    mkdir -p \
        /opt/astrbot/runtime-assets/bin \
        /opt/astrbot/runtime-assets/docker-config/cli-plugins \
        /opt/astrbot/runtime-assets/ms-playwright \
        /opt/astrbot/runtime-assets/nvm; \
    install -m 0755 /usr/local/bin/uv /opt/astrbot/runtime-assets/bin/uv; \
    install -m 0755 /usr/local/bin/playwright /opt/astrbot/runtime-assets/bin/playwright; \
    if [[ ",${features}," == *,node,* ]]; then \
        cp -a /root/.nvm/. /opt/astrbot/runtime-assets/nvm/; \
    fi; \
    if [[ ",${features}," == *,docker,* ]]; then \
        install -m 0755 /usr/bin/docker /opt/astrbot/runtime-assets/bin/docker; \
        install -m 0755 \
            /usr/libexec/docker/cli-plugins/docker-compose \
            /opt/astrbot/runtime-assets/docker-config/cli-plugins/docker-compose; \
    fi; \
    if [[ ",${features}," == *,browser,* ]]; then \
        cp -a /ms-playwright/. /opt/astrbot/runtime-assets/ms-playwright/; \
    fi

FROM builder AS dev

EXPOSE 6185

CMD ["python", "main.py"]

# Keep the development image above separate from the production runtime. The
# runtime copies only the application, installed Python packages, browser
# assets, and the Node/uv tools needed by runtime MCP integrations.
FROM python:3.14.6-slim@sha256:7bec7ddcddeff7975d6ba9b4be7dd6f6b2f55e7491539145e2978f7f97ce9144 AS runtime

WORKDIR /AstrBot

ARG ASTRBOT_FEATURES

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/astrbot/runtime-assets/ms-playwright \
    DOCKER_CONFIG=/opt/astrbot/runtime-assets/docker-config \
    NVM_DIR=/opt/astrbot/runtime-assets/nvm \
    PATH=/opt/astrbot/runtime-assets/bin:/opt/astrbot/runtime-assets/nvm/versions/node/v26.5.0/bin:/usr/local/bin:${PATH} \
    UV_LINK_MODE=copy \
    UV_INSTALL_DIR=/usr/local/bin \
    HOME=/root

COPY --from=runtime-assets /opt/astrbot/runtime-assets/ /opt/astrbot/runtime-assets/

COPY --from=builder /usr/local/lib/python3.14/site-packages/ \
    /usr/local/lib/python3.14/site-packages/

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    features="${ASTRBOT_FEATURES}" \
    && case "${features}" in \
        full) features="browser,documents,media,ocr,fonts,node,docker" ;; \
        minimal) features="" ;; \
    esac \
    && for feature in ${features//,/ }; do \
        case "${feature}" in \
            browser|documents|media|ocr|fonts|node|docker) ;; \
            *) echo "Unknown AstrBot feature: ${feature}" >&2; exit 1 ;; \
        esac; \
    done \
    && apt_packages="bash ca-certificates curl file git jq openssh-client procps psmisc ripgrep sqlite3 unzip wget xxd zip" \
    && if [[ ",${features}," == *,media,* ]]; then \
        apt_packages="${apt_packages} ffmpeg ghostscript imagemagick libavcodec-extra libmagic1"; \
    fi \
    && if [[ ",${features}," == *,documents,* ]]; then \
        apt_packages="${apt_packages} lmodern pandoc poppler-utils texlive-fonts-recommended texlive-lang-chinese texlive-latex-extra texlive-latex-recommended texlive-pictures texlive-xetex"; \
    fi \
    && if [[ ",${features}," == *,ocr,* ]]; then \
        apt_packages="${apt_packages} tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng"; \
    fi \
    && if [[ ",${features}," == *,fonts,* ]]; then \
        apt_packages="${apt_packages} fontconfig fonts-croscore fonts-crosextra-caladea fonts-crosextra-carlito fonts-dejavu-core fonts-dejavu-extra fonts-freefont-otf fonts-firacode fonts-inter fonts-liberation fonts-liberation2 fonts-noto-cjk fonts-noto-color-emoji fonts-noto-core fonts-noto-extra fonts-noto-mono fonts-roboto fonts-texgyre fonts-texgyre-math fonts-wqy-microhei fonts-wqy-zenhei"; \
    fi \
    && read -r -a apt_package_array <<< "${apt_packages}" \
    && apt-get update \
    && apt-get install -y --no-install-recommends "${apt_package_array[@]}" \
    && if [[ ",${features}," == *,browser,* ]]; then \
        playwright install-deps chromium; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /AstrBot/astrbot /AstrBot/astrbot
COPY --from=builder /AstrBot/main.py /AstrBot/runtime_bootstrap.py \
    /AstrBot/pyproject.toml /AstrBot/requirements.txt /AstrBot/.python-version /AstrBot/

EXPOSE 6185

CMD ["python", "main.py"]
