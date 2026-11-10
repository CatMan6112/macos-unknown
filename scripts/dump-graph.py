"""dumps each named shader graph's decompressed D3D11 blob to <outdir>/<name>.bin
plus <name>.txt with pass/keyword info. usage: dump-graph.py <Data> <outdir> name..."""
import sys, pathlib, UnityPy, lz4.block
data, out = sys.argv[1], pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
want = set(sys.argv[3:])
env = UnityPy.load(data)
for obj in env.objects:
    if obj.type.name != "Shader": continue
    tt = obj.read_typetree(); n = tt["m_ParsedForm"]["m_Name"]
    if not n.startswith("Shader Graphs/") or (want and n[14:] not in want): continue
    n = n[14:]
    blob = bytes(tt["compressedBlob"])
    pi = tt["platforms"].index(4) if 4 in tt["platforms"] else 0
    offs, clen, dlen = tt["offsets"][pi], tt["compressedLengths"][pi], tt["decompressedLengths"][pi]
    chunks = []
    for o, c, d in zip(offs, clen, dlen):
        chunks.append(lz4.block.decompress(blob[o:o + c], uncompressed_size=d))
    (out / f"{n}.bin").write_bytes(b"".join(chunks))
    pf = tt["m_ParsedForm"]
    lines = [f"platforms {tt['platforms']}"]
    for si, sub in enumerate(pf["m_SubShaders"]):
        for p in sub["m_Passes"]:
            tags = {k: v for k, v in p["m_Tags"]["tags"]}
            lines.append(f"pass {p['m_Name']!r} {tags}")
    for p in pf["m_PropInfo"]["m_Props"]:
        lines.append(f"prop {p['m_Name']} type{p['m_Type']} def {p['m_DefValue[0]']} {p['m_DefValue[1]']} {p['m_DefValue[2]']} {p['m_DefValue[3]']}")
    (out / f"{n}.txt").write_text("\n".join(lines) + "\n")
    print(n, sum(dlen))
