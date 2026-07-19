#!/bin/bash
# Hello-world test for a gateway: ./hello-gateway.sh [openrouter|vercel]
# (default: openrouter). Reads the gateway's API key from .env and asks one
# premium model (GPT-5.5) and one cheap model (Llama) to say hello.
# Vercel only: if Llama answers but GPT-5.5 is 403, the account is still being
# treated as unpaid free tier. On OpenRouter both calls just validate key/credit.
set -euo pipefail
cd "$(dirname "$0")"

GATEWAY="${1:-openrouter}"
case "$GATEWAY" in
  openrouter)
    BASE_URL="https://openrouter.ai/api/v1"
    KEY_VAR="OPENROUTER_API_KEY"
    LLAMA="meta-llama/llama-4-maverick"
    GPT="openai/gpt-5.5"
    ;;
  vercel)
    BASE_URL="https://ai-gateway.vercel.sh/v1"
    KEY_VAR="VERCEL_AI_GATEWAY_API_KEY"
    LLAMA="meta/llama-4-maverick"
    GPT="openai/gpt-5.5"
    ;;
  *)
    echo "ERROR: unknown gateway '$GATEWAY' (use openrouter or vercel)" >&2
    exit 1
    ;;
esac

KEY=$(grep "^${KEY_VAR}=" .env | cut -d= -f2- || true)
if [ -z "$KEY" ]; then
  echo "ERROR: no $KEY_VAR in .env" >&2
  exit 1
fi

call() {
  local model="$1"
  echo "=== $model ==="
  curl -sS "$BASE_URL/chat/completions" \
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

call "$LLAMA"   # cheap — should always work
call "$GPT"     # premium — validates paid credit
