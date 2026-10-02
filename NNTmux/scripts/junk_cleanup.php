<?php
// Delete tiny single-file releases (obfuscated-post fragments) in Hashed/Misc
// using NNTmux's own batch delete (NZB file, images and search index too).
use Illuminate\Support\Facades\DB;

$mgmt = app(App\Services\Releases\ReleaseManagementService::class);
$nzb = app(App\Services\Nzb\NzbService::class);
$img = app(App\Services\ReleaseImageService::class);
$minSize = 52428800;
$lastId = 0;
$total = 0;
do {
    $batch = DB::select(
        'SELECT id, guid FROM releases WHERE totalpart = 1 AND size < ? AND categories_id IN (10, 20) AND id > ? ORDER BY id LIMIT 1000',
        [$minSize, $lastId]
    );
    if ($batch === []) {
        break;
    }
    $lastId = (int) end($batch)->id;
    $mgmt->deleteBatch($batch, $nzb, $img);
    $total += count($batch);
    if ($total % 20000 === 0) {
        file_put_contents('/config/junk_cleanup.log', date('H:i:s')." deleted $total\n", FILE_APPEND);
    }
} while (true);
file_put_contents('/config/junk_cleanup.log', date('H:i:s')." DONE deleted $total\n", FILE_APPEND);
