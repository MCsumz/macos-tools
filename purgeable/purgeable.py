#!/usr/bin/env python3
"""Show and free macOS "purgeable" disk space through the system's own CacheDelete service.

    purgeable.py                 what macOS could free right now, by kind
    purgeable.py purge           free it, after you confirm (--yes skips the question)
    purgeable.py ... --json      the same as JSON

Purgeable space is what Finder counts as available but the disk does not show as free: Time
Machine local snapshots, downloaded system and App Store assets, iCloud files that can be
downloaded again, and app and Spotlight caches. macOS frees it on its own when an app needs
the room, but not before a large copy or an installer checks the free space first.

This uses CacheDelete, a private macOS framework, through ctypes: no root, no installs, only
the Python that comes with macOS (3.9 or later). Private frameworks can change in any macOS
release; see the README for the versions it was tested on.
"""
import argparse
import ctypes
import json
import os
import platform
import sys
import time

VERSION = "1.0.0"
VOLUME = "/System/Volumes/Data"
CACHE_DELETE = "/System/Library/PrivateFrameworks/CacheDelete.framework/CacheDelete"
CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
# Services report their share of purgeable space; these groups name them for people.
GROUPS = (
    ("snapshots", "Time Machine local snapshots", ("com.apple.TMCacheDelete",)),
    ("assets", "Downloaded system, update and App Store assets",
     ("com.apple.mobileassetd.cache-delete", "com.apple.installd.CacheDelete",
      "com.apple.system_installd.CacheDelete", "com.apple.appstoreagent.CacheDelete",
      "com.apple.AssetCache.builtin.CacheDelete", "com.apple.triald.cache-delete",
      "com.apple.triald.system.cache-delete")),
    ("cloud_files", "iCloud and cloud files that can be downloaded again",
     ("com.apple.fspurgeable_document", "com.apple.FileProvider.cache-delete",
      "com.apple.cloudd.cache-delete", "com.apple.cloudd.system.cache-delete")),
    ("app_data", "Apps' purgeable data", ("com.apple.fspurgeable_data",)),
    ("spotlight", "Spotlight and search caches",
     ("com.apple.metadata.mds.cachedelete", "com.apple.corespotlightd.cachedelete",
      "com.apple.spotlightknowledged.updater.cachedelete")),
)
OTHER = ("caches", "Other system caches")
# Time Machine and other services finish their share shortly after the purge call returns.
SETTLE_CHECKS = 8
SETTLE_SECONDS = 2
UTF8 = 0x08000100
SINT64 = 11


class _BlockDescriptor(ctypes.Structure):
    _fields_ = [("reserved", ctypes.c_ulong), ("size", ctypes.c_ulong)]


class _Block(ctypes.Structure):
    _fields_ = [("isa", ctypes.c_void_p), ("flags", ctypes.c_int), ("reserved", ctypes.c_int),
                ("invoke", ctypes.c_void_p), ("descriptor", ctypes.POINTER(_BlockDescriptor))]


def cache_delete():
    cf = ctypes.CDLL(CORE_FOUNDATION)
    cd = ctypes.CDLL(CACHE_DELETE)
    pointer = ctypes.c_void_p
    for name, restype, argtypes in (
            ("CFStringCreateWithCString", pointer, [pointer, ctypes.c_char_p, ctypes.c_uint32]),
            ("CFStringGetCString", ctypes.c_bool, [pointer, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]),
            ("CFNumberCreate", pointer, [pointer, ctypes.c_long, pointer]),
            ("CFNumberGetValue", ctypes.c_bool, [pointer, ctypes.c_long, pointer]),
            ("CFNumberGetTypeID", ctypes.c_ulong, []),
            ("CFGetTypeID", ctypes.c_ulong, [pointer]),
            ("CFDictionaryCreate", pointer, [pointer, pointer, pointer, ctypes.c_long, pointer, pointer]),
            ("CFDictionaryGetCount", ctypes.c_long, [pointer]),
            ("CFDictionaryGetKeysAndValues", None, [pointer, pointer, pointer]),
            ("CFRelease", None, [pointer])):
        function = getattr(cf, name)
        function.restype, function.argtypes = restype, argtypes
    cd.CacheDeleteCopyItemizedPurgeableSpaceWithInfo.restype = pointer
    cd.CacheDeleteCopyItemizedPurgeableSpaceWithInfo.argtypes = [pointer]
    cd.CacheDeletePurgeSpaceWithInfoSync.restype = None
    cd.CacheDeletePurgeSpaceWithInfoSync.argtypes = [pointer, pointer]
    return cf, cd


def request(cf, amount=None):
    """A CacheDelete info dictionary for the data volume, up to urgency 4 (what Finder and installers use)."""
    keys, values = [], []
    for key, value in (("CACHE_DELETE_VOLUME", VOLUME), ("CACHE_DELETE_URGENCY_LIMIT", 4),
                       ("CACHE_DELETE_AMOUNT", amount)):
        if value is None:
            continue
        keys.append(cf.CFStringCreateWithCString(None, key.encode(), UTF8))
        if isinstance(value, str):
            values.append(cf.CFStringCreateWithCString(None, value.encode(), UTF8))
        else:
            number = ctypes.c_longlong(value)
            values.append(cf.CFNumberCreate(None, SINT64, ctypes.byref(number)))
    key_array = (ctypes.c_void_p * len(keys))(*keys)
    value_array = (ctypes.c_void_p * len(values))(*values)
    info = cf.CFDictionaryCreate(
        None, key_array, value_array, len(keys),
        ctypes.addressof(ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")),
        ctypes.addressof(ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryValueCallBacks")))
    for item in keys + values:
        cf.CFRelease(item)
    if not info:
        raise RuntimeError("CacheDelete request could not be built")
    return info


def numbers(cf, dictionary):
    """The integer entries of a CacheDelete result dictionary."""
    count = cf.CFDictionaryGetCount(dictionary)
    keys, values = (ctypes.c_void_p * count)(), (ctypes.c_void_p * count)()
    cf.CFDictionaryGetKeysAndValues(dictionary, keys, values)
    found = {}
    for key, value in zip(keys, values):
        name = ctypes.create_string_buffer(256)
        number = ctypes.c_longlong()
        if (cf.CFGetTypeID(value) == cf.CFNumberGetTypeID() and
                cf.CFStringGetCString(key, name, 256, UTF8) and
                cf.CFNumberGetValue(value, SINT64, ctypes.byref(number))):
            found[name.value.decode()] = number.value
    return found


def group(services):
    """Sort CacheDelete's per-service bytes into the named groups; unknown services count as caches."""
    services = {name: value for name, value in services.items()
                if not name.startswith("CACHE_DELETE_") and value > 0}
    groups = {}
    for key, _, names in GROUPS:
        groups[key] = sum(services.pop(name, 0) for name in names)
    groups[OTHER[0]] = sum(services.values())
    return groups


def purgeable_space():
    """(total bytes macOS can free, bytes per group). Services share space, so trust the total, not the sum."""
    cf, cd = cache_delete()
    info = request(cf)
    try:
        result = cd.CacheDeleteCopyItemizedPurgeableSpaceWithInfo(info)
    finally:
        cf.CFRelease(info)
    if not result:
        raise RuntimeError("CacheDelete returned no purgeable space")
    try:
        found = numbers(cf, result)
    finally:
        cf.CFRelease(result)
    total = found.get("CACHE_DELETE_TOTAL_AVAILABLE")
    if type(total) is not int or total < 0:
        raise RuntimeError("CacheDelete total missing")
    return total, group(found)


def purge_cache_delete(amount):
    cf, cd = cache_delete()
    finished = []
    invoke = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)(lambda block, result: finished.append(True))
    descriptor = _BlockDescriptor(0, ctypes.sizeof(_Block))
    libsystem = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    # A global block is never copied to the heap, so this ctypes structure stays authoritative.
    block = _Block(ctypes.addressof(ctypes.c_void_p.in_dll(libsystem, "_NSConcreteGlobalBlock")),
                   1 << 28, 0, ctypes.cast(invoke, ctypes.c_void_p), ctypes.pointer(descriptor))
    info = request(cf, amount)
    try:
        cd.CacheDeletePurgeSpaceWithInfoSync(info, ctypes.addressof(block))
    finally:
        cf.CFRelease(info)
    if not finished:
        raise RuntimeError("CacheDelete purge did not finish")


def free_bytes():
    stat = os.statvfs(VOLUME)
    return stat.f_bavail * stat.f_frsize


def scan():
    total, groups = purgeable_space()
    return {"state": "scanned", "purgeable": total, "groups": groups, "free": free_bytes(), "freed": 0}


def purge():
    before = free_bytes()
    total, _ = purgeable_space()
    if total:
        # Ask for everything plus headroom; CacheDelete frees whole service allotments.
        purge_cache_delete(total + (1 << 30))
    remaining, groups = purgeable_space()
    for _ in range(SETTLE_CHECKS):
        time.sleep(SETTLE_SECONDS)
        previous = remaining
        remaining, groups = purgeable_space()
        if remaining == previous:
            break
    after = free_bytes()
    freed = max(0, after - before)
    return {"state": "purged" if freed else "no_change", "purgeable": remaining, "groups": groups,
            "free": after, "freed": freed}


def size(value):
    """Decimal units, as Finder shows them."""
    for unit, factor in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6)):
        if value >= factor:
            return "%.1f %s" % (value / factor, unit)
    return "%d KB" % round(value / 1e3)


def report(result):
    labels = dict((key, label) for key, label, _ in GROUPS)
    labels[OTHER[0]] = OTHER[1]
    lines = []
    if result["state"] != "scanned":
        lines.append("Freed %s." % size(result["freed"]) if result["freed"] else "Nothing was freed.")
    lines.append("Free now: %s. %s: %s." % (size(result["free"]), "Purgeable" if result["state"] == "scanned"
                                             else "Still purgeable", size(result["purgeable"])))
    shown = [(labels[key], value) for key, value in result["groups"].items() if value]
    if shown:
        lines.append("")
        width = max(len(label) for label, _ in shown)
        lines += ["  %-*s  %9s" % (width, label, size(value)) for label, value in shown]
        lines.append("  (the services share space, so these can add up to more than the total)")
    return "\n".join(lines)


CONFIRM = """This asks macOS to free {amount} now:
  - Time Machine local snapshots are deleted (backups on your backup disk stay).
  - iCloud and cloud files kept on this Mac are removed locally; they stay in the cloud
    and download again when you open them.
  - Downloaded update assets and caches are deleted and fetched again when needed.
Free it? [y/N] """


def main(argv=None):
    parser = argparse.ArgumentParser(prog="purgeable.py", description="Show and free macOS purgeable disk space.")
    parser.add_argument("action", nargs="?", choices=("scan", "purge"), default="scan")
    parser.add_argument("--yes", action="store_true", help="purge without asking")
    parser.add_argument("--json", action="store_true", help="print JSON")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    args = parser.parse_args(argv)
    if platform.system() != "Darwin":
        print("purgeable.py runs on macOS only.", file=sys.stderr)
        return 2
    try:
        if args.action == "scan":
            result = scan()
        else:
            if not args.yes:
                if args.json or not sys.stdin.isatty():
                    print("purge needs --yes when it cannot ask.", file=sys.stderr)
                    return 2
                total, _ = purgeable_space()
                if not total:
                    print("Nothing is purgeable right now.")
                    return 0
                try:
                    answer = input(CONFIRM.format(amount=size(total)))
                except (EOFError, KeyboardInterrupt):
                    # Ctrl-D, Ctrl-C or a closed input is a no.
                    answer = ""
                    print()
                if answer.strip().lower() not in ("y", "yes"):
                    print("Nothing was changed.")
                    return 1
            result = purge()
    except (OSError, RuntimeError, AttributeError) as error:
        # AttributeError: a macOS release changed or removed the private CacheDelete functions.
        print("CacheDelete failed: %s: %s" % (type(error).__name__, error), file=sys.stderr)
        return 1
    print(json.dumps(result) if args.json else report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
