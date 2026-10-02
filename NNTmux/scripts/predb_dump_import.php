<?php
// Import nZEDb daily PreDB dumps (2014-2024) into NNTmux `predb`.
// Run inside the container: php artisan tinker --execute="require '/config/predb-import/predb_dump_import.php';"
// Format per line: 12 fields separated by "\t\t", values in single quotes, \N = NULL, CRLF endings.
// Field order: title, nfo, size, files, filename, nuked, nukereason, category, predate, source, requestid, groupname

use Illuminate\Support\Facades\DB;

$dir = '/config/predb-import/gz';
$files = glob($dir.'/*_predb_dump.csv.gz');
sort($files);

$clean = static function (string $v): ?string {
    $v = trim($v);
    if ($v === '\N' || $v === '') {
        return null;
    }
    if (strlen($v) >= 2 && $v[0] === "'" && substr($v, -1) === "'") {
        $v = substr($v, 1, -1);
    }

    return stripcslashes($v);
};

$batch = [];
$inserted = 0;
$lines = 0;
$bad = 0;
$flush = static function () use (&$batch, &$inserted): void {
    if ($batch) {
        $inserted += DB::table('predb')->insertOrIgnore($batch);
        $batch = [];
    }
};

foreach ($files as $i => $file) {
    $fh = gzopen($file, 'rb');
    while (($line = gzgets($fh)) !== false) {
        $line = rtrim($line, "\r\n");
        if ($line === '') {
            continue;
        }
        $lines++;
        $f = explode("\t\t", $line);
        if (count($f) < 12) {
            $bad++;
            continue;
        }
        $title = $clean($f[0]);
        if ($title === null) {
            $bad++;
            continue;
        }
        $predate = $clean($f[8]);
        $batch[] = [
            'title' => mb_substr($title, 0, 255),
            'nfo' => ($n = $clean($f[1])) === null ? null : mb_substr($n, 0, 255),
            'size' => ($s = $clean($f[2])) === null ? null : mb_substr($s, 0, 50),
            'files' => ($x = $clean($f[3])) === null ? null : mb_substr($x, 0, 50),
            'filename' => mb_substr((string) $clean($f[4]), 0, 255),
            'nuked' => (int) $clean($f[5]),
            'nukereason' => ($r = $clean($f[6])) === null ? null : mb_substr($r, 0, 255),
            'category' => ($c = $clean($f[7])) === null ? null : mb_substr($c, 0, 255),
            'predate' => ($predate && strtotime($predate)) ? $predate : null,
            'source' => mb_substr((string) $clean($f[9]), 0, 50),
            'requestid' => max(0, (int) $clean($f[10])),
            'groups_id' => 0,
        ];
        if (count($batch) >= 2000) {
            $flush();
        }
    }
    gzclose($fh);
    if (($i + 1) % 200 === 0) {
        $flush();
        echo sprintf("[%s] files %d/%d, lines %d, inserted %d, skipped %d\n", date('H:i:s'), $i + 1, count($files), $lines, $inserted, $bad);
    }
}
$flush();
echo sprintf("DONE files %d, lines %d, inserted %d (duplicates ignored), skipped %d\n", count($files), $lines, $inserted, $bad);
