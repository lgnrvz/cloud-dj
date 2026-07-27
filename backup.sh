#!/bin/bash
BACKUP_DIR="/home/raspberrypi/cloud-dj/backups"
mkdir -p "$BACKUP_DIR"
cp /home/raspberrypi/cloud-dj/database.db "$BACKUP_DIR/database-$(date +%Y%m%d).db"
# Keep only last 7 backups
ls -t "$BACKUP_DIR"/database-*.db 2>/dev/null | tail -n +8 | xargs -r rm
echo "Backup done: database-$(date +%Y%m%d).db"