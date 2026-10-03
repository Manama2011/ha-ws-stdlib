# ha-ws-stdlib

A tiny command-line WebSocket client for the **Home Assistant** Core API that needs
nothing but the Python standard library.

*Deutsch:* Kleines Kommandozeilen-Skript für die WebSocket-Schnittstelle von Home
Assistant – ohne Zusatzpakete, läuft direkt im SSH-Add-on.

## Why

Some things in Home Assistant are only available over WebSocket, not over REST:
setting area, icon, labels or category of an entity or device, reading and saving
dashboards, listing repair issues, label and category registries, and more.

Inside the SSH add-on there is neither `websockets` nor `websocket-client`, and `pip`
refuses to install them (PEP 668). Whatever you install with force tends to disappear
with the next add-on update. This script implements the small part of the WebSocket
protocol it needs itself – one file, no dependencies.

## Usage

Send a JSON list of commands **without** `id` on stdin; the results come back as a
JSON list on stdout, in the same order.

```bash
echo '[{"type":"config/label_registry/list"}]' | python3 ha_ws.py
```

Inside an add-on (SSH add-on, Studio Code Server …) it works out of the box: it uses
`SUPERVISOR_TOKEN` and talks to `ws://supervisor/core/websocket`.

Several commands in one connection:

```bash
cat > cmds.json <<'EOF'
[
  {"type": "config/entity_registry/update",
   "entity_id": "automation.my_automation",
   "icon": "mdi:lightbulb",
   "labels": ["lighting"],
   "area_id": "living_room"},
  {"type": "repairs/list_issues"}
]
EOF
python3 ha_ws.py < cmds.json
```

From another machine over SSH (no quoting trouble, the JSON travels on stdin):

```bash
ssh root@homeassistant "python3 /config/scripts/ha_ws.py" < cmds.json
```

### A few useful commands

| What | Command |
|---|---|
| List labels | `{"type": "config/label_registry/list"}` |
| List entities / devices | `{"type": "config/entity_registry/list"}` / `{"type": "config/device_registry/list"}` |
| Change an entity | `{"type": "config/entity_registry/update", "entity_id": "…", "area_id": "…", "icon": "…", "labels": ["…"]}` |
| Set an automation category | `{"type": "config/entity_registry/update", "entity_id": "automation.x", "categories": {"automation": "<category id>"}}` |
| Change a device | `{"type": "config/device_registry/update", "device_id": "…", "name_by_user": "…", "area_id": "…", "labels": ["…"]}` |
| Read a dashboard | `{"type": "lovelace/config", "url_path": "my-dashboard"}` |
| Save a dashboard | `{"type": "lovelace/config/save", "url_path": "my-dashboard", "config": { … }}` |
| Repair issues | `{"type": "repairs/list_issues"}` |

Tip: after a registry update, verify with a `…/list` command instead of reading the
files in `/config/.storage` – Home Assistant writes those with a delay.

### Outside an add-on

Create a long-lived access token in your Home Assistant profile and point the script
at Home Assistant directly:

```bash
export HA_WS_TOKEN='…'          # long-lived access token
export HA_WS_HOST=192.168.1.10
export HA_WS_PORT=8123
export HA_WS_PATH=/api/websocket
echo '[{"type":"get_config"}]' | python3 ha_ws.py
```

| Variable | Default | Meaning |
|---|---|---|
| `SUPERVISOR_TOKEN` | set by the Supervisor | token used inside add-ons |
| `HA_WS_TOKEN` | – | overrides `SUPERVISOR_TOKEN` |
| `HA_WS_HOST` | `supervisor` | host |
| `HA_WS_PORT` | `80` | port |
| `HA_WS_PATH` | `/core/websocket` | path |
| `HA_WS_TIMEOUT` | `30` | socket timeout in seconds |

## Limitations

- Plain `ws://` only, no TLS. Inside add-ons that is what you want; from outside use
  it on your LAN or through an SSH tunnel.
- No subscriptions: for every command the script waits for its `result` message and
  ignores events.
- Failed authentication counts as a failed login in Home Assistant – do not loop on a
  wrong token if IP banning is enabled.
- Tested inside the SSH add-on (Python 3.14) against Home Assistant 2026.10. The
  direct connection with a long-lived token is the same code path with other
  host/port/path values, but I have only used it through the Supervisor.

## License

MIT – see [LICENSE](LICENSE).
