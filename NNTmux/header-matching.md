# Matching obfuscated uploads from headers

What I found while trying to make NNTmux find what paid indexers find, without their NZBs. Measured in October 2026 on Eweka, mostly in alt.binaries.boneless, .moovee, .hdtv and the multimedia groups. The scripts are in [`scripts/regroup/`](scripts/regroup/).

## Why NNTmux misses so much

Comparing DrunkenSlug's newest 400 movies and TV episodes with NNTmux, NNTmux had only 10 of the movies and 0 of the TV by name. There were four reasons:

1. **NNTmux never names most new releases.** 82% of a day's releases (about 38,000) stayed in Other/Misc with random names.
2. **Its PreDB had stopped filling.** The IRC scraper hung after a reconnect (fixed in NNTmux#1900), and srrDB only lists scene releases, not P2P.
3. **Uploads spread over groups we didn't read** (see [Index every group an upload uses](README.md#index-every-group-an-upload-uses)).
4. **Most new TV is posted so that only the uploader's NZB can put it back together** (pattern E below).

Checking DrunkenSlug's listing times against post times: new TV is listed within 15 minutes (half of it) or about 70 minutes (the rest). So DrunkenSlug doesn't wait days for NZBs. It has them at posting time.

## The posting patterns

| | Subject | Poster | Message id | Volume seen | From headers alone |
|---|---|---|---|---|---|
| A | `[27/62] "X8Iqg1gnf6CUFzEHc7qbsut1tEyEdj4e" yEnc (127/942)` | `bob@home.com`, `bob@news.in` | `<random-<13-digit ms>@nyuu>` | ~413 GiB/h in boneless | Rebuildable. All encrypted. |
| B | `"<hex32>.bin" yEnc` | new `<hex8>@archive.invalid` per article | random | small | No |
| C | `elys-<16 hex> - [8 chars] "random" yEnc` | `elys-<id>` per upload | | small | Probably, not done |
| D | `<7-8 digit job id>-n [01/97] - "random"` | random | | small | Probably, not done |
| E | `Gdfk42x4uykZzv7HGTUKC09R5tFVFI7GpjOz6d` (38 random characters) | new `10hex <7hex@5hex.com>` per article | `<7hex$7hex$7hex@10hex.5hex>` | 9.8% of all sampled volume, 23% of hdtv | No |
| F | message id = subject = random UUID | new `13 chars@ngPost.com` per article | `<uuid@ngPost>` | 7.9% | No |
| G | `quxBx44jcyykh80szgi9` (20 random characters) | one `10 lowercase@5.3` per upload, e.g. `wpqbi363zb@amtxh.3py` | `<letters-<13-digit ms>@nyuu>` | a few uploads an hour (LuCY encodes) | Found and named cheaply; rebuilt by downloading once |

NNTmux drops every article without a part counter like `(127/942)` while reading headers, so patterns B, E, F and G never reach its database.

### A: file number kept, random name on every article

NNTmux makes one collection per article (600,000 an hour in boneless) because the name in quotes differs on every article. But each article still says which file it belongs to (`27/62`), and NNTmux's binaries table keeps the part number and part count. So:

- **Files:** group by poster + total files + file number + total parts. If a part number repeats, or more than 5 minutes pass, start a new copy.
- **Uploads:** chain file f−1 → f when the next file starts within 2 minutes of the previous one ending. Several uploads run interleaved; the same-size data files and the timing keep them apart.
- **Shape:** files 1–11 are PAR2 (1, 5, 8, 16, 31… parts, doubling), then about 50 equal RAR volumes and a smaller last one.
- **Result:** one hour gave 35 uploads; 33 named from the PAR2 index (`Backrooms.2026…Remux-CiNEPHiLES`, `Animal.House.1978…`). None existed in NNTmux or DrunkenSlug under those names.
- **Catch:** every RAR checked was RAR5 with **header encryption** (first block type 4), so the password is needed even to list the files. These are probably another indexer's private uploads. `regroup.py` still runs, skips encrypted uploads and imports anything unlocked.

### E: everything random, every article

Checked with a DrunkenSlug NZB (`Adults.2025.S01E03…2160p`, 4,156 articles):

- **Each article is unique:** its own random poster, its own random subject, and its own random group out of about 20 (erotica, ath, cores, nl, mom, hdtv, town…). All were posted within 11 seconds.
- **Size doesn't help:** 90% of articles are 739,487–739,855 bytes, which is what every tool produces.
- **The signature narrows it a lot:** the poster and message-id formats cut 56,696 articles in that window to about 8,000 (this upload plus one other from the same tool). But nothing separates two uploads by the same tool posted at the same moment.
- **Other headers are fake:** `Organization` and `User-Agent` are randomized ("Anon-Drop/8.8", "NNTP-Poster/1.0"). `Injection-Info: news.hitnews.com` is shared by many uploaders.
- **The body gives it away, but only after downloading:** `=ybegin part=1249 total=3455 line=128 size=2476370919 name=<random>` and `=ypart begin= end=` place an article exactly. Reading them means downloading everything, and this tool alone posts about 62 GiB/h in hdtv, several TB a day. Not practical.

DrunkenSlug's new TV in boneless was this pattern.

### G: one random poster per upload, shuffled

- **The poster alone isolates the upload:** `wpqbi363zb@amtxh.3py` posted 3,509 articles (2.41 GiB) in 1.8 minutes.
- **The small articles name it:** the smallest is an SFV (cksfv), the next a 48 KB PAR2 index: `The.Psychic.Files.2026.1080p.AMZN.WEBRip.HEVC.10bit.AAC-LuCY`, 22 files.
- **The volumes can't be told apart from outside:** all 20 volumes of 100 MB have the same random yEnc name, the same size and the same part count, and part numbers come in random order. So no header or timing says which volume an article belongs to.
- **But the PAR2 index can sort them once downloaded.** It has, per file, the MD5 of the first 16 KB and a CRC32 + MD5 per block. The block size here (1,139,760) isn't the article size (716,800), so:
  1. Find each volume's part 1 by the 16 KB MD5.
  2. For each block, add the candidate article(s) whose CRC makes the block's CRC32 come out right. That's at most 2 new articles per block, so at most 400 tries.
  3. Compute each article's CRC per block once, and combine CRCs mathematically (zlib's crc32_combine with the length operator cached) instead of re-reading data. That took assembly from about 3½ hours to **41 seconds**.
- **Verified:** 22/22 volumes matched their PAR2 MD5 and the SFV, and `7z t` said "Everything is Ok" (no password, mkv + nfo + sample inside).
- **Indexed:** the output is an NZB, not files. The first three (Frankenstein.2025, Red.Days.2.Cecilia.2026, The.Psychic.Files.2026, all LuCY) were imported, and NNTmux's look-inside opened them through those NZBs (no password, mkv listed).
- **Cost:** one full download per upload (about 2.4 GB, 4 minutes), roughly 60 GB a day at the rate seen.

## Technical details

### What the PAR2 index gives you

The PAR2 index (`.par2`, usually the smallest or second smallest article of an upload) is a set of packets, each starting with `PAR2\0PKT`, length at offset 8, type at offset 48:

| Packet | Contents | Used for |
|---|---|---|
| `PAR 2.0\0Main` | block (slice) size, number of files | Splitting files into blocks |
| `PAR 2.0\0FileDesc` | file id, MD5 of the whole file, **MD5 of the first 16 KB**, length, **real file name** | Naming the release; finding each file's first article; final check |
| `PAR 2.0\0IFSC` | per block: MD5 + **CRC32** | Placing every following article |
| `PAR 2.0\0Creator` | the tool (e.g. "ParPar 0.8.1") | Recognising PAR2 recovery files |

The last block of a file is zero-padded to the full block size before its checksum is taken, so the padding has to be added when comparing.

The release name is the part all archive volumes share (`.partNN.rar`, `.rNN`, `.7z.NNN`, `.NNN` stripped), ignoring `.nfo`/`.sfv` and other extras.

### What the SFV is for

These uploads include an SFV made by cksfv (`; Generated by cksfv v1.3.15…`, then `filename CRC32` per volume). The SFV is written by the uploader independently of the PAR2, so it's a second, independent check that a rebuilt volume is byte-for-byte right. The first test used it to confirm the rebuilt volumes before trusting the PAR2-only check. The SFV is also put into the NZB, where download clients use it as usual.

### How the assembler got 300 times faster

- **First version (about 10 minutes per 100 MB volume, 3½ hours per release):** for every block, try candidate articles by concatenating their data and running CRC32 over up to 1.1 MB per try, up to 400 tries per block.
- **Second version (41 seconds for the whole 2.4 GB release):**
  - **Each article is checksummed once,** split at the block boundaries it crosses, giving a small CRC32 per piece.
  - **A candidate block's CRC32 is built by combining those piece CRCs** (CRC32 is linear: `crc(A+B)` follows from `crc(A)`, `crc(B)` and `len(B)`, as zlib's `crc32_combine` does). No data is re-read.
  - **The combine step uses a 32×32 bit matrix for "advance over N zero bytes".** Building it is the slow part, so it's cached per length. Piece lengths repeat, so there are only a few dozen distinct ones, and each combine is then one cheap matrix-vector product.
- **Other speed-ups:**
  - **yEnc decoding** uses `bytes.translate` plus handling the `=` escapes, instead of a Python loop per byte.
  - **Downloading** uses 4 connections with a 60-second socket timeout. The first attempt with 8 connections hung silently (connections were maxed out). Message ids come from the catalogue instead of listing 300,000 headers again.
- **Cost per release:** download about 7½ minutes for 2.4 GB on 4 connections (4 minutes in the scheduled job), assembly 41 seconds, about 2.9 GB of RAM while it runs.

### Limit: big uploads can't be placed

The search tries combinations of candidate articles until a block's CRC32 matches. The number of combinations is (same-size volumes) to the power of (articles per block). On a 2.4 GB release that's small. On a 9.3 GB 2160p upload (83 files, 13,300 articles) it runs to billions, more than a 32-bit CRC can tell apart, so even a match could be wrong.

The first such upload (`Oddity.2024.2160p…-LuCY`, 2026-10-20) kept the index job busy for 21 hours and blocked every run after it. Since then:
- the search gives up on a block after 200,000 tries ("too many combinations") and the upload is marked "could not rebuild";
- the index job stops at the first file that fails, and only imports an upload when every file was rebuilt (before, a failed file was just left out of the NZB).

### Password checks without extracting

- **Headers encrypted (password needed even to list files):**
  - RAR5: the first block after the signature `Rar!\x1a\x07\x01\x00` is type 4, the archive encryption header.
  - RAR4: the main header (type 0x73) has flag 0x0080.
- **Only the file contents encrypted:**
  - RAR5: the first file header (type 2) has an extra record of type 0x01.
  - RAR4: the first file header (type 0x74) has flag 0x0004.
- **7z and zip** are left to NNTmux's own check after import.

The check reads the start of the first archive volume (the first one or two articles). With pattern G that article is only known after placing, so the check runs after assembly. With pattern A the file order is known, so it costs one extra article.

Trying the end of each volume instead (to avoid needing the first article) didn't work. The bytes before the zero padding couldn't be read reliably as plain or encrypted.

### Building the NZB

- **Data volumes:** real names from the PAR2 index, articles in the placed order.
- **Single-article extras, named by content:**
  - PAR2 index → `<name>.par2`
  - SFV (starts with `;` / mentions cksfv) → `<name>.sfv`
  - anything else → `<name>.nfo`
- **PAR2 recovery files:** articles left over, grouped by size, where there's exactly one article per part number → `<name>.volNN.par2`. Download clients recognise PAR2 files by content, so the exact names don't matter.
- **Segment sizes** are the raw article sizes as downloaded. Poster and groups are the upload's own.
- **Import:** `php artisan nntmux:import-nzbs --folder=/config/regroup/import --filename --delete --delete-failed`. `--filename` makes NNTmux use the NZB's file name as the release name. NNTmux then categorises it and looks inside like any other release.

### Bugs met on the way

- **Article subjects often have a size after the part counter** (`yEnc (2/3137) 13156526610`). Patterns that expect the counter at the end miss them.
- **SimpleXML needs `->attributes()['name']` for attributes of namespaced elements** like `newznab:attr`. Plain `['name']` silently returns empty, which left 19,196 PreDB rows without size and category until fixed.
- **Newznab categories 10 and 20 (Other/Misc, Other/Hashed) aren't 1000s/2000s.** Mapping on the first digit labelled them Console and Movies.
- **NZBHydra stops at 15 pages (1,500 results) per query.** The indexer's own API allows 125,000 per category.
- **`pkill -f <pattern>` matches the shell running it** if the pattern is in the command line. Kill by PID.

## Matching unnamed releases to indexer names afterwards

With a full DrunkenSlug backfill in PreDB (482,000 movie and 655,000 TV names, back to 2008), unnamed NNTmux releases can be matched by post time (±2 min) and size (±1%), always with time-shifted controls:

| | Unnamed candidates | Matched | By chance (controls) | Real |
|---|---|---|---|---|
| Movies (over 70 min) | 5,980 | 1,173 | ~25 | ~1,150, but all except 19 one French dub uploader (VFF), so not applied |
| TV (18–65 min) | 46,368 | 508 | 68–87 | ~430, mostly English and recent |

For TV, the 212 unambiguous pairs (one name per release and one release per name) were applied with NNTmux's own rename (`ReleaseUpdateService::updateRelease`, type `PreDB FT Exact, `), which re-categorises and updates the search index. They came out as 79 TV Foreign, 37 Sport, 31 HD, 21 SD, 2 UHD, and 35 that stayed in Hashed/Misc because NNTmux didn't recognise the name format.

A plain `php artisan predb:check` after the backfill linked another 27,292 already-named releases to PreDB entries.

## Things that didn't work

- **Matching on size and time alone:** within a busy window, random sizes matched about as often as the real ones. Always compare with a time-shifted control. The one batch of "matches" I almost trusted (Futurama) turned out to be a Chinese anime upload.
- **Matching DrunkenSlug names to unnamed NNTmux releases by post time and size:** after a full DrunkenSlug movie backfill, 1,173 unnamed movies matched for real (the control gave about 25), but all except 19 were one French dub uploader (`VFF`, Serpico).
- **Titles embedded in the video files:** only 2,097 unnamed releases had one, mostly old German dubs (TVP).
- **Scene file names inside releases** (`itg-simpsons-s21e22`): 330 matched PreDB by group + episode + show words, all old SD.

## What runs (every 15 minutes unless noted)

| Script | Does |
|---|---|
| `regroup.py` | Pattern A from NNTmux's unfinished pieces; PAR2 name, password check, import |
| `catalog.py` | Pattern G from raw headers; PAR2 name; names into PreDB as `usenet-par2`; keeps message ids 7 days |
| `index.py` | Pattern G uploads named in the last 48 h: download once, rebuild order, password check, NZB, import (up to 4 per run) |
| `signatures.py` | Weekly: posting signatures by volume, and who claims them |
| `techniques.py` | One entry per technique: recognise, fetch, group |
| `assemble.py` | PAR2-based placement; `assemble.py <group> <poster> <dir>` also writes the files for testing |

## Open ideas

- Patterns C and D look groupable (shared upload id / job id) but are small.
- On-demand rebuild of a pattern E upload for one wanted release: download everything posted by that tool in the cluster (about twice the release) and place it by the yEnc headers. Not built.
- Upstream: the pattern A grouping and the PAR2 assembler would help every NNTmux install. Not as a PR: A only finds encrypted uploads, and G needs full downloads (a design decision for the maintainer). An issue sharing the findings was considered and parked (2026-10-19); the scripts work beside an unmodified NNTmux via nntmux:import-nzbs.

## Stats and health checks (planned)

Two different things, kept apart on purpose:

**Health checks**: states with a threshold. They should warn, not draw charts. These are a candidate PR for NNTmux's service-status page (which already has severities), with one log line when the state changes:

| Check | Warns when | Would have caught |
|---|---|---|
| PreDB feed | the newest entry from a source is older than N hours | the IRC scraper hanging for 25 hours |
| Header lag | a group's newest header is more than N minutes behind the server | boneless falling 1.6 hours behind |
| Stuck uploads | incomplete collections older than N hours pass a threshold | 1,606 uploads stuck because one of their groups wasn't indexed |

**Stats**: counts over time, where the trend matters. First as our own daily/weekly report:

- **Releases per day by category** (movies, TV, software, audio, books, XXX, other): created, named, unnamed, passworded.
- **Naming sources:** subject, PreDB by source (srrDB / DrunkenSlug / usenet-par2), look-inside, PAR2.
- **Header volume by posting pattern:** handled by NNTmux, claimed by a technique, unclaimed, including articles dropped at ingest for having no part counter. That counter is the one item that could later become a second NNTmux PR (a real time series).
- **Per technique:** found / named / passworded / imported.
- **Coverage against DrunkenSlug:** share and delay for new movies and TV.

NNTmux already exports Prometheus metrics for releases by category, renamed releases, PreDB entries and matches, backlog and connections, but none of the checks above.

Order: build the stats report, then the health-check PR.

## Updating

**NNTmux (the image):** sync the fork with upstream, build, recreate the container, changelog. The scripts live outside the image (appdata + cron files on the flash drive), so an update doesn't touch them, but they rely on NNTmux internals: the collections/binaries/parts and predb tables, `nntmux:import-nzbs`, and the settings classes (`IngestionConfiguration`, `ConfigurationProvider`). After every NNTmux update:

1. `DRY=1 python3 regroup.py`: runs and lists its techniques.
2. Run `catalog.py` and `index.py` once and check their lines in `regroup.log`.
3. Import one NZB from `import/` and check it shows up and NNTmux opens it.

**The scripts:** one source of truth. The Python scripts live in this repo (`scripts/regroup/`), and `appdata/nntmux/regroup/` has symlinks to them plus the state and logs (state files, `catalog/`, `import/`, `regroup.log`, reports). Edit here and commit; the cron jobs use the change on their next run. The exception is `catalog_predb.php`: it runs inside the NNTmux container, which can't see this repo, so after editing it, copy it to `appdata/nntmux/regroup/`.

**Notes and memory:** updated with each change.

## Plugin system: not yet

`techniques.py` (one entry per technique: recognise, fetch, group) is enough for now. Only two techniques work (A and G), and adding one is a small, contained change. Revisit a real plugin design when there are 4–5 working techniques, when they need their own settings, or when offering this to NNTmux. There it should become a grouping-strategy interface inside NNTmux's release creation, not scripts on the side. `signatures.py` shows when a new high-volume style appears.
