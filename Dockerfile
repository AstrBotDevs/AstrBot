# ----------- base 构建阶段（安装依赖） -----------
  FROM python:3.10-alpine AS base

  WORKDIR /AstrBot
  COPY . .
  
  RUN apk add --no-cache \
      build-base \
      libffi-dev \
      openssl-dev \
      ffmpeg \
      bash \
      ca-certificates \
   && python -m pip install --upgrade pip \
   && pip install uv \
   && uv pip install -r requirements.txt --no-cache-dir --system \
   && uv pip install socksio uv pilk --no-cache-dir --system \
   && find /usr/local -name '*.pyc' -delete \
   && find /usr/local -type d -name '__pycache__' -exec rm -rf {} + \
   && rm -rf /root/.cache /tmp/*
  
  # ----------- dev 镜像：包含 gcc 可热装插件 -----------
  FROM python:3.10-alpine AS dev
  
  WORKDIR /AstrBot
  
  RUN apk add --no-cache \
      ffmpeg \
      bash \
      ca-certificates \
      libstdc++ \
      gcc \
      build-base \
      python3-dev \
      libffi-dev \
      openssl-dev
  
  COPY --from=base /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
  COPY --from=base /AstrBot /AstrBot
  
  EXPOSE 6185
  EXPOSE 6186
  
  CMD ["python", "main.py"]
  
  # ----------- runtime 镜像：无 gcc 更小更轻 -----------
  FROM python:3.10-alpine AS runtime
  
  WORKDIR /AstrBot
  
  RUN apk add --no-cache \
      ffmpeg \
      bash \
      ca-certificates \
      libstdc++
  
  COPY --from=base /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
  COPY --from=base /AstrBot /AstrBot
  
  EXPOSE 6185
  EXPOSE 6186
  
  CMD ["python", "main.py"]