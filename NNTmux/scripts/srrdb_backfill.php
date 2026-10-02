<?php
// Backfill NNTmux `predb` from srrDB, newest day first, back to 2024-05-02 (where the nZEDb dumps end).
// Run: php artisan tinker --execute="require '/config/predb-import/srrdb_backfill.php';"
// Resumable: finished days are appended to srrdb_done_days.txt. Log: srrdb_backfill.log

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;

$base = '/config/predb-import';
$doneFile = $base.'/srrdb_done_days.txt';
$logFile = $base.'/srrdb_backfill.log';
$stopDay = '2024-05-02';
$delay = 2;          // seconds between requests (polite pace for a volunteer site)
$perPage = 45;

$done = is_file($doneFile) ? array_flip(array_filter(array_map('trim', file($doneFile)))) : [];
$log = static function (string $m) use ($logFile): void {
    file_put_contents($logFile, '['.date('Y-m-d H:i:s').'] '.$m."\n", FILE_APPEND);
};

$fetch = static function (string $url) use ($log, $delay): ?array {
    $wait = $delay;
    for ($try = 1; $try <= 8; $try++) {
        sleep($wait);
        try {
            $r = Http::withHeaders(['User-Agent' => 'NNTmux-predb-backfill (home indexer; 1 req/2s)'])->timeout(60)->get($url);
            if ($r->successful() && is_array($r->json())) {
                return $r->json();
            }
            $log("HTTP {$r->status()} on $url (try $try)");
        } catch (Throwable $e) {
            $log('error on '.$url.': '.$e->getMessage()." (try $try)");
        }
        $wait = min(300, $wait * 2);   // back off on errors / rate limits
    }

    return null;
};

$day = new DateTime('today');
$stop = new DateTime($stopDay);
$log("start: backwards from {$day->format('Y-m-d')} to $stopDay");

while ($day >= $stop) {
    $d = $day->format('Y-m-d');
    if (isset($done[$d])) {
        $day->modify('-1 day');
        continue;
    }
    $skip = 0;
    $dayInserted = 0;
    $dayTotal = null;
    $ok = true;
    do {
        $url = "https://api.srrdb.com/v1/search/date:$d".($skip ? "/skip:$skip" : '');
        $j = $fetch($url);
        if ($j === null) {
            $ok = false;
            $log("giving up on $d at skip $skip for now");
            break;
        }
        $dayTotal = (int) ($j['resultsCount'] ?? 0);
        $rows = [];
        foreach ($j['results'] ?? [] as $r) {
            if (empty($r['release'])) {
                continue;
            }
            $rows[] = [
                'title' => mb_substr($r['release'], 0, 255),
                'predate' => $r['date'] ?? null,
                'source' => 'srrdb',
                'filename' => '',
                'requestid' => 0,
                'groups_id' => 0,
                'nuked' => 0,
            ];
        }
        if ($rows) {
            $dayInserted += DB::table('predb')->insertOrIgnore($rows);
        }
        $skip += $perPage;
    } while ($skip < $dayTotal && count($j['results'] ?? []) > 0);

    if ($ok) {
        file_put_contents($doneFile, $d."\n", FILE_APPEND);
        $log("day $d: srrdb total $dayTotal, new $dayInserted");
    }
    $day->modify('-1 day');
}
$log('finished');
