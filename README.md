# Napwnli AD Gameserver

A lightweight Attack/Defense CTF game server written in Python and Flask.
Designed for simplicity, correctness, and ease of deployment.

```
  _  _                          _ _
 | \| |__ _ _ ____ __ ___ _ _ | (_)
 | .` / _` | '_ \ V  V / ' \| | |
 |_|\_\__,_| .__/\_/\_/|_||_|_|_|
            |_|  AD Gameserver
```

---

## Overview

Napwnli AD Gameserver manages the full lifecycle of an Attack/Defense CTF:
tick scheduling, automated service checking, flag lifecycle, score computation,
and a live scoreboard. It is intentionally minimal -- no message queues, no
external task runners, no microservices.

Each team runs the same set of vulnerable services on their own machine. The
server deploys a checker script for each service every tick to verify
availability (SLA) and place a flag. Participants attack each other's services,
steal flags, and submit them to gain points.

---

## Features

- Tick-based game loop with configurable duration
- Three-phase checker protocol: check, put, get
- Pluggable checkers: Python scripts or any executable (Go, Bash, Node, etc.)
- SLA-weighted symmetric scoring
- Per-tick SLA bonus for keeping services up
- Batch flag submission API (up to 50 flags per request)
- Live scoreboard with per-service SLA%, flags gained, flags lost
- Admin panel: team and service management, game settings, competition reset
- PostgreSQL backend via Docker Compose

---

## Architecture

```
+-------------------+        +------------------+
|   Flask App       |        |   tick_loop      |
|                   |        |   (background    |
|  /                |        |    thread)       |
|  /admin           |        |                  |
|  /rules           |        |  for each team   |
|  /api/flagids     |        |  for each svc:   |
|  /api/submit      |        |    check         |
|                   |        |    put           |
+--------+----------+        |    get           |
         |                   +--------+---------+
         |                            |
         v                            v
+--------+----------------------------+---------+
|                 PostgreSQL                    |
|                                               |
|  Team  Service  Flag  CheckerResult           |
|  Config  TeamServiceScore                     |
+-----------------------------------------------+
```

### Database Models

| Model              | Purpose                                              |
|--------------------|------------------------------------------------------|
| `Team`             | Team name, IP address, API key, total score          |
| `Service`          | Service name, checker filename, flags per tick       |
| `Flag`             | Active flags with flag_id, secret, captured state    |
| `CheckerResult`    | Per-tick checker outcome for historical audit        |
| `TeamServiceScore` | Aggregated SLA counters, last status, flag stats     |
| `Config`           | Key-value store for runtime game settings            |

`TeamServiceScore` acts as the primary read model for the scoreboard: SLA
percentage, last checker status, and flag counts are all maintained as running
counters updated atomically by the checker threads. The scoreboard never reads
`CheckerResult` directly.

---

## Scoring

### SLA Bonus
At the end of each tick, for every service that passes all three checker phases
(check, put, get), the owning team earns **K points**. K is configurable from
the admin panel.

### Attack / Defense
When a flag is successfully submitted:

```
points_gained = 10.0 * attacker_SLA
points_lost   =  5.0 * victim_SLA
```

Both are SLA-weighted and symmetric: high-SLA teams earn more when attacking
and lose more when their services are exploited. Teams whose services are
already down lose less from flag theft.

### SLA Calculation
```
SLA% = ticks_up / ticks_total
```

Maintained as integer counters in `TeamServiceScore`. Computed in O(1) with no
additional database queries.

---

## Checker Protocol

Checkers are standalone scripts placed in the `checkers/` directory. The server
invokes them via stdin/stdout using a simple JSON protocol.

If the checker file is executable, it is called directly. Otherwise it is run
with `python`. This allows checkers written in any language.

### Input (stdin)

```json
{
  "action": "check" | "put" | "get",
  "ip":     "10.10.1.2",
  "tick":   42,
  "flag":   "NPW_...",
  "flag_id": "...",
  "secret": "..."
}
```

### Output (stdout)

```json
{
  "status":  "UP" | "DOWN" | "MUMBLE",
  "flag_id": "...",
  "secret":  "..."
}
```

### Phases

| Phase   | Description                                                        |
|---------|--------------------------------------------------------------------|
| `check` | Verify the service is reachable and behaves correctly. No flag.    |
| `put`   | Place the flag in the service. Return `flag_id` (public) and `secret` (private). |
| `get`   | Retrieve the flag using `flag_id` and `secret`. Verify it is still present. |

The service is marked **UP** only if all three phases succeed. A failure in any
phase produces **MUMBLE** (partial) or **DOWN**.

`flag_id` is exposed in the public API so other teams can locate flags.
`secret` is stored privately by the server and passed only to the checker's
`get` phase.

See `checkers/example.py` for a documented skeleton.

---

## API Reference

### GET /api/flagids/<service_id>

Returns active flag IDs grouped by target IP. Only the last 5 ticks are
returned. Already-captured flags are excluded.

```
GET /api/flagids/1
```

Response:
```json
{
  "10.10.1.2": ["user_42", "user_43"],
  "10.10.1.3": ["user_17"]
}
```

### POST /api/submit

Submit one or more flags. Requires the team API key in the `X-Team-Key` header.
Rate limited to 1 request per second per team, with up to 50 flags per request.

```
POST /api/submit
X-Team-Key: <your_api_key>
Content-Type: application/json

{"flags": ["NPW_abc123...", "NPW_def456..."]}
```

Single flag shorthand:
```json
{"flag": "NPW_abc123..."}
```

Response (always an array):
```json
[
  {"flag": "NPW_abc123...", "status": "ACCEPTED",          "points": 8.50},
  {"flag": "NPW_def456...", "status": "ALREADY_CAPTURED",  "points": 0.0},
  {"flag": "NPW_xyz789...", "status": "EXPIRED",           "points": 0.0}
]
```

Possible status values:

| Status             | Meaning                                      |
|--------------------|----------------------------------------------|
| `ACCEPTED`         | Flag is valid. Points awarded.               |
| `INVALID`          | Flag does not exist.                         |
| `OWN_FLAG`         | Flag belongs to your own team.               |
| `EXPIRED`          | Flag is older than 5 ticks.                  |
| `ALREADY_CAPTURED` | Another team captured this flag first.       |
| `ERROR`            | Unexpected server error for this flag.       |

---

## Deployment

### Requirements

- Docker
- Docker Compose

### Quick Start

1. Clone the repository and enter the project directory.

2. Copy and edit the environment variables in `docker-compose.yml`:

```yaml
SECRET_KEY:    change_this_to_a_random_string   # required, no default
ADMIN_PASSWORD: your_admin_password
TICK_DURATION:  60                              # seconds, overridden by admin UI
SLA_BONUS_K:    5                               # points per service UP per tick
```

   `SECRET_KEY` is mandatory. The server will refuse to start without it.

3. Place your checker scripts in the `checkers/` directory.

4. Start the stack:

```
docker compose up --build
```

5. Open `http://localhost:5000/admin` and log in with your admin password.

6. Add teams and services, then press **Start**.

---

## Admin Panel

The admin panel is available at `/admin` after logging in.

| Section          | Actions                                                   |
|------------------|-----------------------------------------------------------|
| Teams            | Add team (name + IP), copy API key, delete team           |
| Services         | Add service (name + checker file), delete service         |
| Game Settings    | Set tick duration and SLA bonus K (triggers reset)        |
| Danger Zone      | Full competition reset (scores, flags, SLA data cleared)  |
| Checker Results  | Last known status for each (team, service) pair           |

The game can be started and stopped at any time from the dashboard header.

> **Note:** Reset clears all scores, flags, checker results, and SLA counters.
> Teams and services are preserved. Always reset with the game stopped.

---

## Writing a Checker

Place your checker in the `checkers/` directory. It will appear automatically
in the admin panel service selector.

Minimal Python skeleton:

```python
import sys, json

data    = json.loads(sys.stdin.read())
action  = data["action"]
ip      = data["ip"]

if action == "check":
    # verify the service responds correctly
    print(json.dumps({"status": "UP"}))

elif action == "put":
    flag   = data["flag"]
    # store the flag in the service
    # flag_id is public (given to attackers)
    # secret is private (stored by the server, passed back to get)
    print(json.dumps({"status": "UP", "flag_id": "user_42", "secret": "s3cr3t"}))

elif action == "get":
    flag_id = data["flag_id"]
    secret  = data["secret"]
    # retrieve and verify the flag using flag_id and secret
    print(json.dumps({"status": "UP"}))

else:
    print(json.dumps({"status": "DOWN"}))
    sys.exit(1)
```

Checkers in other languages work as long as the file is executable (`chmod +x`)
and follows the same stdin/stdout JSON protocol.

---

## Project Structure

```
gameserver/
|-- app.py                  # Main application
|-- dockerfile
|-- docker-compose.yml
|-- requirements.txt
|-- checkers/
|   |-- example.py          # Documented checker skeleton
|   `-- your_checker.py
`-- templates/
    |-- layout.html
    |-- index.html          # Scoreboard
    |-- admin.html          # Admin dashboard
    |-- login.html
    `-- rules.html          # Player-facing rules and API reference
```

---

## Environment Variables

| Variable         | Required | Default | Description                              |
|------------------|----------|---------|------------------------------------------|
| `SECRET_KEY`     | Yes      | --      | Flask session secret. Must be set.       |
| `ADMIN_PASSWORD` | No       | `admin` | Admin panel password.                    |
| `TICK_DURATION`  | No       | `60`    | Initial tick duration in seconds.        |
| `SLA_BONUS_K`    | No       | `5.0`   | Initial SLA bonus points per service UP. |
| `DATABASE_URL`   | No       | SQLite  | SQLAlchemy database URL.                 |

`TICK_DURATION` and `SLA_BONUS_K` can be overridden at runtime from the admin
panel. Changes take effect after a competition reset.
