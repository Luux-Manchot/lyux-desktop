#!/bin/sh
export PYTHONPATH="/opt/lyux/apps/enrollment/src:${PYTHONPATH:-}"
exec python3 /opt/lyux/apps/enrollment/src/pam_auth_hook.py
