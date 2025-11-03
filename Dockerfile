FROM node:25-bookworm-slim

# Install Python 3.11
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    ca-certificates \
    bash \
    ffmpeg \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    rm -f /usr/lib/python3.11/EXTERNALLY-MANAGED

WORKDIR /AstrBot

COPY . /AstrBot/

RUN echo "3.11" > .python-version

RUN python -m pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org uv socksio pilk

EXPOSE 6185
EXPOSE 6186

CMD ["uv", "run", "main.py"]