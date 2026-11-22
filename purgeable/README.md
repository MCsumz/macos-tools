# purgeable: show and free macOS purgeable space

A single Python file that asks macOS's own CacheDelete service what it could free on the disk
right now, and frees it on request. It needs no installs and no root, only the Python that comes
with macOS.

```text
$ python3 purgeable.py
Free now: 269.3 GB. Purgeable: 1.9 GB.

  Downloaded system, update and App Store assets     5.7 MB
  Apps' purgeable data                               1.8 GB
  Spotlight and search caches                       39.0 MB
  Other system caches                               31.9 MB
  (the services share space, so these can add up to more than the total)

$ python3 purgeable.py purge
This asks macOS to free 1.9 GB now:
  ...
Free it? [y/N] y
Freed 3.6 GB.
Free now: 272.9 GB. Still purgeable: 88.1 MB.
```

## Why

Finder's "available" counts **purgeable** space: Time Machine local snapshots, downloaded update
assets, iCloud files that can be downloaded again, and app and Spotlight caches. macOS frees that
space when an app asks for it, but `df`, installers and tools that check the free space first
only see the real free space. My Mac mini is an AI server, and model downloads and large copies
kept failing although Finder showed plenty of room.

This is the purge behind the storage card of my Wake AI dashboard. There it runs over SSH, and it
has been in use since October 2026. It uses the same calls macOS makes when the disk runs low:
`CacheDeleteCopyItemizedPurgeableSpaceWithInfo` to read and `CacheDeletePurgeSpaceWithInfoSync`
to free, both at urgency 4.

## Use

Download [`purgeable.py`](https://github.com/MCsumz/macos-tools/releases/download/purgeable-v1.0.0/purgeable.py)
from the [release](https://github.com/MCsumz/macos-tools/releases/tag/purgeable-v1.0.0), then:

| Command | Does |
| --- | --- |
| `python3 purgeable.py` | Shows free and purgeable space, by kind. Changes nothing. |
| `python3 purgeable.py purge` | Shows what it would free and asks first. Answering anything but `y` changes nothing. |
| `python3 purgeable.py purge --yes` | Frees without asking, for scripts. Without a terminal, `purge` refuses unless you add `--yes`. |
| `--json` | Prints the result as JSON, for scripts and dashboards. |

## What a purge removes

| Kind | What happens |
| --- | --- |
| Time Machine local snapshots | Deleted from this Mac. Backups on your backup disk stay. |
| iCloud and cloud files | Removed locally. They stay in the cloud and download again when you open them. |
| Downloaded system, update and App Store assets | Deleted, and fetched again when needed. |
| Apps' purgeable data, Spotlight and other caches | Rebuilt by macOS and the apps when needed. |

It never touches your own files. It only asks macOS to free what macOS itself marked as safe to
remove. The kinds share space, so freeing one can shrink another; the total is what counts.

## Notes

- **Private API:** CacheDelete is a private framework, called through `ctypes`, so a macOS update
  could change it. If that happens, the script reports "CacheDelete failed" instead of guessing.
- **The numbers move:** macOS frees some space with a delay. After the call returns, the script
  waits until the purgeable total settles, up to 16 seconds. "Freed" is the real change in free
  disk space, so other activity during the purge shows up in it too.

## Tested

- **Mac:** Mac mini M4, macOS 27.2.1, with the system's `/usr/bin/python3` (3.9.6).
- **Unit tests:** `python3 -m unittest -v test_purgeable` runs 15 tests. One of them reads the
  real numbers on a Mac and never purges.
- **Real purge, with this file:** it freed 3.6 GB in 9 seconds. The question in a terminal was
  answered with `n`, then with `y`; Ctrl-D counts as no.

## License

[MIT](../LICENSE). Part of [macos-tools](../README.md).
