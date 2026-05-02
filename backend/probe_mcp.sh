#!/usr/bin/env bash
# Probe the deployed memory MCP server and check whether the tool schemas it
# returns still contain anyOf / array-typed fields that Gemini rejects.
#
# Usage:
#   API_KEY=mem_xxx bash probe_mcp.sh
set -euo pipefail

URL="https://tenants-masteragent.4ky7uo.easypanel.host/api/memory/mcp"
KEY="${API_KEY:?Set API_KEY env var to a valid Memory Key (mem_...)}"

# 1) initialize → server returns Mcp-Session-Id
INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'

INIT_RESP=$(curl -s -i -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-API-Key: $KEY" \
  -d "$INIT_BODY")

SESSION_ID=$(echo "$INIT_RESP" | grep -i '^mcp-session-id:' | awk '{print $2}' | tr -d '\r')
if [ -z "$SESSION_ID" ]; then
  echo "Failed to get session id. Response:"
  echo "$INIT_RESP"
  exit 1
fi
echo "Session: $SESSION_ID"

# 2) initialized notification (required)
curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-API-Key: $KEY" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' > /dev/null

# 3) tools/list
TOOLS=$(curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-API-Key: $KEY" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}')

# Strip SSE framing if present
TOOLS_JSON=$(echo "$TOOLS" | sed -n 's/^data: //p' | head -1)
[ -z "$TOOLS_JSON" ] && TOOLS_JSON="$TOOLS"

# Quick leak counts
echo "$TOOLS_JSON" | python -c "
import sys, json
data = json.load(sys.stdin)
tools = data.get('result', {}).get('tools', [])
print(f'Tool count: {len(tools)}')
total_anyof = total_oneof = total_listtype = 0
for t in tools:
    s = json.dumps(t.get('inputSchema', {}))
    total_anyof += s.count('\"anyOf\"')
    total_oneof += s.count('\"oneOf\"')
    total_listtype += s.count('\"type\": [')
print(f'Total anyOf occurrences:    {total_anyof}')
print(f'Total oneOf occurrences:    {total_oneof}')
print(f'Total array-type fields:    {total_listtype}')
if total_anyof or total_oneof or total_listtype:
    print()
    print('FIRST LEAKING TOOL:')
    for t in tools:
        s = json.dumps(t.get('inputSchema', {}))
        if 'anyOf' in s or 'oneOf' in s or '\"type\": [' in s:
            print(f'  name: {t[\"name\"]}')
            print(json.dumps(t['inputSchema'], indent=2)[:1500])
            break
"
