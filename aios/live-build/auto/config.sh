#!/bin/sh
set -e
# Called by `lb config` / documented manual setup
lb config noauto \
  --distribution bookworm \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --archive-areas "main contrib non-free non-free-firmware" \
  --debian-installer none \
  --bootappend-live "boot=live components locales=zh_CN.UTF-8 keyboard-layouts=cn hostname=luminos username=luminos" \
  --mirror-bootstrap http://deb.debian.org/debian/ \
  --mirror-binary http://deb.debian.org/debian/ \
  "${@}"
