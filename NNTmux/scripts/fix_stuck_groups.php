<?php
// Reset active groups whose position went bad (last_record below first_record),
// so they restart at current posts. Backfill goes back to 60 days.
use App\Models\UsenetGroup;

foreach (UsenetGroup::query()->where('active', 1)->get() as $g) {
    if ((int) $g->last_record === 0 || (int) $g->last_record >= (int) $g->first_record) {
        continue;
    }
    UsenetGroup::reset($g->id);
    UsenetGroup::query()->where('id', $g->id)->update(['active' => 1, 'backfill' => 1, 'backfill_target' => 60]);
    echo "reset {$g->name}", PHP_EOL;
}
echo 'done', PHP_EOL;
