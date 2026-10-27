#!/usr/bin/env bash
# Déploie memo sur le LXC « web » depuis l'hôte : sauvegarde de la base, rsync vers /root/memo,
# venv + dépendances, unité systemd si elle a changé, redémarrage, test de réponse.
# L'état (data/) et le venv restent sur le serveur, jamais écrasés.
set -euo pipefail

HOST="${MEMO_DEPLOY_HOST:-web}"
DEST="${MEMO_DEPLOY_DIR:-/root/memo}"
URL="${MEMO_DEPLOY_URL:-http://100.67.37.21:5005/}"
cd "$(dirname "$0")/.."

# Sauvegarde cohérente (WAL) de la base si elle existe.
ssh "$HOST" "if [ -f $DEST/data/memo.db ]; then mkdir -p $DEST/data/backups && \
  python3 -c \"import sqlite3,sys,time; s=sqlite3.connect('$DEST/data/memo.db'); \
d=sqlite3.connect('$DEST/data/backups/memo-'+time.strftime('%Y%m%d-%H%M%S')+'.db'); s.backup(d); d.close()\" && \
  echo 'sauvegarde de memo.db faite'; else echo 'pas de base à sauvegarder'; fi"

ssh "$HOST" "mkdir -p $DEST"
rsync -az --delete \
  --exclude 'data/' --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' --exclude '.pytest_cache/' \
  ./ "$HOST:$DEST/"

ssh "$HOST" "cd $DEST && { [ -d venv ] || python3 -m venv venv; } && venv/bin/pip install -q -r requirements.txt"

ssh "$HOST" "if ! cmp -s $DEST/deploy/memo.service /etc/systemd/system/memo.service; then \
  cp $DEST/deploy/memo.service /etc/systemd/system/memo.service && systemctl daemon-reload && \
  systemctl enable memo.service >/dev/null 2>&1 && echo 'unité installée'; else echo 'unité inchangée'; fi"

ssh "$HOST" "systemctl restart memo.service"

for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS -m 3 -o /dev/null "$URL"; then echo "memo répond sur $URL"; exit 0; fi
  sleep 1
done
echo "memo ne répond pas sur $URL" >&2
ssh "$HOST" "journalctl -u memo -n 20 --no-pager" >&2 || true
exit 1
