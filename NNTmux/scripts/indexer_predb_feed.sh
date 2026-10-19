#!/bin/bash
# Every 15 min: feed a paid indexer's release names into NNTmux PreDB (indexer_predb_import.php).
# The NZBHydra API key is read from Sonarr's indexer settings at run time, so it isn't stored here.
key=$(python3 -c "
import sqlite3,json
c=sqlite3.connect('file:/mnt/user/appdata/sonarr/sonarr.db?mode=ro',uri=True)
for (s,) in c.execute('select Settings from Indexers'):
    j=json.loads(s)
    if '5076' in j.get('baseUrl',''): print(j['apiKey']); break")
[ -n "$key" ] || { logger -t indexer_predb_feed "no NZBHydra key found in Sonarr"; exit 1; }
HYDRA_KEY="$key" docker exec -u www-data -w /app -e HOME=/config -e HYDRA_KEY \
  -e INDEXER="${INDEXER:-Drunken Slug}" -e PAGES="${PAGES:-10}" -e SEED="${SEED:-0}" -e CATS="${CATS:-}" NNTmux \
  php artisan tinker --execute="require '/config/indexer_predb_import.php';" 2>&1 | tail -1 | logger -t indexer_predb_feed
