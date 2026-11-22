# macos-tools

Small macOS fixes and helpers from my homelab, where a Mac mini M4 works as an always-on AI
server. Each one solved a real problem on that Mac. Each is self-contained, has its own README
and has its own release.

| Tool | What it does | Release |
| --- | --- | --- |
| [purgeable](purgeable/) | Shows the disk space macOS could free (Time Machine local snapshots, update assets, re-downloadable iCloud files, caches), and frees it through macOS's own CacheDelete service. One Python file, no installs. | [purgeable-v1.0.0](https://github.com/MCsumz/macos-tools/releases/tag/purgeable-v1.0.0) |
| [edge-dns-profile](edge-dns-profile/) | A configuration profile that fixes Microsoft Edge showing "DNS not resolved" after the Mac sleeps, by handing DNS back to macOS. | [edge-dns-profile-v1.0.0](https://github.com/MCsumz/macos-tools/releases/tag/edge-dns-profile-v1.0.0) |

**Releases:** each tool's tags start with its folder name, for example `purgeable-v1.0.0`. The
release notes hold the SHA-256 of every download, and `SHA256SUMS` covers every file in the repo.

More of my homelab tools, each in its own repo, are listed on [my profile](https://github.com/MCsumz).

## License

[MIT](LICENSE)
