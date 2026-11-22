# Edge on macOS: "DNS not resolved" after sleep

A configuration profile for Microsoft Edge on macOS. It turns off Edge's built-in DNS client, so
Edge asks macOS for names the way Safari does. An optional second version also clears Edge's
disk cache whenever Edge closes.

## The problem

After my Mac had slept for a while, Edge showed **"DNS not resolved"** for every site, instantly.
Everything else on the Mac worked: Safari, Terminal, Excel, the system services. Only turning
Ethernet off and on fixed Edge.

**Why only Edge:** like Chrome, Edge has its own DNS client. It reads the network's DNS setup
itself instead of asking macOS. A Mac that "sleeps" in the background briefly drops and restores
its network link each time it wakes. Mine does that about 1,500 times a day, because it sleeps
after one idle minute and network traffic wakes it again. Edge's client can catch a link drop
and keep a broken DNS setup until the next real network change. macOS's own resolver
(mDNSResponder) kept working throughout: 217 of 218 questions answered in the same minutes.

**The fix:** Edge's policy `BuiltInDnsClientEnabled = false`. Edge then resolves through macOS.

A related symptom showed up later: **pages without styling** (plain blue links, a "Skip to" list).
Edge was serving a stylesheet from its disk cache that had been cut off by one of those link
drops, while another browser loaded the same page fine. A hard reload (⌘⇧R) fixed the page. The
policy `ClearCachedImagesAndFilesOnExit = true` makes sure a broken copy can't outlive an Edge
restart.

## Which profile

| File | Sets | Use it when |
| --- | --- | --- |
| [`edge-system-dns.mobileconfig`](edge-system-dns.mobileconfig) | `BuiltInDnsClientEnabled = false` | You only have the DNS problem |
| [`edge-system-dns-fresh-cache.mobileconfig`](edge-system-dns-fresh-cache.mobileconfig) | the above + `ClearCachedImagesAndFilesOnExit = true` | You also see unstyled pages. History, cookies and sign-ins stay; only cached images and files go. The first page loads after a restart are a little slower. |

Both use the same identifier, so installing one replaces the other.

**Why a profile:** Edge only honours these as mandatory policies. `defaults write` is ignored.

## Install

1. Download one of the two from the [release](https://github.com/MCsumz/macos-tools/releases/tag/edge-dns-profile-v1.0.0)
   ([DNS fix](https://github.com/MCsumz/macos-tools/releases/download/edge-dns-profile-v1.0.0/edge-system-dns.mobileconfig) ·
   [DNS fix + fresh cache](https://github.com/MCsumz/macos-tools/releases/download/edge-dns-profile-v1.0.0/edge-system-dns-fresh-cache.mobileconfig))
   and double-click it.
2. Open **System Settings → General → Device Management** (on older macOS, Privacy & Security →
   Profiles) and install it. macOS calls it "unverified" because it isn't signed. It's a short
   plain-text XML file, so read it first.
3. Quit Edge (⌘Q) and start it again.
4. Open `edge://policy`. It should list `BuiltInDnsClientEnabled` as `false`, and with the second
   profile `ClearCachedImagesAndFilesOnExit` as `true`.

From Terminal:

```sh
defaults read "/Library/Managed Preferences/$USER/com.microsoft.Edge"
```

**Remove it:** delete the profile in the same place, then restart Edge.

## If it happens again

**Right after waking the Mac:** a "not resolved" in the first few seconds can be the Ethernet link
reconnecting (about 7 s on a Mac mini). Reload once it's back; nothing is stuck.

Otherwise, try Safari, or `ping example.org` in Terminal.

- **They work:** it's Edge only. `edge://net-internals/#dns` → **Clear host cache** is quicker than
  toggling the network.
- **They fail too:** the Mac's resolver or the network is stuck, and this profile isn't the cause.

## Tested

- In use on a Mac mini M4 since 13 Nov 2026: the DNS fix alone first, and since 14 Nov the
  fresh-cache version.
- Currently running macOS 27.2.1 with Edge 158.
- "DNS not resolved" hasn't come back since.

Not affiliated with Microsoft. The settings are Edge's documented policies
([BuiltInDnsClientEnabled](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/BuiltInDnsClientEnabled),
[ClearCachedImagesAndFilesOnExit](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/ClearCachedImagesAndFilesOnExit)).

## License

[MIT](../LICENSE). Part of [macos-tools](../README.md); this profile was first published on its own as
`edge-macos-dns-profile` on 20 Nov 2026.
