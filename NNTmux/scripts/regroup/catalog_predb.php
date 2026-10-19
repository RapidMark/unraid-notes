<?php
// Called by catalog.py: add names read from uploads' PAR2 indexes to PreDB (source usenet-par2).
use App\Facades\Search;
use App\Models\Predb;
use Illuminate\Support\Facades\DB;

$groups = DB::table('usenet_groups')->pluck('id', 'name')->all();
$added = 0;
foreach (file('/config/regroup/catalog_predb.tsv', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
    [$title, $predate, $size, $files, $group] = array_pad(explode("\t", $line), 5, '');
    if ($title === '' || strlen($title) > 255 || Predb::query()->where('title', $title)->exists()) {
        continue;
    }
    $id = DB::table('predb')->insertGetId([
        'title' => $title, 'predate' => $predate, 'source' => 'usenet-par2', 'size' => $size, 'files' => $files,
        'groups_id' => $groups[$group] ?? 0, 'filename' => '',
    ]);
    Search::insertPredb(['id' => $id, 'title' => $title, 'filename' => null, 'source' => 'usenet-par2']);
    $added++;
}
echo "added=$added\n";
