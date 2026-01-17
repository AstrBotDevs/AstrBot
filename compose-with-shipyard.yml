version: '3.8'

# 当接入 QQ NapCat 时，请使用这个 compose 文件一键部署: https://github.com/NapNeko/NapCat-Docker/blob/main/compose/astrbot.yml

services:
  astrbot:
    image: soulter/astrbot:latest
    container_name: astrbot
    restart: always
    ports: # mappings description: https://github.com/AstrBotDevs/AstrBot/issues/497
      - "6185:6185" # 必选，AstrBot WebUI 端口
      - "6199:6199" # 可选, QQ 个人号 WebSocket 端口
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ${PWD}/data:/AstrBot/data
      # - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    networks:
      - astrbot_network

  shipyard:
    image: soulter/shipyard-bay:latest
    container_name: astrbot_shipyard
    # ports:
    #   - "8156:8156"
    environment:
      - PORT=8156
      - DATABASE_URL=sqlite+aiosqlite:///./data/bay.db
      - ACCESS_TOKEN=secret-token
      - MAX_SHIP_NUM=10
      - BEHAVIOR_AFTER_MAX_SHIP=reject
      - DOCKER_IMAGE=soulter/shipyard-ship:latest
      - DOCKER_NETWORK=astrbot_network
      - SHIP_DATA_DIR=${PWD}/data/shipyard/ship_mnt_data
      - DEFAULT_SHIP_CPUS=1.0
      - DEFAULT_SHIP_MEMORY=512m
    volumes:
      - ${PWD}/data/shipyard/bay_data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - astrbot_network

networks:
  astrbot_network:
    name: astrbot_network
    driver: bridge
