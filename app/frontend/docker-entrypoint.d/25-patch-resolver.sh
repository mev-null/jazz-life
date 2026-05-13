#!/bin/sh
# nginx の resolver directive を /etc/resolv.conf から動的に組み立てた IP に
# 置換する。20-envsubst-on-templates.sh が default.conf.template を展開した直後
# (sort -V 順で 20- → 25- → 30-) に走り、/etc/nginx/conf.d/default.conf の中の
# __RESOLVER__ placeholder を実値に sed 置換する。
#
# なぜ envsubst (${NGINX_LOCAL_RESOLVERS}) を使わないか:
#   PR #20 / #21 で resolver を envsubst 変数で書いたところ、Railway 上で
#   "host not found in resolver \"${NGINX_LOCAL_RESOLVERS}\"" でループに入った。
#   NGINX_ENVSUBST_FILTER に当該名を入れているのに展開が走らない原因が確定
#   できず (Docker BuildKit の $ 展開 / awk 正規表現解釈 / 組み込み 15-local-
#   resolvers.envsh の export 経路のいずれかと推測)、envsubst 自体を回避するのが
#   一番確実なので runtime sed patch に倒した。
#
# 実行権限は Dockerfile の COPY --chmod=755 で付与する (git の +x bit に依らず
# 確実に付ける)。
#
# IPv6 アドレスは nginx 仕様で `[...]` で囲む必要がある (ポート番号と区別するため)。
# Railway は内部 DNS を IPv6 (例: fd12::10) で持たせているので、IPv4/IPv6 を
# awk 内で分岐して適切に整形する。

set -e

NS=$(awk '$1=="nameserver" {
    if ($2 ~ /:/) { printf "[%s] ", $2 }
    else          { printf "%s ", $2 }
}' /etc/resolv.conf 2>/dev/null | sed 's/ *$//')
if [ -z "$NS" ]; then
    # /etc/resolv.conf が空 / 読めない場合のフォールバック。Cloudflare public DNS は
    # Railway 内部ホスト名 (*.railway.internal) を引けないが、nginx の起動ループは
    # 止まるので 502 として原因切り分けがしやすくなる。
    NS="1.1.1.1"
fi

sed -i "s|__RESOLVER__|$NS|g" /etc/nginx/conf.d/default.conf
echo "$0: patched __RESOLVER__ with: $NS"
