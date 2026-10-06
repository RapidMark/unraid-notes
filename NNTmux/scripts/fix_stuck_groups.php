<?php
// Restart stuck groups at current posts. Stuck = position below its own first
// article, or newest fetched post older than 7 days. The start is taken straight
// from the server (newest minus 100k); a normal group reset can land years back.
use App\Models\UsenetGroup;

$n = app(App\Services\NNTP\NNTPService::class);
$n->doConnect();
foreach (UsenetGroup::query()->where('active', 1)->get() as $g) {
    $old = $g->last_record_postdate !== null && $g->last_record_postdate < now()->subDays(7);
    $bad = (int) $g->last_record > 0 && (int) $g->last_record < (int) $g->first_record;
    if (! $old && ! $bad) {
        continue;
    }
    $s = $n->selectGroup($g->name);
    if (! is_array($s)) {
        echo "skip {$g->name} (server error)", PHP_EOL;
        continue;
    }
    $start = max((int) $s['first'], (int) $s['last'] - 100000);
    UsenetGroup::query()->where('id', $g->id)->update([
        'first_record' => $start, 'last_record' => $start,
        'first_record_postdate' => now(), 'last_record_postdate' => now(),
        'backfill' => 1, 'backfill_target' => 60,
    ]);
    echo "restarted {$g->name} at ", number_format($start), PHP_EOL;
}
$n->doQuit();
echo 'done', PHP_EOL;
