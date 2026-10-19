<?php
// Every 15 min (indexer_predb_feed.sh): add a paid indexer's release names (via NZBHydra) to PreDB so obfuscated posts and
// re-uploads we index can be renamed. Pages newest-first and stops at the first page with nothing new.
use App\Facades\Search;
use App\Models\Predb;
use Illuminate\Support\Facades\DB;

$indexer = getenv('INDEXER') ?: 'Drunken Slug'; // the indexer's name in NZBHydra
$source = strtolower(preg_replace('/\W+/', '', $indexer));
$log = fopen('/config/indexer_predb_import.log', 'a');
$say = fn (string $m) => fwrite($log, '['.date('Y-m-d H:i:s')."] $m\n");
$key = getenv('HYDRA_KEY') ?: exit("HYDRA_KEY not set\n");
$maxPages = (int) (getenv('PAGES') ?: 10);
$catParam = getenv('CATS') ?: ''; // all categories; most indexers serve 100 items per API call
$seed = getenv('SEED') === '1'; // seed: keep paging past known titles
$cats = [0 => 'Other', 1 => 'Console', 2 => 'Movies', 3 => 'Audio', 4 => 'PC', 5 => 'TV', 6 => 'XXX', 7 => 'Books', 8 => 'Other'];
$groups = DB::table('usenet_groups')->pluck('id', 'name')->all();
$added = $seen = $pages = 0;

for ($page = 0; $page < $maxPages; $page++) {
    $base = getenv('API_BASE'); // set to the indexer's own API (e.g. https://api.example.com) to bypass NZBHydra's 1,500-result cap
    $url = $base
        ? rtrim($base, '/').'/api?t=search&extended=1&limit=100&offset='.($page * 100).($catParam !== '' ? '&cat='.$catParam : '').'&apikey='.$key
        : (getenv('HYDRA_URL') ?: 'http://172.17.0.1:5076').'/api?t=search&extended=1&limit=100&offset='.($page * 100).($catParam !== '' ? '&cat='.$catParam : '').'&indexers='.rawurlencode($indexer).'&apikey='.$key;
    for ($try = 0, $xml = false; $try < 3 && $xml === false; $try++) {
        if ($try > 0) sleep(10);
        $body = @file_get_contents($url, false, stream_context_create(['http' => ['timeout' => 120, 'follow_location' => 1]]));
        $xml = $body ? @simplexml_load_string($body) : false;
    }
    if ($xml === false) { $say("page $page: no response"); break; }
    $pages++;

    $new = 0;
    foreach ($xml->channel->item as $item) {
        $title = trim((string) $item->title);
        if ($title === '' || strlen($title) > 255) continue;
        $seen++;
        $a = [];
        foreach ($item->children('newznab', true)->attr as $at) $a[(string) $at->attributes()['name']] = (string) $at->attributes()['value'];
        $date = strtotime($a['usenetdate'] ?? (string) $item->pubDate) ?: time();
        $row = [
            'predate' => date('Y-m-d H:i:s', $date),
            'source' => $source,
            'category' => isset($a['category']) ? ($cats[intdiv((int) $a['category'], 1000)] ?? null) : null, // 10/20 = Other
            'size' => isset($a['size']) ? round($a['size'] / 1048576).'MB' : null,
            'files' => $a['files'] ?? null,
            'groups_id' => $groups[$a['group'] ?? ''] ?? 0,
        ];
        $existing = Predb::query()->where('title', $title)->first(['id', 'source', 'size']);
        if ($existing !== null) {
            // Fill in rows we added before attributes were parsed.
            if ($existing->source === $source && $existing->size === null) DB::table('predb')->where('id', $existing->id)->update($row);
            continue;
        }
        try {
            $id = DB::table('predb')->insertGetId($row + ['title' => $title, 'filename' => '']);
            Search::insertPredb(['id' => $id, 'title' => $title, 'filename' => null, 'source' => $source]);
            $new++;
        } catch (\Throwable $e) {
            $say("error $title: ".$e->getMessage());
        }
    }
    $added += $new;
    if (count($xml->channel->item) === 0 || (! $seed && $new === 0)) break;
    if ($seed) {
        if ($page % 50 === 0) $say("seed page $page seen=$seen added=$added");
        usleep(500000);
    }
}
$say("seen=$seen added=$added pages=$pages");
echo "seen=$seen added=$added\n";
