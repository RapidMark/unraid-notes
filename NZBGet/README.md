# NZBGet

## Extensions

Two small extensions in [`scripts/`](scripts/). Copy each folder into NZBGet's `ScriptDir` and enable it under Settings → Extension Scripts.

- **QueueSort**: re-sorts the queue every time an NZB is added, with NZBGet's own sort. The default `age+` puts the newest posts first, so a new episode doesn't wait behind a batch of old remuxes. Priorities still come first.
- **DeobfuscateArchives**: post-processing. Extracts 7z/RAR/ZIP archives that were posted without a file extension, which NZBGet otherwise leaves packed.
