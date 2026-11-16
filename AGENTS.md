# AGENTS.md — Engineering Rules & Anti-Mistake Checklist

**Rule #0: Do not make stupid mistakes. Verify on real data and real browser/server state before claiming something works.**

## Mandatory Checklist Before Saying "Done"

1. **Never Trust Browser Cache When Updating Static Assets (`index.html`, `styles.css`, `app.js`, `viewer3d.js`)**:
   - Always send `Cache-Control: no-store` on static file responses.
   - Always bump the cache-busting query string (`?v=N`) on `<link rel="stylesheet">` and `<script src="...">` in `index.html` whenever CSS or JS changes so a normal `F5` reload picks up the changes.

2. **Never Use `encodeURI()` on File Paths That Can Contain `#` or `?`**:
   - Many Cyberpunk 2077 mod archives start with `#` or `###` (e.g., `###-rebeccaheadband.archive`).
   - `#` is the URL fragment delimiter—browsers strip everything after an unencoded `#` before sending the HTTP request, causing `404 Not Found`.
   - Always sanitize cache folder names (`safe_archive_key`) and encode path segments with `encodeURIComponent()` (JS) / `urllib.parse.quote(rel, safe="/")` (Python).

3. **Test Against the User's Actual Game Directory, Not Just Mock Fixtures**:
   - Never default to mock mods when a real Cyberpunk 2077 installation exists on disk.
   - When scanning a Cyberpunk 2077 game root, **only** scan `archive/pc/mod`, `r6/tweaks`, `r6/scripts`, and `mods`—never recursively walk `archive/pc/content` or `archive/pc/ep1` (100GB+ of basegame archives).
   - Filter out non-clothing TweakXL records (weapons, `Preset_*`, cyberware, stat shards, UI records, numeric `LocKey#` IDs) and non-clothing archives (tattoos, VTK body textures, button replacers, addon refit patches).
   - Collapse `$instances` color tables and multi-block `entityName` color variants into a single item card instead of flooding the grid with 16–30 duplicate cards per item.

4. **Never Spawn Cold `.NET` CLI Processes in a Loop**:
   - Spawning `WolvenKit.CLI.exe` costs ~4 seconds of `.NET` + hash-table startup per invocation.
   - Always use the persistent in-memory `WolvenKitDaemon.exe` pipe (`tools/wk_daemon/Program.cs`), which keeps `IHost` warm in RAM (`~100–500 ms` per archive).
   - Remember that custom ArchiveXL paths not in WolvenKit's vanilla hash table appear as `<hash>.bin` prior to unbundling—any uncook regex must include `|\.bin$` or it will extract 0 files from custom archives.
   - Never write a `.done` cache marker for a failed/empty extraction without version-stamping (`CACHE_MARKER_VERSION`).
   - Background batch extraction must always yield immediately to foreground user actions (`_PRIORITY_WAITING`).

