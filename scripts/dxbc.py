"""bare bones DXBC (SM4/5) disassembler. it has RDEF names and SHEX instructions"""
import struct, sys

OPS = """add and break breakc call callc case continue continuec cut default deriv_rtx deriv_rty discard div dp2 dp3 dp4
else emit emitthencut endif endloop endswitch eq exp frc ftoi ftou ge iadd if ieq ige ilt imad imax imin imul ine ineg ishl ishr itof
label ld ld_ms log loop lt mad min max customdata mov movc mul ne nop not or resinfo ret retc round_ne round_ni round_pi round_z rsq
sample sample_c sample_c_lz sample_l sample_d sample_b sqrt switch sincos udiv ult uge umul umad umax umin ushr utof xor
dcl_resource dcl_constantbuffer dcl_sampler dcl_index_range dcl_gs_output_topology dcl_gs_input_primitive dcl_max_output_vertex_count
dcl_input dcl_input_sgv dcl_input_siv dcl_input_ps dcl_input_ps_sgv dcl_input_ps_siv dcl_output dcl_output_sgv dcl_output_siv
dcl_temps dcl_indexable_temp dcl_global_flags reserved lod gather4 sample_pos sample_info reserved hs_decls hs_cp hs_fork hs_join
emit_stream cut_stream emitthencut_stream interface_call bufinfo deriv_rtx_coarse deriv_rtx_fine deriv_rty_coarse deriv_rty_fine
gather4_c gather4_po gather4_po_c rcp f32tof16 f16tof32 uaddc usubb countbits firstbit_hi firstbit_lo firstbit_shi ubfe ibfe bfi bfrev swapc""".split()
TYPES = {0: "r", 1: "v", 2: "o", 3: "x", 6: "s", 7: "t", 8: "cb", 9: "icb", 13: "null", 1+11: "oDepth"}
C = "xyzw"


def cstr(b, o):
    return b[o:b.index(b"\0", o)].decode()


def rdef(b):
    cbn, cbo, bn, bo = struct.unpack_from("<4I", b, 0)
    out = {"bind": [], "cb": {}}
    for i in range(bn):
        n, t, rt, dim, ns, bp, bc, fl = struct.unpack_from("<8I", b, bo + 32 * i)
        out["bind"].append((cstr(b, n), t, bp))
    for i in range(cbn):
        n, vc, vo, size, fl, t = struct.unpack_from("<6I", b, cbo + 24 * i)
        vs = []
        for j in range(vc):
            vn, so, sz = struct.unpack_from("<3I", b, vo + 40 * j)
            vs.append((so, sz, cstr(b, vn)))
        out["cb"][cstr(b, n)] = vs
    return out


def operand(t, i):
    tok = t[i]; i += 1
    ncomp = tok & 3; sel = (tok >> 2) & 3; cdata = (tok >> 4) & 0xFF
    otype = (tok >> 12) & 0xFF; idim = (tok >> 20) & 3
    reps = [(tok >> 22) & 7, (tok >> 25) & 7, (tok >> 28) & 7]
    mod = 0
    if tok >> 31:
        ext = t[i]; i += 1
        if ext & 0x3F == 1:
            mod = (ext >> 6) & 0xFF
    if otype == 4:  # imm32
        n = 4 if ncomp == 2 else 1
        vals = t[i:i + n]; i += n
        fs = []
        for v in vals:
            f = struct.unpack("<f", struct.pack("<I", v))[0]
            fs.append(f"{f:g}" if (abs(f) > 1e-6 and abs(f) < 1e7) or v == 0 else f"0x{v:x}")
        s = "l(" + ", ".join(fs) + ")"
        return s, i
    name = TYPES.get(otype, f"T{otype}")
    idx = []
    for d in range(idim):
        r = reps[d]
        if r == 0:
            idx.append(str(t[i])); i += 1
        elif r == 2:
            s, i = operand(t, i); idx.append(s)
        elif r == 3:
            base = t[i]; i += 1
            s, i = operand(t, i); idx.append(f"{s} + {base}")
        else:
            idx.append("?"); i += 1
    if otype in (0, 1, 2, 6, 7) and idx:
        s = name + idx[0] + "".join(f"[{x}]" for x in idx[1:])
    else:
        s = name + "".join(f"[{x}]" for x in idx)
    if ncomp == 2:
        if sel == 0:
            m = "".join(C[k] for k in range(4) if cdata & (1 << k))
            if m and m != "xyzw": s += "." + m
        elif sel == 1:
            sw = "".join(C[(cdata >> (2 * k)) & 3] for k in range(4))
            if sw != "xyzw": s += "." + sw
        else:
            s += "." + C[cdata & 3]
    if mod == 1: s = "-" + s
    elif mod == 2: s = "|" + s + "|"
    elif mod == 3: s = "-|" + s + "|"
    return s, i


def shex(b, names=None):
    t = struct.unpack_from(f"<{len(b)//4}I", b)
    ver = t[0]
    i = 2
    lines = [f"; type {ver >> 16} v{(ver >> 4) & 0xF}.{ver & 0xF}"]
    indent = 0
    while i < len(t):
        tok = t[i]
        op = tok & 0x7FF
        ln = (tok >> 24) & 0x7F
        if op == 53:
            ln = t[i + 1]
            lines.append(f"customdata {ln} dwords")
            i += ln; continue
        name = OPS[op] if op < len(OPS) else f"op{op}"
        j = i + 1
        ext = tok >> 31
        while ext:
            ext = t[j] >> 31; j += 1
        if name.startswith("dcl") or name in ("label",):
            ops = []
            if name in ("dcl_constantbuffer", "dcl_sampler", "dcl_input_ps", "dcl_input", "dcl_output", "dcl_resource", "dcl_input_ps_siv", "dcl_output_siv", "dcl_input_sgv", "dcl_input_siv"):
                try:
                    s, _ = operand(t, j if name != "dcl_resource" else j); ops.append(s)
                except Exception:
                    pass
            if name == "dcl_temps": ops.append(str(t[j]))
            lines.append(f"{name} {', '.join(ops)}")
            i += ln; continue
        ops = []
        try:
            while j < i + ln:
                s, j = operand(t, j); ops.append(s)
        except Exception as e:
            ops.append(f"<err {e}>")
        if name in ("endif", "endloop", "else", "endswitch"): indent -= 1
        sat = "_sat" if (tok >> 13) & 1 and op not in (31, 3, 63, 13, 5, 8) else ""
        if op in (31, 3, 63, 13, 5, 8):
            sat = "_nz" if (tok >> 18) & 1 else "_z"
        txt = "  " * max(indent, 0) + name + sat + " " + ", ".join(ops)
        if names:
            import re
            def rep(m):
                cb, reg = m.group(1), int(m.group(2))
                n = names.get((int(cb), reg))
                return m.group(0) + (f"{{{n}}}" if n else "")
            txt = re.sub(r"cb(\d+)\[(\d+)\]", rep, txt)
        lines.append(txt)
        if name in ("if", "loop", "else", "switch"): indent += 1
        i += ln
    return lines


def container(d):
    assert d[:4] == b"DXBC"
    total, n = struct.unpack_from("<II", d, 24)
    offs = struct.unpack_from(f"<{n}I", d, 32)
    ch = {}
    for o in offs:
        fourcc = d[o:o + 4].decode("latin1"); sz = struct.unpack_from("<I", d, o + 4)[0]
        ch[fourcc] = d[o + 8:o + 8 + sz]
    return ch, total


def disasm(d):
    ch, total = container(d)
    names = {}
    out = []
    if "RDEF" in ch:
        r = rdef(ch["RDEF"])
        cbslots = {n: bp for n, t, bp in r["bind"] if t == 0}
        out.append("; bindings: " + ", ".join(f"{n}(t{t})@{bp}" for n, t, bp in r["bind"]))
        for cbname, vs in r["cb"].items():
            slot = cbslots.get(cbname)
            for so, sz, vn in vs:
                if slot is not None:
                    names[(slot, so // 16)] = names.get((slot, so // 16), "") + ("+" if (slot, so // 16) in names else "") + f"{vn}@{so % 16}"
    code = ch.get("SHEX") or ch.get("SHDR")
    out += shex(code, names)
    return out, total


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    pos = 0; k = 0
    while True:
        p = data.find(b"DXBC", pos)
        if p < 0: break
        ch, total = container(data[p:])
        code = ch.get("SHEX") or ch.get("SHDR")
        kind = struct.unpack_from("<I", code)[0] >> 16 if code else -1
        print(f"=== #{k} at {p} size {total} {'PS' if kind == 0 else 'VS' if kind == 1 else kind}")
        if len(sys.argv) > 2 and str(k) in sys.argv[2].split(","):
            print("\n".join(disasm(data[p:])[0]))
        pos = p + total; k += 1
