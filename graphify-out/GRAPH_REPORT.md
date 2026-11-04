# Graph Report - cloud-dj  (2026-11-04)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 173 nodes · 361 edges · 27 communities (11 shown, 16 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ef30a952`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 45 edges
2. `_prepare_video()` - 9 edges
3. `advance()` - 8 edges
4. `_enrich_now()` - 8 edges
5. `get_next_pending()` - 8 edges
6. `set_now_playing()` - 8 edges
7. `skip()` - 8 edges
8. `add()` - 8 edges
9. `auto_advance()` - 8 edges
10. `admin_change_password()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `login()` --calls--> `User`  [EXTRACTED]
  app.py → app.py  _Bridges community 12 → community 1_
- `admin_change_password()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 1 → community 3_
- `admin_change_password()` --references--> `route`  [EXTRACTED]
  app.py →   _Bridges community 1 → community 4_
- `_prepare_video()` --calls--> `_apply_loudness()`  [EXTRACTED]
  app.py → app.py  _Bridges community 10 → community 6_
- `handle_connect()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 11 → community 3_

## Import Cycles
- None detected.

## Communities (27 total, 16 thin omitted)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (11): admin_change_password(), admin_users(), ban_check(), _ban_state(), check_password_hash(), forgot_password(), generate_password_hash(), init_db() (+3 more)

### Community 2 - "Community 2"
Cohesion: 0.20
Nodes (9): advance(), _auto_start(), _enrich_now(), get_next_pending(), now_playing(), queue(), remove_item(), set_now_playing() (+1 more)

### Community 3 - "Community 3"
Cohesion: 0.26
Nodes (12): admin(), admin_love(), clear_leaderboard(), clear_users(), export_csv(), get_db(), import_csv(), leaderboard() (+4 more)

### Community 4 - "Community 4"
Cohesion: 0.17
Nodes (8): admin_settings(), admin_settings_leaderboard(), admin_settings_suggested(), index(), leaderboard_enabled(), love_toggle(), proxy_video(), scoring_enabled()

### Community 5 - "Community 5"
Cohesion: 0.20
Nodes (7): add(), add_from_loved(), auto_advance(), clean_yt_url(), fetch_title(), replay_from_history(), run_ytdl()

### Community 6 - "Community 6"
Cohesion: 0.18
Nodes (7): _cached_video_path(), direct_video(), muxed_video(), _prepare_video(), _prune_video_cache(), _video_lock(), _ytdlp_base()

### Community 7 - "Community 7"
Cohesion: 0.42
Nodes (8): Install-Direct(), Install-WithWinget(), Refresh-Path(), Test-RealCommand(), Test-ValidPe(), Write-Info(), Write-Ok(), Write-Warn()

### Community 8 - "Community 8"
Cohesion: 0.29
Nodes (4): admin_system(), _lan_ip(), _read_proc(), _system_stats()

### Community 9 - "Community 9"
Cohesion: 0.60
Nodes (5): err(), info(), ok(), install.sh script, warn()

### Community 10 - "Community 10"
Cohesion: 0.40
Nodes (3): _apply_loudness(), _loudness_sidecar(), _measure_loudness()

### Community 11 - "Community 11"
Cohesion: 0.40
Nodes (3): handle_connect(), handle_react_message(), handle_send_message()

## Knowledge Gaps
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 11`, `Community 12`, `Community 14`, `Community 15`, `Community 18`, `Community 19`, `Community 22`, `Community 23`, `Community 24`, `Community 25`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08333333333333333 - nodes in this community are weakly interconnected._
- **Why does `_system_stats()` connect `Community 8` to `Community 0`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.1111111111111111 - nodes in this community are weakly interconnected._
- **Why does `proxy_seg()` connect `Community 13` to `Community 0`, `Community 3`, `Community 4`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._