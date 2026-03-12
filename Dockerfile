FROM python:3.12-slim
WORKDIR /AstrBot

COPY . /AstrBot/

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    ca-certificates \
    bash \
    ffmpeg \
    curl \
    gnupg \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN python -m pip install uv \
    && echo "3.12" > .python-version \
    && uv lock \
    && uv export --format requirements.txt --output-file requirements.txt --frozen \
    && uv pip install -r requirements.txt --no-cache-dir --system \
    && uv pip install socksio uv pilk --no-cache-dir --system

# Keep UID/GID 1000 in sync with the Kubernetes runAsUser/runAsGroup/fsGroup values.
RUN groupadd --system --gid 1000 astrbot \
    && useradd --system --uid 1000 --gid astrbot --home-dir /AstrBot --shell /usr/sbin/nologin astrbot \
    && mkdir -p /AstrBot/data \
    && chown -R astrbot:astrbot /AstrBot

EXPOSE 6185

USER astrbot

CMD ["python", "main.py"]
