#!/bin/sh
set -e
exec python3 /opt/lyux/apps/enrollment/src/update_policy_sync.py --apply
