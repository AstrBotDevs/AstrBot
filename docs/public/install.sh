#!/usr/bin/env bash
# Install AstrBot with uv on Linux / macOS / WSL. Compatible with Bash 3.2+.

set -euo pipefail

language=''
download_source=''
uv_download_base_url=''
pypi_index_url=''
python_install_mirror=''
non_interactive=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --language|--download-source|--uv-download-base-url|--pypi-index-url|--python-install-mirror)
      if [ "$#" -lt 2 ] || [[ "$2" == --* ]] || [ -z "$2" ]; then
        printf 'Missing value for %s\n' "$1" >&2
        exit 2
      fi
      case "$1" in
        --language) language="$2" ;;
        --download-source) download_source="$2" ;;
        --uv-download-base-url) uv_download_base_url="$2" ;;
        --pypi-index-url) pypi_index_url="$2" ;;
        --python-install-mirror) python_install_mirror="$2" ;;
      esac
      shift 2
      ;;
    --non-interactive) non_interactive=1; shift ;;
    --help|-h)
      cat <<'HELP'
Usage: bash install.sh [options]
  --language zh-CN|en-US|ja-JP
  --download-source china|official|custom
  --uv-download-base-url HTTPS-URL   Directory containing uv archives and .sha256 files
  --pypi-index-url HTTPS-URL         PyPI simple index for custom sources
  --python-install-mirror HTTPS-URL  Optional Python interpreter download mirror
  --non-interactive                 Skip all menus (defaults: system language, official sources)
HELP
      exit 0
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RED=$'\033[0;31m'
  GREEN=$'\033[0;32m'
  YELLOW=$'\033[1;33m'
  CYAN=$'\033[0;36m'
  NC=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi

info() { printf '%s[INFO]%s %s\n' "$CYAN" "$NC" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$YELLOW" "$NC" "$*"; }
ok() { printf '%s[OK]%s %s\n' "$GREEN" "$NC" "$*"; }
err() { printf '%s[ERROR]%s %s\n' "$RED" "$NC" "$*" >&2; }
has() { command -v "$1" >/dev/null 2>&1; }

# Read menus from the terminal, never from the script stream in curl | bash.
can_prompt=0
if [ "$non_interactive" -eq 0 ]; then
  if [ -t 0 ]; then
    exec 3<&0
    can_prompt=1
  elif { exec 3</dev/tty; } 2>/dev/null; then
    can_prompt=1
  fi
fi

if [ -z "$language" ]; then
  case "${LC_ALL:-${LC_MESSAGES:-${LANG:-en_US}}}" in
    zh*) language='zh-CN'; default_choice=1 ;;
    ja*) language='ja-JP'; default_choice=3 ;;
    *) language='en-US'; default_choice=2 ;;
  esac
  if [ "$can_prompt" -eq 1 ]; then
    printf '\n请选择语言 / Select language / 言語を選択してください\n  1. 简体中文\n  2. English\n  3. 日本語\n' >&2
    while :; do
      printf '1-3 [%s]: ' "$default_choice" >&2
      IFS= read -r choice <&3 || exit 1
      case "${choice:-$default_choice}" in
        1) language='zh-CN'; break ;;
        2) language='en-US'; break ;;
        3) language='ja-JP'; break ;;
      esac
    done
  fi
fi
case "$language" in
  zh-CN|en-US|ja-JP) ;;
  *) err "Unsupported language: $language"; exit 2 ;;
esac

message() {
  local key="$1" format
  shift
  case "$language:$key" in
    zh-CN:ChooseSource) format='请选择下载源' ;;
    zh-CN:China) format='中国大陆加速下载镜像源' ;;
    zh-CN:Official) format='官方源' ;;
    zh-CN:Custom) format='自定义' ;;
    zh-CN:Choice) format='输入编号，按回车使用默认选项' ;;
    zh-CN:InvalidChoice) format='请输入 1、2 或 3。' ;;
    zh-CN:UvUrl) format='uv tar.gz 下载目录 URL（不含文件名）' ;;
    zh-CN:PypiUrl) format='PyPI simple 索引 URL' ;;
    zh-CN:CustomRequired) format='自定义源需要同时提供 --uv-download-base-url 和 --pypi-index-url。' ;;
    zh-CN:InvalidUrl) format='下载源必须是有效的 HTTPS URL：%s' ;;
    zh-CN:Source) format='下载源：%s' ;;
    zh-CN:UvMirror) format='uv 下载目录：%s' ;;
    zh-CN:Pypi) format='PyPI 索引：%s' ;;
    zh-CN:PythonMirror) format='Python 下载镜像：%s' ;;
    zh-CN:PythonDefault) format='Python 下载沿用 uv 的配置；如需加速，可通过 --python-install-mirror 指定镜像（PyPI 镜像不包含 Python 解释器）。' ;;
    zh-CN:InstallingUv) format='未找到 uv，正在安装…' ;;
    zh-CN:TryingMirror) format='正在尝试 uv 镜像：%s' ;;
    zh-CN:MirrorFailed) format='uv 镜像下载失败：%s' ;;
    zh-CN:OfficialFallback) format='正在尝试 uv 官方安装器…' ;;
    zh-CN:UnsupportedPlatform) format='当前平台无法使用预设 uv 镜像，将尝试官方安装器：%s' ;;
    zh-CN:InvalidChecksum) format='uv 压缩包 SHA256 校验失败。' ;;
    zh-CN:MissingBinaries) format='uv 压缩包中缺少 uv 或 uvx。' ;;
    zh-CN:MissingTools) format='需要 curl 或 wget 下载文件；镜像安装还需要 tar 和 sha256sum 或 shasum。' ;;
    zh-CN:PathHint) format='uv 安装目录：%s。请确保新终端的 PATH 中包含此目录。' ;;
    zh-CN:UvFailed) format='uv 安装失败。请参考 https://docs.astral.sh/uv/getting-started/installation/' ;;
    zh-CN:InstallingAstrBot) format='正在使用 Python 3.12 安装 AstrBot…' ;;
    zh-CN:AstrBotFailed) format='AstrBot 安装失败（退出码 %s）。请检查上方的下载或依赖错误。' ;;
    zh-CN:Installed) format='AstrBot 安装完成。' ;;
    en-US:ChooseSource) format='Select a download source' ;;
    en-US:China) format='Mainland China accelerated download mirrors' ;;
    en-US:Official) format='Official sources' ;;
    en-US:Custom) format='Custom' ;;
    en-US:Choice) format='Enter a number, or press Enter to use the default' ;;
    en-US:InvalidChoice) format='Please enter 1, 2, or 3.' ;;
    en-US:UvUrl) format='uv tar.gz download directory URL (without the filename)' ;;
    en-US:PypiUrl) format='PyPI simple index URL' ;;
    en-US:CustomRequired) format='Custom sources require both --uv-download-base-url and --pypi-index-url.' ;;
    en-US:InvalidUrl) format='Download sources must be valid HTTPS URLs: %s' ;;
    en-US:Source) format='Download source: %s' ;;
    en-US:UvMirror) format='uv download directory: %s' ;;
    en-US:Pypi) format='PyPI index: %s' ;;
    en-US:PythonMirror) format='Python download mirror: %s' ;;
    en-US:PythonDefault) format='Python downloads use the existing uv configuration. Set --python-install-mirror to use a mirror (PyPI mirrors do not include Python interpreters).' ;;
    en-US:InstallingUv) format='uv was not found. Installing uv...' ;;
    en-US:TryingMirror) format='Trying uv mirror: %s' ;;
    en-US:MirrorFailed) format='uv mirror download failed: %s' ;;
    en-US:OfficialFallback) format='Trying the official uv installer...' ;;
    en-US:UnsupportedPlatform) format='No preset uv mirror for this platform; trying the official installer: %s' ;;
    en-US:InvalidChecksum) format='uv archive SHA256 verification failed.' ;;
    en-US:MissingBinaries) format='The uv archive is missing uv or uvx.' ;;
    en-US:MissingTools) format='curl or wget is required to download files; mirror installation also requires tar and sha256sum or shasum.' ;;
    en-US:PathHint) format='uv installation directory: %s. Ensure it is on PATH in new terminals.' ;;
    en-US:UvFailed) format='Failed to install uv. See https://docs.astral.sh/uv/getting-started/installation/' ;;
    en-US:InstallingAstrBot) format='Installing AstrBot with Python 3.12...' ;;
    en-US:AstrBotFailed) format='AstrBot installation failed (exit code %s). Check the download or dependency errors above.' ;;
    en-US:Installed) format='AstrBot has been installed.' ;;
    ja-JP:ChooseSource) format='ダウンロード元を選択してください' ;;
    ja-JP:China) format='中国本土向け高速ダウンロードミラー' ;;
    ja-JP:Official) format='公式ソース' ;;
    ja-JP:Custom) format='カスタム' ;;
    ja-JP:Choice) format='番号を入力してください。Enter で既定値を使用します' ;;
    ja-JP:InvalidChoice) format='1、2、3 のいずれかを入力してください。' ;;
    ja-JP:UvUrl) format='uv tar.gz のダウンロードディレクトリ URL（ファイル名を除く）' ;;
    ja-JP:PypiUrl) format='PyPI simple インデックス URL' ;;
    ja-JP:CustomRequired) format='カスタムソースには --uv-download-base-url と --pypi-index-url の両方が必要です。' ;;
    ja-JP:InvalidUrl) format='ダウンロード元には有効な HTTPS URL を指定してください：%s' ;;
    ja-JP:Source) format='ダウンロード元：%s' ;;
    ja-JP:UvMirror) format='uv ダウンロードディレクトリ：%s' ;;
    ja-JP:Pypi) format='PyPI インデックス：%s' ;;
    ja-JP:PythonMirror) format='Python ダウンロードミラー：%s' ;;
    ja-JP:PythonDefault) format='Python のダウンロードには既存の uv 設定を使用します。ミラーを使うには --python-install-mirror を指定してください（PyPI ミラーに Python 本体は含まれません）。' ;;
    ja-JP:InstallingUv) format='uv が見つかりません。インストールしています…' ;;
    ja-JP:TryingMirror) format='uv ミラーを試しています：%s' ;;
    ja-JP:MirrorFailed) format='uv ミラーからのダウンロードに失敗しました：%s' ;;
    ja-JP:OfficialFallback) format='uv の公式インストーラーを試しています…' ;;
    ja-JP:UnsupportedPlatform) format='この環境に対応する uv ミラーがないため、公式インストーラーを試します：%s' ;;
    ja-JP:InvalidChecksum) format='uv アーカイブの SHA256 検証に失敗しました。' ;;
    ja-JP:MissingBinaries) format='uv アーカイブに uv または uvx がありません。' ;;
    ja-JP:MissingTools) format='ダウンロードには curl または wget が必要です。ミラーからのインストールには tar と sha256sum または shasum も必要です。' ;;
    ja-JP:PathHint) format='uv のインストール先：%s。新しいターミナルでも PATH に含まれていることを確認してください。' ;;
    ja-JP:UvFailed) format='uv のインストールに失敗しました。https://docs.astral.sh/uv/getting-started/installation/ を参照してください。' ;;
    ja-JP:InstallingAstrBot) format='Python 3.12 で AstrBot をインストールしています…' ;;
    ja-JP:AstrBotFailed) format='AstrBot のインストールに失敗しました（終了コード %s）。上記のダウンロードまたは依存関係のエラーを確認してください。' ;;
    ja-JP:Installed) format='AstrBot のインストールが完了しました。' ;;
    *) printf 'Unknown message: %s\n' "$key" >&2; return 1 ;;
  esac
  printf "$format\n" "$@"
}

if [ -z "$download_source" ]; then
  download_source='official'
  if [ "$can_prompt" -eq 1 ]; then
    default_choice=2
    if [ "$language" = 'zh-CN' ]; then default_choice=1; fi
    printf '\n%s\n  1. %s\n  2. %s\n  3. %s\n' \
      "$(message ChooseSource)" "$(message China)" "$(message Official)" "$(message Custom)" >&2
    while :; do
      printf '%s [%s]: ' "$(message Choice)" "$default_choice" >&2
      IFS= read -r choice <&3 || exit 1
      case "${choice:-$default_choice}" in
        1) download_source='china'; break ;;
        2) download_source='official'; break ;;
        3) download_source='custom'; break ;;
        *) warn "$(message InvalidChoice)" ;;
      esac
    done
  fi
fi

uv_mirror_urls=()
case "$download_source" in
  china)
    source_label="$(message China)"
    uv_mirror_urls=(
      'https://mirrors.ustc.edu.cn/github-release/astral-sh/uv/LatestRelease'
      'https://mirror.nyist.edu.cn/github-release/astral-sh/uv/LatestRelease'
    )
    pypi_index_url='https://mirrors.cernet.edu.cn/pypi/web/simple/'
    ;;
  official)
    source_label="$(message Official)"
    pypi_index_url='https://pypi.org/simple/'
    ;;
  custom)
    source_label="$(message Custom)"
    if [ "$can_prompt" -eq 1 ]; then
      if [ -z "$uv_download_base_url" ]; then
        printf '%s: ' "$(message UvUrl)" >&2
        IFS= read -r uv_download_base_url <&3 || exit 1
      fi
      if [ -z "$pypi_index_url" ]; then
        printf '%s: ' "$(message PypiUrl)" >&2
        IFS= read -r pypi_index_url <&3 || exit 1
      fi
    fi
    if [ -z "$uv_download_base_url" ] || [ -z "$pypi_index_url" ]; then
      err "$(message CustomRequired)"; exit 2
    fi
    uv_mirror_urls=("${uv_download_base_url%/}")
    ;;
  *) err "Unsupported download source: $download_source"; exit 2 ;;
esac

# Bash 3.2 treats empty arrays as unset with nounset; use the guarded expansion.
for url in ${uv_mirror_urls[@]+"${uv_mirror_urls[@]}"} "$pypi_index_url" "$python_install_mirror"; do
  [ -n "$url" ] || continue
  if ! [[ "$url" =~ ^https://[^/?#[:space:]@]+(/[^?#[:space:]]*)?$ ]]; then
    err "$(message InvalidUrl "$url")"; exit 2
  fi
done

info "$(message Source "$source_label")"
for url in ${uv_mirror_urls[@]+"${uv_mirror_urls[@]}"}; do info "$(message UvMirror "$url")"; done
info "$(message Pypi "$pypi_index_url")"

refresh_uv_path() {
  local dir
  for dir in "${UV_INSTALL_DIR:-}" "${UV_UNMANAGED_INSTALL:-}" "${XDG_BIN_HOME:-}" \
    "${XDG_DATA_HOME:+$XDG_DATA_HOME/../bin}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -n "$dir" ] && [ -d "$dir" ]; then export PATH="$dir:$PATH"; fi
  done
}

download() {
  if has curl; then
    curl -fsSL --connect-timeout 15 --max-time 90 -o "$2" -- "$1"
  elif has wget; then
    wget -q -T 30 -O "$2" -- "$1"
  else
    err "$(message MissingTools)"
    return 1
  fi
}

install_temp_dir=''
trap 'if [ -n "$install_temp_dir" ]; then rm -rf -- "$install_temp_dir"; fi' EXIT

install_uv() {
  info "$(message InstallingUv)"
  install_temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/astrbot-install.XXXXXX")"
  local platform machine target='' base_url artifact archive expected_hash actual_hash install_dir
  platform="$(uname -s)"
  machine="$(uname -m)"
  case "$platform:$machine" in
    Darwin:arm64|Darwin:aarch64) target='aarch64-apple-darwin' ;;
    Darwin:x86_64) target='x86_64-apple-darwin' ;;
    Linux:x86_64|Linux:amd64) target='x86_64-unknown-linux-musl' ;;
    Linux:aarch64|Linux:arm64) target='aarch64-unknown-linux-musl' ;;
    Linux:i?86) target='i686-unknown-linux-musl' ;;
    Linux:armv7l|Linux:armv8l) target='armv7-unknown-linux-musleabihf' ;;
    Linux:armv6l) target='arm-unknown-linux-musleabihf' ;;
    Linux:ppc64le) target='powerpc64le-unknown-linux-gnu' ;;
    Linux:s390x) target='s390x-unknown-linux-gnu' ;;
    Linux:riscv64) target='riscv64gc-unknown-linux-musl' ;;
  esac

  if [ -n "${uv_mirror_urls[*]:-}" ]; then
    if [ -z "$target" ]; then
      warn "$(message UnsupportedPlatform "$platform/$machine")"
    elif ! has tar || { ! has sha256sum && ! has shasum; }; then
      warn "$(message MissingTools)"
    else
      artifact="uv-$target.tar.gz"
      archive="$install_temp_dir/$artifact"
      for base_url in "${uv_mirror_urls[@]}"; do
        info "$(message TryingMirror "$base_url")"
        if ! download "$base_url/$artifact" "$archive" || \
           ! download "$base_url/$artifact.sha256" "$install_temp_dir/checksum"; then
          warn "$(message MirrorFailed "$base_url")"
          continue
        fi
        expected_hash=''
        read -r expected_hash _ < "$install_temp_dir/checksum" || true
        if has sha256sum; then
          actual_hash="$(sha256sum "$archive")"
        else
          actual_hash="$(shasum -a 256 "$archive")"
        fi
        actual_hash="${actual_hash%% *}"
        if ! [[ "$expected_hash" =~ ^[a-fA-F0-9]{64}$ ]] || \
           [ "$(printf '%s' "$expected_hash" | tr 'A-F' 'a-f')" != "$actual_hash" ]; then
          warn "$(message InvalidChecksum)"
          continue
        fi
        rm -rf -- "$install_temp_dir/unpacked"
        mkdir -p "$install_temp_dir/unpacked"
        if ! tar -xzf "$archive" -C "$install_temp_dir/unpacked" --strip-components=1; then
          warn "$(message MirrorFailed "$base_url")"
          continue
        fi
        if [ ! -f "$install_temp_dir/unpacked/uv" ] || [ ! -f "$install_temp_dir/unpacked/uvx" ]; then
          warn "$(message MissingBinaries)"
          continue
        fi
        install_dir="${UV_INSTALL_DIR:-${UV_UNMANAGED_INSTALL:-${XDG_BIN_HOME:-${XDG_DATA_HOME:+$XDG_DATA_HOME/../bin}}}}"
        install_dir="${install_dir:-$HOME/.local/bin}"
        mkdir -p "$install_dir"
        cp "$install_temp_dir/unpacked/uv" "$install_temp_dir/unpacked/uvx" "$install_dir/"
        chmod +x "$install_dir/uv" "$install_dir/uvx"
        refresh_uv_path
        info "$(message PathHint "$install_dir")"
        return
      done
    fi
  fi

  info "$(message OfficialFallback)"
  if ! download 'https://astral.sh/uv/install.sh' "$install_temp_dir/uv-install.sh" || \
     ! sh "$install_temp_dir/uv-install.sh" </dev/null; then
    err "$(message UvFailed)"
    exit 1
  fi
  refresh_uv_path
}

# Recover an existing installation before downloading uv again.
refresh_uv_path
if ! has uv; then install_uv; fi
if ! has uv; then err "$(message UvFailed)"; exit 1; fi
if uv_version="$(uv --version)"; then
  ok "$uv_version"
else
  status=$?
  err "$(message UvFailed)"
  exit "$status"
fi

python_install_mirror="${python_install_mirror:-${UV_PYTHON_INSTALL_MIRROR:-}}"
if [ -n "$python_install_mirror" ]; then
  info "$(message PythonMirror "$python_install_mirror")"
else
  info "$(message PythonDefault)"
fi
info "$(message InstallingAstrBot)"
# Scope mirror settings to this command; do not change the caller's environment or pip config.
if UV_PYTHON_INSTALL_MIRROR="$python_install_mirror" \
  uv tool install --python 3.12 astrbot --default-index "$pypi_index_url"; then
  ok "$(message Installed)"
else
  status=$?
  err "$(message AstrBotFailed "$status")"
  exit "$status"
fi
