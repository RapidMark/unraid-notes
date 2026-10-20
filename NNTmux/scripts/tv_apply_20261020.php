<?php
// One-off (2026-10-20): name unnamed TV-length releases from DrunkenSlug PreDB names matched by post time (±2 min)
// and size (±1%), unambiguous pairs only. Uses NNTmux's own rename (recategorises and updates the search index).
use App\Models\Release;
use App\Services\NameFixing\ReleaseUpdateService;
$svc = new ReleaseUpdateService;
$done = $skipped = 0;
foreach (file('/config/tv_apply_20261020.tsv', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
    [$rid, $pid, $title] = explode("\t", $line);
    $r = Release::query()->find((int) $rid, ['id', 'searchname', 'groups_id', 'fromname', 'categories_id', 'predb_id']);
    if (! $r || (int) $r->predb_id > 0) { $skipped++; continue; }
    $svc->updateRelease($r, $title, 'DrunkenSlug post time + size', true, 'PreDB FT Exact, ', true, false, (int) $pid);
    $done++;
}
echo "renamed=$done skipped=$skipped\n";
