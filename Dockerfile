FROM python:3.10-slim
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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install uv
RUN uv pip install -r requirements.txt --no-cache-dir --system
RUN uv pip install socksio uv pyffmpeg --no-cache-dir --system

EXPOSE 6185 
EXPOSE 6186

CMD [ "python", "main.py" ]
