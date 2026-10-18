#!/bin/sh
set -eu
if command -v busybox-extras >/dev/null 2>&1; then
  exec busybox-extras httpd -f -p 8080 -h /srv
fi
exec busybox httpd -f -p 8080 -h /srv
