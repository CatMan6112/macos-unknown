"""
what steam thinks the newest build of a depot is. reads appcache/appinfo.vdf so no network
CUPort.dll has the same parser so change both
"""

import pathlib
import struct

APPINFO = pathlib.Path.home() / "Library/Application Support/Steam/appcache/appinfo.vdf"

V28, V29 = 0x07564428, 0x07564429
# after appid and size comes state/updated/token/sha1/change/sha1
ENTRY_HEAD = 4 + 4 + 8 + 20 + 4 + 20


class _KV:
    def __init__(self, data, pos, keys):
        self.d, self.p, self.keys = data, pos, keys

    def cstr(self):
        end = self.d.index(b"\0", self.p)
        s = self.d[self.p:end].decode("utf-8", "replace")
        self.p = end + 1
        return s

    def key(self):
        if self.keys is None:
            return self.cstr()
        (i,) = struct.unpack_from("<I", self.d, self.p)
        self.p += 4
        return self.keys[i]

    def section(self):
        out = {}
        while True:
            t = self.d[self.p]
            self.p += 1
            if t == 8:
                return out
            k = self.key()
            if t == 0:
                out[k] = self.section()
            elif t == 1:
                out[k] = self.cstr()
            elif t in (2, 4, 6):  # int32/float/pointer
                out[k] = struct.unpack_from("<i", self.d, self.p)[0]
                self.p += 4
            elif t in (7, 10):  # uint64/int64
                out[k] = struct.unpack_from("<Q", self.d, self.p)[0]
                self.p += 8
            else:
                raise ValueError(f"appinfo: unknown kv type {t}")


_cache = {}


def app_info(appid, path=APPINFO):
    """parsed product info for one app or None if steam has none cached"""
    path = pathlib.Path(path)
    # the launcher asks every tick so only reparse when steam rewrites the file
    stamp = (str(path), appid, path.stat().st_mtime_ns)
    if stamp not in _cache:
        _cache.clear()
        _cache[stamp] = _parse(path.read_bytes(), appid)
    return _cache[stamp]


def _parse(d, appid):
    magic, _universe = struct.unpack_from("<II", d, 0)
    if magic == V29:
        (table,) = struct.unpack_from("<q", d, 8)
        (count,) = struct.unpack_from("<I", d, table)
        keys = d[table + 4:].split(b"\0", count)[:count]
        keys = [k.decode("utf-8", "replace") for k in keys]
        p = 16
    elif magic == V28:
        keys, p = None, 8
    else:
        raise ValueError(f"appinfo: unknown version {magic:#x}")
    while p + 8 <= len(d):
        aid, size = struct.unpack_from("<II", d, p)
        if aid == 0:
            return None
        if aid == appid:
            info = _KV(d, p + 8 + ENTRY_HEAD, keys).section()
            return info.get("appinfo", info)
        p += 8 + size
    return None


def public_manifest(appid, depot, branch="public", path=APPINFO):
    """manifest gid steam lists for this depot on the branch as a string"""
    try:
        info = app_info(appid, path)
    except (OSError, ValueError, IndexError, struct.error):
        return None
    try:
        m = info["depots"][str(depot)]["manifests"][branch]
    except (TypeError, KeyError):
        return None
    # newer appinfo nests gid/size/download and older ones only have the gid
    gid = m.get("gid") if isinstance(m, dict) else m
    return str(gid) if gid else None


if __name__ == "__main__":
    import sys
    print(public_manifest(int(sys.argv[1]), int(sys.argv[2])))
