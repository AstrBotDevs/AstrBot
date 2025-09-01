FROM python:3.11-slim
WORKDIR /AstrBot

COPY . /AstrBot/

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
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
RUN uv pip install socksio uv pyffmpeg pilk --no-cache-dir --system

# 释出 ffmpeg
RUN python -c "from pyffmpeg import FFmpeg; ff = FFmpeg();"

# add /root/.pyffmpeg/bin/ffmpeg to PATH, inorder to use ffmpeg
RUN echo 'export PATH=$PATH:/root/.pyffmpeg/bin' >> ~/.bashrc

EXPOSE 6185 
EXPOSE 6186

CMD [ "python", "main.py" ]



