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
- Upstream: the pattern A grouping and the PAR2 assembler would help every NNTmux install.

## Plugin system: not yet

`techniques.py` (one entry per technique: recognise, fetch, group) is enough for now. Only two techniques work (A and G), and adding one is a small, contained change. Revisit a real plugin design when there are 4–5 working techniques, when they need their own settings, or when offering this to NNTmux. There it should become a grouping-strategy interface inside NNTmux's release creation, not scripts on the side. `signatures.py` shows when a new high-volume style appears.
