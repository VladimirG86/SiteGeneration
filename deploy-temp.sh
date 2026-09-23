#!/usr/bin/env bash
# Обновление временного стенда Nelvi (185.185.70.64:8002) до текущей ветки.
# Запуск на сервере:  bash deploy-temp.sh [branch] [port]
set -euo pipefail
BRANCH="${1:-arena/01a0c97a-sitegeneration}"
PORT="${2:-8002}"
DIR="${SITEGEN_DIR:-/opt/sitegen-temp}"
REPO="https://github.com/VladimirG86/SiteGeneration.git"

if [ ! -d "$DIR/.git" ]; then
  git clone --branch "$BRANCH" "$REPO" "$DIR"
fi
cd "$DIR"
git fetch origin "$BRANCH"
git checkout -q "$BRANCH"
git reset -q --hard "origin/$BRANCH"

python3 -m venv .venv 2>/dev/null || true
. .venv/bin/activate
pip install -q -r sitegen/requirements.txt

# systemd-юнит sitegen-temp (данные в sitegen-temp-data, порт только $PORT)
if systemctl list-units --type=service | grep -q sitegen-temp; then
  sudo systemctl restart sitegen-temp
else
  sudo tee /etc/systemd/system/sitegen-temp.service >/dev/null <<EOF
[Unit]
Description=Nelvi temp stand
After=network.target
[Service]
WorkingDirectory=$DIR/sitegen
Environment=SITEGEN_DATA_DIR=/var/lib/sitegen-temp-data
EnvironmentFile=-$DIR/.env
ExecStart=$DIR/.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port $PORT
Restart=always
[Install]
WantedBy=multi-user.target
EOF
  sudo mkdir -p /var/lib/sitegen-temp-data
  sudo systemctl daemon-reload
  sudo systemctl enable --now sitegen-temp
fi

sleep 2
curl -fsS "http://127.0.0.1:$PORT/api/health" && echo && echo "OK: http://185.185.70.64:$PORT/"
