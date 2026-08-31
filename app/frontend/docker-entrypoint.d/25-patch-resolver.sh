#!/bin/sh
# Replace the nginx resolver directive with IPs built dynamically from /etc/resolv.conf.
# Runs right after 20-envsubst-on-templates.sh has expanded default.conf.template
# (sort -V order: 20- -> 25- -> 30-) and sed-replaces the __RESOLVER__ placeholder in
# /etc/nginx/conf.d/default.conf with the real value.
#
# Why not envsubst (${NGINX_LOCAL_RESOLVERS}):
#   An earlier version wrote the resolver as an envsubst variable, and on Railway nginx
#   went into a restart loop with "host not found in resolver \"${NGINX_LOCAL_RESOLVERS}\"".
#   The variable was listed in NGINX_ENVSUBST_FILTER yet never got expanded; the cause
#   was never pinned down (suspects: Docker BuildKit's $ expansion, awk regex handling,
#   or the export path of the built-in 15-local-resolvers.envsh). Avoiding envsubst
#   altogether is the most reliable fix, hence this runtime sed patch.
#
# The execute bit is set by `COPY --chmod=755` in the Dockerfile (does not rely on
# git's +x bit).
#
# nginx requires IPv6 addresses to be wrapped in `[...]` (to disambiguate from a port).
# Railway's internal DNS is IPv6 (e.g. fd12::10), so awk branches on IPv4/IPv6 and
# formats each accordingly.

set -e

NS=$(awk '$1=="nameserver" {
    if ($2 ~ /:/) { printf "[%s] ", $2 }
    else          { printf "%s ", $2 }
}' /etc/resolv.conf 2>/dev/null | sed 's/ *$//')
if [ -z "$NS" ]; then
    # Fallback when /etc/resolv.conf is empty or unreadable. Cloudflare public DNS cannot
    # resolve Railway internal hostnames (*.railway.internal), but it stops the nginx
    # restart loop, so the failure surfaces as a 502 and is easier to diagnose.
    NS="1.1.1.1"
fi

sed -i "s|__RESOLVER__|$NS|g" /etc/nginx/conf.d/default.conf
echo "$0: patched __RESOLVER__ with: $NS"
