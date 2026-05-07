#!/bin/bash
set -e

echo "Restarting Lucent services..."
sudo systemctl restart discord-bot.service lucent-server.service lucent-poller.service lucent-voice-box.service

echo "Waiting for services to start..."
sleep 2

echo ""
echo "Service Status:"
sudo systemctl status discord-bot.service lucent-server.service lucent-poller.service lucent-voice-box.service --no-pager | grep -A 1 "^●"

echo ""
echo "All services restarted successfully."
