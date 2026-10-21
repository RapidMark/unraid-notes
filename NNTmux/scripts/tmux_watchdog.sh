#!/bin/bash
# Every 5 min: restart NNTmux's processing when its tmux monitor pane has died.
# The container's own loop only checks that the tmux session exists, so a dead monitor
# (e.g. after a Redis read timeout) leaves header and release processing stopped for hours.
docker ps --format '{{.Names}}' | grep -qx NNTmux || exit 0
started=$(date -d "$(docker inspect -f '{{.State.StartedAt}}' NNTmux)" +%s)
[ $(( $(date +%s) - started )) -lt 600 ] && exit 0      # leave start-up alone
dead=$(docker exec -u www-data NNTmux tmux display-message -p -t nntmux:0.0 '#{pane_dead}' 2>/dev/null)
[ "$dead" = "0" ] && exit 0
logger -t nntmux_watchdog "tmux monitor ${dead:+dead}${dead:-missing}, restarting processing"
docker exec -u www-data -w /app -e HOME=/config NNTmux php artisan tmux:stop --session=nntmux --force --no-interaction >/dev/null 2>&1
docker exec NNTmux /command/s6-svc -r /run/service/indexer
sleep 60
alive=$(docker exec -u www-data NNTmux tmux list-panes -s -t nntmux -F '#{pane_dead}' 2>/dev/null | grep -c '^0')
logger -t nntmux_watchdog "after restart: $alive panes alive"
