# Graph Report - cloud-dj  (2026-11-05)

## Corpus Check
- 5 files · ~41,004 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 2, .csv 2)

## Summary
- 217 nodes · 445 edges · 19 communities (12 shown, 7 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `951ff03e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- admin_change_password
- _enrich_now
- route
- Cloud-DJ
- add
- _prepare_video
- install.ps1
- _system_stats
- install.sh script
- _apply_loudness
- stream_audio
- direct_video
- proxy_seg
- _no_stale_pages
- downloads
- inject_commit
- suggested
- backup.sh

## God Nodes (most connected - your core abstractions)
1. `get_db()` - 49 edges
2. `set_now_playing()` - 11 edges
3. `_enrich_now()` - 11 edges
4. `get_next_pending()` - 10 edges
5. `suggested()` - 10 edges
6. `get_setting()` - 9 edges
7. `_prepare_video()` - 9 edges
8. `_autodj_pick()` - 8 edges
9. `add()` - 8 edges
10. `auto_advance()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `_autodj_pick()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 2 → community 3_
- `add()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 3 → community 5_
- `admin_change_password()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 3 → community 1_
- `work()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 3 → community 23_
- `handle_connect()` --calls--> `get_db()`  [EXTRACTED]
  app.py → app.py  _Bridges community 3 → community 11_

## Import Cycles
- None detected.

## Communities (19 total, 7 thin omitted)

### Community 1 - "admin_change_password"
Cohesion: 0.09
Nodes (12): admin_change_password(), admin_users(), ban_check(), _ban_state(), check_password_hash(), forgot_password(), generate_password_hash(), init_db() (+4 more)

### Community 2 - "_enrich_now"
Cohesion: 0.12
Nodes (16): admin_settings_crossfade(), advance(), _advance_from_failed(), _auto_start(), _autodj_pick(), _enrich_now(), get_next_pending(), get_setting() (+8 more)

### Community 3 - "route"
Cohesion: 0.08
Nodes (31): admin(), admin_history(), admin_love(), admin_settings(), admin_settings_chat(), admin_settings_consecutive(), admin_settings_leaderboard(), admin_settings_loudness() (+23 more)

### Community 4 - "Cloud-DJ"
Cohesion: 0.20
Nodes (9): Cloud-DJ, Features, Install, Linux / Raspberry Pi, Login, Mac, Tech, Windows (installer script) (+1 more)

### Community 5 - "add"
Cohesion: 0.20
Nodes (7): add(), add_from_loved(), auto_advance(), clean_yt_url(), fetch_title(), replay_from_history(), run_ytdl()

### Community 6 - "_prepare_video"
Cohesion: 0.22
Nodes (6): _cached_video_path(), muxed_video(), _prepare_video(), _prune_video_cache(), _video_lock(), _ytdlp_base()

### Community 7 - "install.ps1"
Cohesion: 0.42
Nodes (8): Install-Direct(), Install-WithWinget(), Refresh-Path(), Test-RealCommand(), Test-ValidPe(), Write-Info(), Write-Ok(), Write-Warn()

### Community 8 - "_system_stats"
Cohesion: 0.29
Nodes (4): admin_system(), _lan_ip(), _read_proc(), _system_stats()

### Community 9 - "install.sh script"
Cohesion: 0.60
Nodes (5): err(), info(), ok(), install.sh script, warn()

### Community 10 - "_apply_loudness"
Cohesion: 0.40
Nodes (3): _apply_loudness(), _loudness_sidecar(), _measure_loudness()

### Community 11 - "stream_audio"
Cohesion: 0.21
Nodes (4): handle_connect(), handle_react_message(), handle_send_message(), stream_audio()

### Community 23 - "suggested"
Cohesion: 0.16
Nodes (9): _album_genre(), _deezer_json(), _ensure_genre(), work(), _lookup_genre(), _parse_artist_title(), suggested(), genre_pool() (+1 more)

## Knowledge Gaps
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `route` to `app.py`, `admin_change_password`, `_enrich_now`, `add`, `stream_audio`, `suggested`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Should `app.py` be split into smaller, more focused modules?**
  _Cohesion score 0.08333333333333333 - nodes in this community are weakly interconnected._
- **Why does `suggested()` connect `suggested` to `app.py`, `_enrich_now`, `route`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Should `admin_change_password` be split into smaller, more focused modules?**
  _Cohesion score 0.09090909090909091 - nodes in this community are weakly interconnected._
- **Why does `proxy_seg()` connect `proxy_seg` to `app.py`, `route`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **Should `_enrich_now` be split into smaller, more focused modules?**
  _Cohesion score 0.11965811965811966 - nodes in this community are weakly interconnected._
- **Should `route` be split into smaller, more focused modules?**
  _Cohesion score 0.08140610545790934 - nodes in this community are weakly interconnected._