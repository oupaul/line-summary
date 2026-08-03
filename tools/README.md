# tools/

Optional add-ons that fall outside the MCP server's passive-DB-read design.
The MCP server (`line_mcp_server.py` + its 4 tools) never controls your
screen or sends any input to LINE. Scripts in this folder do — read the
warning in each one before running it.

## scroll_backfill.py

Automates scrolling up inside a specific LINE OpenChat/group window so LINE
fetches older history from its servers and writes it into the local encrypted
`.edb`. Verified: manual scrolling makes LINE persist older messages locally;
the MCP server's passive reader can then read them afterward.

**This moves your real mouse cursor and sends real wheel input.** Two
mouse-free approaches were tried and both failed:
- Synthetic `WM_MOUSEWHEEL` via `PostMessage` (no cursor movement) — no
  measurable effect; Qt likely needs real cursor presence for hit-testing.
- Windows UI Automation scroll patterns — the message pane is a custom-drawn
  Qt Quick canvas with no accessible scroll control (`GetScrollPattern()`
  returns nothing anywhere in the tree).

Real mouse wheel input is the only method confirmed to work.

### Usage

```
python tools/scroll_backfill.py "<exact chat name>" [--max-rounds N] [--stall-limit N] [--ticks-per-round N]
```

Before running:
1. LINE PC must be running and logged in.
2. Manually switch to the target chat in LINE PC so it's the one visible on screen.
3. Don't touch the mouse/keyboard until it prints "Done -- you can use the mouse again."

Defaults: `--max-rounds 60`, `--stall-limit 3` (stop after 3 consecutive
rounds with no new local message), `--ticks-per-round 15`.

Each run pays a fresh ~80s key-extraction cost (by design -- the key is never
persisted to disk). Depth reached per run varies with LINE's own load timing;
it is not deterministic.

### Dependencies (not in the main requirements.txt on purpose)

```
pip install uiautomation
```

Only needed for this optional tool; the MCP server itself doesn't require it.
