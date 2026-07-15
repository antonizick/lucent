#!/bin/bash
set -e

echo "Restarting Lucent services..."
sudo systemctl restart lucent-voice-box.service lucent-monitor.service discord-bot.service

echo "Waiting for services to start..."
sleep 2

echo ""
echo "Service Status:"
sudo systemctl status lucent-voice-box.service lucent-monitor.service discord-bot.service --no-pager | grep -A 1 "^●"

echo ""
echo "All services restarted successfully."
