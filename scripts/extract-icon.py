"""pulls the main icon out of a windows exe as .ico plus the biggest one as .png"""
import sys, struct, io, pefile
from PIL import Image
exe, out = sys.argv[1], sys.argv[2]
pe = pefile.PE(exe)
res = {e.id: e for e in pe.DIRECTORY_ENTRY_RESOURCE.entries}
def data(entry):
    d = entry.directory.entries[0].data.struct
    return pe.get_data(d.OffsetToData, d.Size)
icons = {e.id: data(e) for e in res[pefile.RESOURCE_TYPE["RT_ICON"]].directory.entries}
grp = data(res[pefile.RESOURCE_TYPE["RT_GROUP_ICON"]].directory.entries[0])
_, _, n = struct.unpack("<HHH", grp[:6])
ents = [struct.unpack("<BBBBHHIH", grp[6 + 14*i: 20 + 14*i]) for i in range(n)]
hdr = struct.pack("<HHH", 0, 1, n); body = b""; off = 6 + 16*n
for w, h, c, r, p, b, size, iid in ents:
    img = icons[iid]
    hdr += struct.pack("<BBBBHHII", w, h, c, r, p, b, len(img), off + len(body)); body += img
open(out + ".ico", "wb").write(hdr + body)
im = Image.open(out + ".ico"); im.size = max(im.ico.sizes()); im.load()
im.save(out + ".png"); print(out + ".ico", out + ".png", im.size, sorted(im.ico.sizes()))
