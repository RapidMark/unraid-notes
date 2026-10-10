# NNTmux on Unraid

Things I wish I'd known.

## Getting real names (PreDB)

Most posts on Usenet now have hashed or random names, e.g. `9ypUjdMZfNOnlJaB` or `78e1e0d363ad2ce9.bin`. To turn those into real release names, NNTmux looks inside each release and matches what it finds against the **PreDB**, a big list of real release names.

The PreDB starts empty. Until you fill it, almost nothing gets a proper name.

### 1. Let NNTmux look inside releases

In the container template (advanced view), set:

| Template field | Variable | Value |
|---|---|---|
| Look inside releases | `CHECK_PASSWORDED_RARS` | `true` |
| Use PAR2 names | `ADD_PAR2` | `true` |
| Fix release names | `FIX_NAMES` | `true` |

### 2. Keep it filled going forward

In the template, set:

| Template field | Variable | Value |
|---|---|---|
| IRC PRE scraper nick | `SCRAPE_IRC_USERNAME` | a name plus a few random characters, e.g. `yourname_k7q2x` |

That turns on the IRC scraper, which sits in `#PreNNTmux` on SynIRC and adds new releases as they come out (about 2,500 a day).

The nick has to be unique. If someone else is using it, the scraper quietly fails and the PreDB stops growing. If that happens, change the nick.

### 3. Backfill (optional)

The scraper only catches what's new. For older posts, backfill. Run these from the Unraid terminal.

**2014 to May 2024:** download the `.csv.gz` files from [nZEDb/nZEDbPre_Dumps](https://github.com/nZEDb/nZEDbPre_Dumps) into `appdata/nntmux/predb-import/gz/` and put [`predb_dump_import.php`](scripts/predb_dump_import.php) in `appdata/nntmux/predb-import/`. Then:

```
docker exec -u www-data NNTmux php /app/artisan tinker --execute="require '/config/predb-import/predb_dump_import.php';"
```

About 7M names.

**May 2024 to today:** put [`srrdb_backfill.php`](scripts/srrdb_backfill.php) in `appdata/nntmux/predb-import/`. Then:

```
docker exec -d -u www-data NNTmux php /app/artisan tinker --execute="require '/config/predb-import/srrdb_backfill.php';"
```

It runs in the background and logs to `predb-import/srrdb_backfill.log`. It's slow on purpose (srrDB is volunteer-run), and you can stop and restart it. Mine took about 30 hours.

**When both are done, rebuild the search index:**

```
docker exec -u www-data NNTmux php /app/artisan nntmux:populate --manticore --predb
```

## Skip junk fragments

Obfuscated posts split one episode across many random poster names. NNTmux turns each piece into its own one-file "release", from a few hundred KB up to one RAR volume (~75 MB). Useless to download. Mine were 83% of the index.

In the template (advanced view), set:

| Template field | Variable | Value |
|---|---|---|
| Minimum release size (MB) | `MIN_RELEASE_SIZE_MB` | `50` |

If you already have them, clear them out from the Unraid terminal. Movies/TV:

```
docker exec -u www-data -w /app NNTmux php artisan releases:remove-crap --type=size --time=full --delete
```

The minimum size doesn't catch the bigger ones. For those, [`junk_cleanup.php`](scripts/junk_cleanup.php) deletes one-file Hashed/Misc releases under 100 MB. Put it in `appdata/nntmux/`, then:

```
docker exec -d -u www-data -w /app NNTmux php artisan tinker --execute="require '/config/junk_cleanup.php';"
```

Progress goes to `appdata/nntmux/junk_cleanup.log`. It's slow on a big index (hours).

They keep coming, so run it hourly. Save this as `/boot/config/plugins/dynamix/nntmux-junk.cron`, then run `update_cron`:

```
23 * * * * flock -n /tmp/nntmux-junk.lock docker exec -u www-data -w /app NNTmux php artisan tinker --execute="require '/config/junk_cleanup.php';" >/dev/null 2>&1
```

## Check for stuck groups

A group's position could go bad and NNTmux would start crawling posts from years ago instead of new ones. Fixed in NNTmux since October 2026; groups that got stuck before you updated stay stuck until you fix them. Signs: old releases (2008, 2009) showing up as new, and collections piling up. Check from the Unraid terminal:

```
docker exec NNTmux mariadb -e "select name from nntmux.usenet_groups where active=1 and (last_record < first_record or last_record_postdate < now() - interval 7 day)"
```

Any names listed are stuck. Put [`fix_stuck_groups.php`](scripts/fix_stuck_groups.php) in `appdata/nntmux/`, then:

```
docker exec -u www-data -w /app NNTmux php artisan tinker --execute="require '/config/fix_stuck_groups.php';"
```

It restarts them at the server's newest posts. Your existing releases are kept.

## Start with a short backfill

Don't set a big Usenet backfill (thousands of days) on a new install. It pulls years of headers at once and release processing falls far behind. Start with a few days and raise it slowly.

If it already happened, this clears the stuck headers. Releases that have an NZB are kept:

```
docker exec -u www-data -w /app NNTmux php artisan nntmux:reset-truncate
```

## Give the database more memory

The template's **MariaDB buffer pool** (`DB_INNODB_BUFFER_POOL_SIZE`) defaults to `1G`. Set it to about half your spare RAM, e.g. `16G` or `32G`. Too small and the database lives on disk and everything slows down.

## Database on cache, NZBs on the array

Keep **Config** (the database) on the cache pool. Point **Data** (NZBs and covers) at an array share. It grows fast.

## Share your Usenet connections

NNTmux needs its own connections. If your provider allows 50, give your downloader 40 and NNTmux 10.

## Threads

Everything starts at 1 thread. What I use with 10 connections (Admin → Site Settings, **Ingestion** and **Post Processing** tabs):

| Setting | Threads | Uses connections |
|---|---|---|
| `binary_threads` | 4 | yes |
| `post_threads` | 32 | yes |
| `nfo_threads` | 8 | yes |
| `backfill_threads` | 1 | yes |
| `release_threads` | 4 | no |
| `fix_name_threads` | 4 | no |

Also on the Post Processing tab, set `max_additional_processed` to `100` (default 25).

4 binary threads was the sweet spot. At 6 I got 8x the "Lock retries exhausted" errors and 30% fewer releases, so more threads made it slower.

Post processing is different: its workers mostly wait on Usenet downloads, so more of them help. With a backlog, NNTmux puts several workers on the same part of it, up to `post_threads`. My checking rate per hour:

| `post_threads` | Batch | Releases checked per hour |
|---|---|---|
| 2 | 25 | 1,700 |
| 16 | 100 | 12,300 |
| 32 | 100 | 27,000 |

No errors at any step. At 32, NNTmux used up to 19 Usenet connections at once, so I lowered my downloader to 20 on that provider. If your provider reports too many connections, lower `post_threads` and `nfo_threads` first.

Post processing and the NFO step take turns, so while there's a big backlog the NFO queue moves slowly. It catches up once the backlog is done.

## Raise part repair

Header fetches miss some articles, and part repair fetches them again later. At the default 15,000 per run it falls far behind on a busy group like boneless (millions a day). Set `max_part_repair` to `100000` (Admin → Site Settings → **Ingestion**).

## Metadata keys

Fill in the template's **TMDB**, **OMDb**, **TVDB** and **Fanart.tv** keys (advanced view). Trakt now charges for API access; you can leave it empty. TVDB also needs your subscriber **PIN**, otherwise it runs in local mode only.

When NNTmux starts, it writes one line per source it can't use (missing key or switched off) at the top of the log, and then skips those sources quietly.

OMDb is how NNTmux gets IMDb data. IMDb answers scripts with a bot check (`HTTP 202`, empty page) from any network, so direct IMDb lookups rarely work. The template's **IMDb scraping** field is on: after a block NNTmux pauses IMDb lookups for an hour (**IMDb block pause**) and then tries once. Leave **imdbapi.dev fallback** off; that site is gone.

## Compressed headers

On by default (template: **Compressed headers**). Headers download compressed, which saves a lot of bandwidth. If your provider doesn't support it (`XFEATURE COMPRESS GZIP`), set it to `false`.

Images before 2026-10-09 often cut compressed headers off, which logged `Decompression of OVER headers failed.` and stopped part repair from ever running. Update the container if you see that.

## Passworded and unreadable archives

NNTmux looks inside each release's archive to spot passwords and real file names. Until October 2026 it could only read RAR and ZIP, so 7z uploads (most of them passworded) and obfuscated posts stayed at "unknown" forever.

Now it reads 7z too (the template's **7-Zip path**), samples a few files of obfuscated posts to find the archive (**Archive probe files**), and gives an archive it can't read one more try a day later (**Archive retry delay**). Plain videos count as not passworded.

Passworded releases stay hidden from Sonarr and Radarr as long as **show passworded releases** is off (the default), so they never get downloaded.

To re-check releases that were already stuck before you updated, run once from the Unraid terminal:

```
docker exec -u www-data -w /app NNTmux php artisan releases:retry-archive-inspection --dry-run
docker exec -u www-data -w /app NNTmux php artisan releases:retry-archive-inspection
```

Whatever still can't be read after that stays "unknown"; most of those are old posts whose pieces are gone from the server.

## Shorter collection timeout

Some uploads post every piece of a file under a different random subject, often in different groups. NNTmux can't join them, so each piece sits as an unfinished collection until the timeout deletes it. At the default 48 hours they pile up into millions and slow everything down.

Set `collection_timeout_hours` to `12` (Admin → Site Settings → **Ingestion**). Normal posts finish long before that.

## Use it through NZBHydra

If you have NZBHydra, add NNTmux there, not directly in Sonarr and Radarr. Otherwise every search hits NNTmux twice.

In NZBHydra, give NNTmux the highest **score** (I use 100) so its copy wins when several indexers have the same release, and clear its API hit and download limits.

NNTmux allows 60 API requests a minute per IP, and that isn't a setting. With NZBHydra in front it's only one client, which helps.

## What it won't find

Many new P2P uploads post each piece of a file under its own random subject, in random groups. Only the uploader's NZB says which pieces belong together, and NNTmux can't assemble them from headers. In my test, 7 of 10 new releases on a paid indexer were posted like this. Keep a paid indexer behind NNTmux in NZBHydra for those.
