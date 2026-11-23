#!/usr/bin/env bash
# Prépare le réseau avant l'OOBE : toute carte Ethernet sans IPv4 reçoit un bail DHCP.
# Cela permet aux clients génériques de trouver le serveur sur le réseau pédagogique
# sans figer d'adresse IP dans l'ISO.
set -u

LOG="/var/log/lyux-net-setup.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "[lyux-net-setup] $(date -Is)"

for syspath in /sys/class/net/*; do
    iface="${syspath##*/}"
    case "$iface" in
        lo|docker*|br-*|veth*|virbr*|sit*|tun*|tap*|dummy*) continue ;;
    esac

    if ip -4 addr show dev "$iface" 2>/dev/null | grep -q 'inet '; then
        echo "$iface : déjà configurée, on garde son IP"
        continue
    fi

    echo "$iface : activation DHCP"
    ip link set "$iface" up || true
    if command -v dhclient >/dev/null 2>&1; then
        dhclient -nw "$iface" || echo "$iface : dhclient a échoué"
    else
        ifup "$iface" 2>/dev/null || echo "$iface : ni dhclient ni ifup disponible"
    fi
done

echo "--- état final ---"
ip -brief addr
