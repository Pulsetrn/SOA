#!/bin/sh
set -eu

if [ ! -f /data/sentinel.conf ]; then
    cp /etc/redis/sentinel.conf /data/sentinel.conf
fi

exec redis-server /data/sentinel.conf --sentinel
