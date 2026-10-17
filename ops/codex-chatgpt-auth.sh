#!/bin/bash
# The Codex browser tool (cua_repl -> node_repl) asks a Codex app-server for
# the ChatGPT auth token. The app-server reports that token only when the
# model provider is `openai`. Mission HQ runs Codex's models on the Grid
# (juspay) provider, so the browser tool got no token and failed with
# "Codex auth token is unavailable". This wrapper is given to the browser
# tool only: its app-server sees the ChatGPT sign-in, while the models keep
# running on Grid.
#
# The ChatGPT app has moved its bundled CLI between releases (Resources/codex
# until 2026-10-14, Resources/codex-cli/bin/codex after), and a plugin's
# .mcp.json keeps naming the old path. A dead path here makes the app-server
# exit and every browser call fail with "trusted Node process exited
# unexpectedly", so take the first candidate that exists.
for cli in \
    "$CODEX_REAL_CLI_PATH" \
    /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex \
    /Applications/ChatGPT.app/Contents/Resources/codex \
    "${CODEX_HOME:-$HOME/.codex}/plugins/.plugin-appserver/codex"; do
  if [ -n "$cli" ] && [ -x "$cli" ]; then
    exec "$cli" -c model_provider=openai "$@"
  fi
done
echo "codex-chatgpt-auth: no codex CLI found; set CODEX_REAL_CLI_PATH" >&2
exit 127
