#!/bin/bash
# Wrapper cron: pemeriksaan otomatis mingguan PC + kirim ringkasan ke Telegram
cd /home/ubnt/pc-monitor || exit 1
exec /home/ubnt/pc-monitor/.venv/bin/python /home/ubnt/pc-monitor/weekly_check.py --send
