FROM python:3.11-slim
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
    nodejs \
    curl \
    gnupg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    echo "3.11" > .python-version && \
    rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv && \
    uv pip install socksio pilk --no-cache-dir --system

EXPOSE 6185
EXPOSE 6186

CMD ["uv", "run", "main.py"]