[Unit]
Description=AstrBot Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/.local/share/astrbot
ExecStart=/usr/bin/sh -c '/usr/bin/astrbot run || { /usr/bin/astrbot init && /usr/bin/astrbot run; }'
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
