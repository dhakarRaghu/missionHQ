# Deploying Mission HQ

This guide takes Mission HQ from a checkout to an always-on production box.
It covers a Mac (a Mac mini is the usual choice) and a Linux VPS.

## What runs in production

Four processes. All of them bind to localhost only.

| Process | Command | Port | Purpose |
| --- | --- | --- | --- |
| backend | `uv run python -m hq` in `backend/` | 127.0.0.1:8000 | FastAPI, agents, Telegram bot, cron |
| frontend | `npm run start` in `frontend/` (`next start`) | 127.0.0.1:3000 | Web console, serves the last `npm run build` |
| caddy | `caddy run --config ops/Caddyfile` | 127.0.0.1:8080 | One reverse proxy: `/api/*` to 8000, the rest to 3000 |
| backup | `ops/backup.sh run` | none | Nightly `pg_dump` plus vault push |

Tailscale Serve fronts port 8080. Serve is the only way in from outside the
machine. It terminates TLS and adds the `Tailscale-User-Login` header. The
backend trusts that header only when it equals `TAILSCALE_OWNER_LOGIN`
(`backend/src/hq/api/deps.py`). Otherwise the backend needs
`Authorization: Bearer <API_BEARER_TOKEN>`.

Never use `tailscale funnel`. Funnel opens the port to the public internet.
Public requests have no trusted `Tailscale-User-Login` header, and a public
client could forge one. Serve on the tailnet is the security boundary.

## 1. Install the tools

### Mac

```bash
xcode-select --install
brew install postgresql@16 node@20 caddy git
brew install --cask tailscale        # or the App Store app
curl -LsSf https://astral.sh/uv/install.sh | sh
brew services start postgresql@16
```

Postgres.app also works. `pg_dump` and `psql` must be on `PATH`.

### Linux (Debian or Ubuntu)

```bash
sudo apt install postgresql-16 git curl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install nodejs
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo apt install caddy               # see https://caddyserver.com/docs/install
sudo apt install bubblewrap          # optional, see "Sandboxing on Linux"
```

Create a user for the app, for example `hq`, and check out the repo into
`/opt/missionhq`. Run every command in this guide as that user unless it
starts with `sudo`.

## 2. Create the database

```bash
createdb missionhq
```

If the app connects as a specific role, create it and set it as the owner:

```bash
psql -c "CREATE ROLE hq LOGIN PASSWORD 'change-me'"
createdb -O hq missionhq
```

The backend applies `backend/migrations/*.sql` on startup. You do not run
migrations by hand.

## 3. Environment files

### `backend/.env`

Copy `backend/.env.example` to `backend/.env` and set:

| Variable | Set it to |
| --- | --- |
| `DATABASE_URL` | `postgresql://localhost:5432/missionhq`, or the role form `postgresql://hq:pass@localhost:5432/missionhq` |
| `GATEWAY_BASE_URL` | Your OpenAI-compatible gateway, ending in `/v1` |
| `GATEWAY_API_KEY` | The gateway key |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `OWNER_CHAT_ID` | Your numeric Telegram chat id. The bot ignores every other chat |
| `API_BEARER_TOKEN` | A long random secret. Generate with `openssl rand -hex 32`. Required in production |
| `TAILSCALE_OWNER_LOGIN` | Your Tailscale login, for example `you@github` or `you@gmail.com`. Check with `tailscale whoami` or `tailscale status --json` |
| `CRON_TZ` | Your time zone, for example `Asia/Kolkata` |
| `DAILY_SPEND_CAP_USD`, `NOTIFICATIONS_PER_DAY` | Keep the defaults until you have a reason to change them |
| `HEALTHCHECKS_PING_URL` | Optional. A healthchecks.io ping URL. The backend pings it so you are told when the box is down |
| `CORS_ORIGINS` | Leave empty for this setup. Only used when a page on another origin calls the API: the console on Vercel (section 11) or the phone reader's sync (section 12) |
| `BIND_HOST`, `BIND_PORT` | Keep `127.0.0.1` and `8000`. Caddy and Tailscale Serve reach the backend on the same box |

`API_BEARER_TOKEN` must not be empty in production. An empty token turns
authentication off (local development mode).

### `frontend/.env.local`

Copy `frontend/.env.example` to `frontend/.env.local`. The defaults are
correct: `NEXT_PUBLIC_API_BASE=/api` and `BACKEND_ORIGIN=http://127.0.0.1:8000`.
The launchd plist and the systemd unit also set `BACKEND_ORIGIN`, so the file
is only needed for `npm run dev`.

## 4. Build the frontend

```bash
cd frontend && npm ci && npm run build
```

`next start` serves the last build. Run `npm run build` again after every
frontend change, then restart the frontend service.

## 5. Start the services

### Mac (launchd)

Every plist in `ops/` has the repo path written into it
(`/Users/raghvendra.dhakar/Desktop/project/code/missionHq`). If your checkout
lives elsewhere, replace that path in the four plists first:

```bash
sed -i '' 's#/Users/raghvendra.dhakar/Desktop/project/code/missionHq#/path/to/missionHq#g' ops/*.plist
```

Also check the `uv`, `npm` and `caddy` paths in the plists match your machine
(`which uv npm caddy`). Then:

```bash
ops/supervise.sh install          # backend  (com.missionhq.backend)
ops/frontend.sh install           # frontend (com.missionhq.frontend)
ops/proxy.sh caddy install        # caddy    (com.missionhq.caddy)
ops/backup-schedule.sh install    # backup   (com.missionhq.backup, 03:30 nightly)
```

Each script also has `status`, `logs`, `uninstall`, and (for the servers)
`restart`. Logs go to `data/logs/<service>.log`. `KeepAlive` restarts a server
after any exit, including a crash.

### The nightly regression run (Mac, optional)

`scripts/regress-nightly.sh` runs the model-backed regression set
(`hq.cli regress run nightly-<date>`) and compares it with the newest
`after-*` result. It calls the models for real, so it runs here, where
`backend/.env` has the gateway key, and never in CI. Nothing installs it for
you; to schedule it at 04:30, after the backup, write a LaunchAgent:

```bash
cat > ~/Library/LaunchAgents/com.missionhq.regress.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.missionhq.regress</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/path/to/missionHq/scripts/regress-nightly.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/path/to/missionHq</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>4</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/path/to/missionHq/data/logs/regress.log</string>
  <key>StandardErrorPath</key>
  <string>/path/to/missionHq/data/logs/regress.log</string>
</dict>
</plist>
EOF
sed -i '' "s#/path/to/missionHq#$(pwd)#g" ~/Library/LaunchAgents/com.missionhq.regress.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.missionhq.regress.plist
```

Run it from the repo root so `$(pwd)` fills the path, and check that `uv` is
on the `PATH` the plist names (`which uv`). Then:

```bash
launchctl kickstart gui/$(id -u)/com.missionhq.regress     # run one now
tail -f data/logs/regress.log                              # PASS/FAIL per case, then the compare
launchctl bootout gui/$(id -u)/com.missionhq.regress       # remove it
```

The compare's last line is the night's summary (`N/M pass → N/M pass; $a →
$b`); a `REGRESSION` line means a case the accepted run passed and tonight's
failed. The spend lands on the daily cap like any other run, under agents
named `eval:<name>`, so size `--k` (add it to `ProgramArguments`) with that
in mind.

### Linux (systemd)

Install as system units in `/etc/systemd/system/`. Replace `hq` and
`/opt/missionhq` with your user and path.

`missionhq-backend.service`:

```ini
[Unit]
Description=Mission HQ backend
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
User=hq
WorkingDirectory=/opt/missionhq/backend
Environment=PATH=/home/hq/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/hq/.local/bin/uv run python -m hq
Restart=always
RestartSec=15
StandardOutput=append:/opt/missionhq/data/logs/backend.log
StandardError=append:/opt/missionhq/data/logs/backend.log

[Install]
WantedBy=multi-user.target
```

`missionhq-frontend.service`:

```ini
[Unit]
Description=Mission HQ frontend (next start)
After=network-online.target

[Service]
User=hq
WorkingDirectory=/opt/missionhq/frontend
Environment=NODE_ENV=production
Environment=BACKEND_ORIGIN=http://127.0.0.1:8000
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/bin/npm run start -- -p 3000 -H 127.0.0.1
Restart=always
RestartSec=15
StandardOutput=append:/opt/missionhq/data/logs/frontend.log
StandardError=append:/opt/missionhq/data/logs/frontend.log

[Install]
WantedBy=multi-user.target
```

`missionhq-caddy.service` (use this instead of the distro's `caddy.service`,
or point that unit at `ops/Caddyfile`):

```ini
[Unit]
Description=Mission HQ reverse proxy
After=network-online.target

[Service]
User=hq
WorkingDirectory=/opt/missionhq
ExecStart=/usr/bin/caddy run --config /opt/missionhq/ops/Caddyfile --adapter caddyfile
Restart=always
RestartSec=10
StandardOutput=append:/opt/missionhq/data/logs/caddy.log
StandardError=append:/opt/missionhq/data/logs/caddy.log

[Install]
WantedBy=multi-user.target
```

Backup: use a systemd timer or a cron line as the `hq` user:

```
30 3 * * * /opt/missionhq/ops/backup.sh run >> /opt/missionhq/data/logs/backup.log 2>&1
```

Enable everything:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now missionhq-backend missionhq-frontend missionhq-caddy
```

### Sandboxing on Linux

On Linux you can wrap agent tool processes in `bubblewrap` (`bwrap`). It gives
each tool call its own read-only view of the file system and no network unless
you allow it. macOS has no equivalent that works without a signed helper. This
is the main reason to prefer a Linux box if agents run shell tools. Nothing in
`ops/` enables it yet. When you add it, wrap the tool runner, not the backend
process, so the API and the database connection stay outside the sandbox.

## 6. Expose it over Tailscale Serve

On the box:

```bash
sudo tailscale up                 # log in once
tailscale serve --bg 8080         # https://<machine>.<tailnet>.ts.net -> 127.0.0.1:8080
tailscale serve status
```

Serve stays configured across reboots. Open `https://<machine>.<tailnet>.ts.net`
from any device on your tailnet. You are logged in by your Tailscale identity.
No bearer token is needed in the browser.

Do not run `tailscale funnel`. See the comment block in `ops/Caddyfile`.

## 7. First-boot checks

Run these on the box, in order.

1. Backend is up.

   ```bash
   curl -s http://127.0.0.1:8000/api/health
   ```

   Expect a JSON health body. If not: `ops/supervise.sh logs`.

2. Auth works and the token is required.

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/agents          # expect 401
   curl -s -H "Authorization: Bearer $API_BEARER_TOKEN" http://127.0.0.1:8000/api/agents   # expect the agent list
   ```

3. Proxy routes both halves.

   ```bash
   curl -s http://127.0.0.1:8080/api/health                              # backend through Caddy
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/       # expect 200 from next start
   ```

4. Tailscale identity is accepted. From another tailnet device open
   `https://<machine>.<tailnet>.ts.net/agents`. The page loads and lists agents
   without asking for a token. If it shows 401, `TAILSCALE_OWNER_LOGIN` does not
   match the login Serve sends. Check `tailscale whoami` on the client.

5. Telegram answers. Send `/board` to the bot from the owner chat. Expect the
   task board summary. Other commands: `/tickets /costs /agents /digest /drafts`.

6. Backup and restore work.

   ```bash
   ops/backup.sh run
   ops/backup.sh restore-drill      # prints "RESTORE DRILL PASSED"
   ```

   Do the restore drill once now and once a month. A backup that was never
   restored is not a backup.

7. Reboot the box and repeat steps 1 and 3. All services must come back on
   their own.

## 8. Keep the machine awake

### Mac

A sleeping Mac runs nothing. On AC power:

```bash
sudo pmset -a sleep 0 disksleep 0
sudo pmset -a womp 1               # wake on network access
```

Also in System Settings, Energy: enable "Start up automatically after a power
failure" and "Prevent automatic sleeping when the display is off". Closing the
lid on a laptop still sleeps it unless an external display is attached.

### Linux

VPS machines do not sleep. For a home Linux box, check
`systemctl status sleep.target` and mask it if needed:
`sudo systemctl mask sleep.target suspend.target hibernate.target`.

## 9. Updating

```bash
git pull
cd backend && uv sync && cd ..
cd frontend && npm ci && npm run build && cd ..
ops/supervise.sh restart
ops/frontend.sh restart
```

Caddy only needs a restart when `ops/Caddyfile` changes:
`ops/proxy.sh caddy restart`.

## 10. Emergency stop

Create a file named `HALT` at the repo root. The backend stops dispatching new
runs while the file exists. Delete it to resume. Per-agent pause is available
from the web console and Telegram.

## 11. Public console (Vercel) + backend on a VPS

The private Tailscale path above stays the recommended default. Use this
section only if you want the web console on Vercel. In that mode the console
and the backend live on different origins, so the backend must accept
cross-origin requests and the browser must send the bearer token itself.

### How it fits together

| Part | Where | Notes |
| --- | --- | --- |
| Backend | A VPS, behind Caddy | Binds to `127.0.0.1:8000`. Caddy terminates TLS on a real hostname |
| Console | Vercel | Static Next.js build. Calls the backend directly from the browser |
| Telegram | Unchanged | The bot talks to Telegram from the backend. Nothing changes here |

### Backend on the VPS

1. Install and start the backend as in sections 1 to 5. Keep
   `BIND_HOST=127.0.0.1` and `BIND_PORT=8000`.
2. Give the VPS a DNS name, for example `hq-api.example.com`, pointing at its
   public IP. Open ports 80 and 443 in the VPS firewall.
3. Run Caddy with this block. Caddy gets and renews the TLS certificate on its
   own (automatic HTTPS):

   ```
   hq-api.example.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```

4. In `backend/.env` set:

   | Variable | Set it to |
   | --- | --- |
   | `API_BEARER_TOKEN` | A long random secret: `openssl rand -hex 32` |
   | `CORS_ORIGINS` | The Vercel URL(s), comma-separated, exact origins. Example: `https://hq.vercel.app,https://hq-git-main-you.vercel.app`. No path, no trailing slash, no wildcard |
   | `TAILSCALE_OWNER_LOGIN` | Leave empty. There is no Tailscale Serve in front, so the header cannot be trusted |

5. Restart the backend. Check from your laptop:

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' https://hq-api.example.com/api/agents        # expect 401
   curl -s -H "Authorization: Bearer $API_BEARER_TOKEN" https://hq-api.example.com/api/agents
   ```

### Console on Vercel

1. Import the repo in Vercel. The repo stays a monorepo. Set the project's
   **Root Directory** to `frontend`.
2. Set the build-time environment variable
   `NEXT_PUBLIC_API_BASE=https://hq-api.example.com/api`. The browser then
   calls the backend directly. The `/api/*` rewrite in `next.config.ts` is not
   used in this mode, and `BACKEND_ORIGIN` is not needed.
3. Deploy. Open the console. The login page asks for the bearer token and
   stores it in the browser. Every request sends `Authorization: Bearer <token>`.
4. The live event stream uses the browser `EventSource` API, which cannot set
   headers. The console therefore opens the stream as
   `https://hq-api.example.com/api/events?token=<token>`. The backend accepts
   `?token=` only as an alternative to the header, and you must only use it
   over HTTPS. Never expose the backend over plain HTTP.

### Trade-off

In this mode the API is reachable from the whole internet. The only
protection is the bearer token.

- Use a long random token. Never reuse it anywhere else.
- Rotate the token if it leaks: change `API_BEARER_TOKEN`, restart the
  backend, and log in again in the console.
- Never run the backend without TLS. Without TLS the token and the `?token=`
  query string travel in clear text.
- `CORS_ORIGINS` limits which websites a browser lets call the API. It does
  not stop `curl` or scripts. The token is the real boundary.
- If you do not need the console from outside your devices, use Tailscale
  Serve (section 6) instead and leave `CORS_ORIGINS` empty.

## 12. Reading on a phone (Vercel, no backend)

Section 11 puts the whole console online and needs a backend on a VPS to do
it. This is the smaller thing: read the lessons on a phone, with no backend
anywhere, because the lessons ship as files.

`/read` is the one route that is not the console. It reads
`frontend/public/reader/`, which is committed to the repo, so it works while
the machine that runs the backend is asleep. `providers.tsx` exempts the path
from the auth guard and from the event stream, both of which would otherwise
try to reach a backend the phone cannot see.

### The loop: nightly, on the `reader` branch

Nothing to do by hand. Every night, right after the 03:00 vault reindex (or
its catch-up when the machine was asleep at 03:00), the backend builds the
bundle and commits it to a branch named **`reader`**, then runs
`git push origin reader`. Vercel deploys that branch. New lessons are on the
phone by morning.

How it stays out of your way:

- **`main` and your working tree are never touched.** The bundle is built in a
  temporary folder, hashed into git's object store, and committed with
  `git commit-tree` from a throwaway index (`GIT_INDEX_FILE` in a temp dir).
  Nothing is checked out, nothing is staged in your index, HEAD does not
  move, and your uncommitted files are never read.
- **The tree is `origin/main` plus the bundle.** Each `reader` commit is the
  app as you last pushed it, with `frontend/public/reader` replaced by
  tonight's bundle. Only already-pushed code goes out, and app changes reach
  the phone with the next lesson change after you push `main`.
- **A commit only when the library changed.** The commit carries a
  `Reader-Fingerprint:` line, a hash of every file in the bundle with
  `index.json`'s `built_at` left out. Same fingerprint as last night means no
  commit, no push and no Vercel build. A lesson written, rebuilt or marked
  read changes it.
- **A failed push is logged, not raised.** No network or no credential: the
  commit stays on your local `reader` branch, a `reader.published` event
  records the error, and the next night pushes it. The push runs with
  `GIT_TERMINAL_PROMPT=0`, so it can never hang waiting for a password; the
  https remote needs the macOS keychain credential helper (or an SSH remote)
  to push unattended.

Run the same thing by hand, for example after a lesson you want now:

```bash
uv run python -m hq.cli publish-reader   # in backend/
```

`uv run python -m hq.cli export-reader` still writes `frontend/public/reader`
in your working tree, for `next dev` on your own machine; you no longer need
to commit it.

The bundle is `index.json` (the catalogue) and one file per lesson under
`lessons/`, rebuilt from scratch each time, so a lesson you deleted or
rebuilt under a new date does not linger. Each page gets the same content
policy and `<base target="_blank">` that `/api/learning/page` injects for the
console, because here there is no endpoint to inject them.

### Point Vercel at `reader`

Once, after the first nightly run has pushed the branch (or after
`publish-reader`):

1. Vercel dashboard → the project → **Settings → Git**.
2. Under **Production Branch**, change `main` to `reader` and save.
3. Optional, to stop a preview build on every push to `main`: **Settings →
   Git → Ignored Build Step**, command
   `[ "$VERCEL_GIT_COMMIT_REF" = "reader" ] && exit 1 || exit 0`. Vercel
   builds when the command exits 1, so only `reader` builds.
4. **Deployments → Redeploy** the latest `reader` commit once, so production
   switches now rather than at the next lesson.

Root Directory stays `frontend`: the `reader` branch is the whole repo as of
`origin/main`, so the app, `src/proxy.ts` and its password gate build exactly
as before.

### Vercel settings

1. Import the repo. Set **Root Directory** to `frontend`.
2. Add one environment variable, for all environments:

   | Variable | Set it to |
   | --- | --- |
   | `READER_PASSWORD` | A long random secret: `openssl rand -hex 24` |

   That is the gate. `src/proxy.ts` checks it on the server before any route
   or file is served, and answers `401` with `WWW-Authenticate: Basic` until
   the request carries it. The browser asks once and remembers; any user name
   is accepted, so only the password matters. Leave the variable unset on
   your own machine and there is no gate, which is what `next start` behind
   the console wants.

   **Never name it `NEXT_PUBLIC_READER_PASSWORD`.** Anything with that prefix
   is compiled into the JavaScript the browser downloads, so the secret would
   be published rather than checked.

3. Leave `NEXT_PUBLIC_API_BASE` and `BACKEND_ORIGIN` unset. The reader
   reads its own files; the only request it makes to the backend is the
   optional sync below.
4. Optional, to send "Mark read" and concept taps back: set
   `NEXT_PUBLIC_READER_SYNC_URL` (see "Sending reads and taps back").
5. Open `https://<your-project>.vercel.app/read` on the phone and add it to
   the home screen.

The gate has no matcher, on purpose. The lessons are static files:
`/reader/index.json` and `/reader/lessons/<slug>.html` can be fetched on
their own, so a check drawn inside the React page would leave both open. Any
matcher added later must keep covering `/reader`.

Vercel's own Deployment Protection does the same job without any code, and
the two can be used together. This project uses the variable instead, so the
credential lives with the repo's other secrets.

### Sending reads and taps back

Reading on the phone has to move the course along: the evening run will not
start the next phase while the last course lesson is unread, and topic
articles wait the same way. So the lesson page on `/read` has a **Mark read**
button under the lesson, and each **Got it / Lost me** tap under a concept is
sent too. Both go to the backend on your tailnet, with no secret anywhere in
the deployment.

How it works: the page posts to `NEXT_PUBLIC_READER_SYNC_URL`, your backend's
tailnet address, with `credentials: "omit"` and no token. Tailscale Serve adds
the `Tailscale-User-Login` header on the way in, and the backend accepts it
because it equals `TAILSCALE_OWNER_LOGIN` (section 6). The two endpoints are
`POST /api/reader/read {file}` and `POST /api/reader/signal {file, concept,
verdict}`, where `file` is the lesson's page name from `index.json`. A read
goes through the same function as the console's buttons, so a course lesson
marks its phase read as well; a tap is stored in `hq.concept_signals` with
`via = 'phone'`, where the next outline reads it.

To turn it on:

1. **Vercel**, Settings → Environment Variables:

   | Variable | Set it to |
   | --- | --- |
   | `NEXT_PUBLIC_READER_SYNC_URL` | Your backend's tailnet origin, e.g. `https://mac.tail1234.ts.net` (no path, no trailing slash). `tailscale serve status` shows it |

   It is public by design (compiled into the page) and is not a secret: it
   only answers devices on your tailnet, signed in as you. Redeploy after
   setting it; `NEXT_PUBLIC_*` values are fixed at build time.
2. **Backend** `.env`: add the reader's Vercel origin to `CORS_ORIGINS`
   (comma-separated, exact, scheme and host, no path), e.g.
   `CORS_ORIGINS=https://your-reader.vercel.app`. Without it the browser
   blocks the request. Add each origin you open the reader from (a custom
   domain as well as the `.vercel.app` one). The backend reads this at start,
   so it applies from its next restart.
3. `TAILSCALE_OWNER_LOGIN` must be set (section 3) and Tailscale must be on,
   signed in as you, on the phone. If the phone's browser asks whether the
   page may reach devices on your network, allow it for the reader's site.

When the phone is off the tailnet, the Mac is asleep, or the variable is not
set, nothing is lost: the event waits in an outbox in the phone browser's
storage, and is sent on the next page load of `/read` and whenever the
browser comes back online. Next to the button, **saved** means the backend has
it and **will sync** means it is waiting. A tap on a page the backend has no
lesson for (**refused**) is dropped rather than retried. The read tick in the
library shows at once on that phone; everywhere else it follows from the
backend with the next export.

### What the phone cannot do

Everything else that writes. There is no Build enhanced version, no board and
no chat, because each of those needs the console and its credential. The
console on your laptop stays the place that changes anything beyond "I read
this" and "this concept landed / lost me".

The console routes are deployed too, and they have no backend to talk to:
the `/api/*` rewrite lands on the serverless function's own localhost, so
`/courses` showed "Could not load data — HTTP 404" and `/learn` showed empty
boxes that never filled in. So on a deployment with no backend every console
path now redirects to `/read`, including `/`. Open the bare domain on the
phone and you land in the library.

"No backend" is worked out without anything to configure: Vercel sets
`VERCEL` itself, and a console deployment that does have a backend sets
`NEXT_PUBLIC_API_BASE` (section 11). Your own machine sets neither, so the
console there is untouched — `/` still goes to `/home` and every view works
as before.
