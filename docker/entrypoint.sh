#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
	chown -R plym:plym /app/storage
	# Dropping uid does not move HOME, and libraries such as asyncpg probe
	# $HOME for credentials; left at /root they fail on an unreadable path.
	export HOME=/home/plym
	exec setpriv --reuid=plym --regid=plym --init-groups "$@"
fi

exec "$@"
