#!/bin/bash
# Hello-world test for the Vercel AI Gateway.
# Reads AI_GATEWAY_API_KEY from .env, asks one premium model (GPT-5.5) and one
# free-tier model (Llama) to say hello. If Llama answers but GPT-5.5 is 403,
# the account is still being treated as unpaid free tier.
set -euo pipefail
cd "$(dirname "$0")"

KEY=$(grep '^AI_GATEWAY_API_KEY=' .env | cut -d= -f2-)
if [ -z "$KEY" ]; then
  echo "ERROR: no AI_GATEWAY_API_KEY in .env" >&2
  exit 1
fi

call() {
  local model="$1"
  echo "=== $model ==="
  curl -sS https://ai-gateway.vercel.sh/v1/chat/completions \
    -H "Authorization: Bearer $KEY" \
    -H "Content-Type: application/json" \
    -d '{"model": "'"$model"'", "messages": [{"role": "user", "content": "Say hello world"}], "max_tokens": 20}' \
    | python3 -c '
import json, sys
r = json.load(sys.stdin)
if "choices" in r:
    print("PASS:", r["choices"][0]["message"]["content"].strip())
else:
    err = r.get("error", {})
    print("FAIL:", err.get("type", "unknown"), "-", err.get("message", r))
'
  echo
}

call "meta/llama-4-maverick"   # free tier — should always work
call "openai/gpt-5.5"          # premium — works only once Vercel sees your paid credit
