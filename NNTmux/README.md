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

Everything starts at 1 thread. What I use with 10 connections (Admin → Site Settings → Advanced - Threaded Settings):

| Setting | Threads | Uses connections |
|---|---|---|
| `binarythreads` | 4 | yes |
| `postthreads` | 2 | yes |
| `nfothreads` | 2 | yes |
| `backfillthreads` | 1 | yes |
| `releasethreads` | 4 | no |
| `fixnamethreads` | 4 | no |

Keep the ones that use connections at or under your NNTmux connection count. The others only use CPU.

4 binary threads was the sweet spot. At 6 I got 8x the "Lock retries exhausted" errors and 30% fewer releases, so more threads made it slower.
