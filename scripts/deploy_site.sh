#!/usr/bin/env bash
# Publishes ZecPy Live's recorded run as a static site on Cloudflare Pages (project
# "zecpy-live", https://zecpy-live.pages.dev). The hosted page waits for Run and replays
# demo/static/replay.json; the live mode needs this repository's server and devnet.
# Credentials come from ~/.zecpy-dev/deploy.env, never from this repository.
#
#   scripts/deploy_site.sh            build and deploy
#   scripts/deploy_site.sh --build    build into ./site-dist only
set -euo pipefail
cd "$(dirname "$0")/.."
dist=site-dist
rm -rf "$dist" && mkdir -p "$dist/static"
cp demo/static/app.js demo/static/app.css demo/static/replay.json "$dist/static/"
# The hosted copy is the same page, told that it has no server behind it.
sed 's|<meta charset="utf-8">|<meta charset="utf-8">\n  <meta name="zecpy-mode" content="replay">\n  <meta name="description" content="A recorded run of ZecPy on a local Zcash chain, with every request the light server received.">|' \
  demo/static/index.html > "$dist/index.html"
cat > "$dist/404.html" <<'HTML'
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not found · ZecPy Live</title><link rel="stylesheet" href="/static/app.css"></head>
<body><main class="canvas"><h1>Not found</h1><p class="finding"><a href="/">Open ZecPy Live</a></p></main></body></html>
HTML
printf '/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n' > "$dist/_headers"
[ "${1:-}" = "--build" ] && exit 0
. "$HOME/.zecpy-dev/deploy.env"
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
out=$(pwd)/$dist
(cd "$(mktemp -d)" && npx --yes wrangler@4 pages deploy "$out" --project-name zecpy-live --branch main --commit-dirty=true)
