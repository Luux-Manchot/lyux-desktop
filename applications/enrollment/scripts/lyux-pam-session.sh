#!/usr/bin/env bash
# Wrapper pam_exec pour synchroniser la session et contrôler la mono/multi-session LyuX.
set -u
export PYTHONPATH="/opt/lyux/apps/enrollment/src:${PYTHONPATH:-}"
exec /usr/bin/python3 /opt/lyux/apps/enrollment/src/pam_session_hook.py
