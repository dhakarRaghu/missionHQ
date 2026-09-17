#!/bin/bash
# The Codex browser tool (cua_repl -> node_repl) asks a Codex app-server for
# the ChatGPT auth token. The app-server reports that token only when the
# model provider is `openai`. Mission HQ runs Codex's models on the Grid
# (juspay) provider, so the browser tool got no token and failed with
# "Codex auth token is unavailable". This wrapper is given to the browser
# tool only: its app-server sees the ChatGPT sign-in, while the models keep
# running on Grid.
exec "${CODEX_REAL_CLI_PATH:-/Applications/ChatGPT.app/Contents/Resources/codex}" -c model_provider=openai "$@"
