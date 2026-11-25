#!/usr/bin/env bash
# Prépare le réseau avant l'OOBE : toute carte Ethernet sans IPv4 reçoit un bail DHCP
# (ou une configuration statique locale si /etc/lyux/network-static.conf est fourni).
# Aucune adresse réseau propre à un établissement n'est figée dans ce script.
set -u

LOG="${LYUX_NET_LOG:-/var/log/lyux-net-setup.log}"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "[lyux-net-setup] $(date -Is)"

STATIC_CONF="${LYUX_STATIC_CONF:-/etc/lyux/network-static.conf}"
if [ -f "$STATIC_CONF" ]; then
    # Format attendu : IFACE, IP_CIDR, GATEWAY, DNS
    # shellcheck disable=SC1090
    . "$STATIC_CONF"
    if [ -n "${IFACE:-}" ] && [ -n "${IP_CIDR:-}" ]; then
        echo "$IFACE : application configuration statique ($IP_CIDR)"
        ip link set "$IFACE" up || true
        ip addr flush dev "$IFACE" 2>/dev/null || true
        ip addr add "$IP_CIDR" dev "$IFACE" || echo "$IFACE : échec ip addr add"
        if [ -n "${GATEWAY:-}" ]; then
            ip route replace default via "$GATEWAY" dev "$IFACE" || echo "$IFACE : échec route par défaut"
        fi
        if [ -n "${DNS:-}" ]; then
            printf "nameserver %s\n" "$DNS" > /etc/resolv.conf 2>/dev/null || true
        fi
    fi
fi

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
        dhclient -1 -nw "$iface" 2>/dev/null || dhclient -nw "$iface" || echo "$iface : dhclient a échoué"
    elif command -v udhcpc >/dev/null 2>&1; then
        udhcpc -n -q -i "$iface" || echo "$iface : udhcpc a échoué"
    else
        ifup "$iface" 2>/dev/null || echo "$iface : ni dhclient ni ifup disponible"
    fi
done

echo "--- état final ---"
ip -brief addr
