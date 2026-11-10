"""turns the game's shader graphs from D3D11 bytecode back into HLSL unity can
compile for metal, one .shader per graph

usage: dx2hlsl.py <game Data> <out dir> [graph name ...]

goes instruction by instruction. registers are uint4 so the integer hash math
stays bit exact. cbuffer reads get renamed to the real unity uniforms from the
reflection data. the "Sprite Lit" pass has 16 light variants, so instead of
translating all of them its rebuilt from the forward pass plus URP's own
CombinedShapeLightShared, same as shader graph does it
"""
import sys, struct, pathlib, collections
import UnityPy, lz4.block

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from dxbc import OPS, container  # noqa: E402

# stuff URP's Core.hlsl and friends already declare, dont redeclare
BUILTIN = {
    "_TimeParameters", "_ScaledScreenParams", "_GlobalMipBias", "_ProjectionParams", "_ScreenParams",
    "_WorldSpaceCameraPos", "unity_MatrixVP", "unity_MatrixInvVP", "unity_MatrixV", "unity_MatrixInvV",
    "glstate_matrix_projection", "unity_MatrixInvP", "unity_ObjectToWorld", "unity_WorldToObject",
    "_Time", "_SinTime", "_CosTime", "unity_DeltaTime", "_ZBufferParams", "unity_OrthoParams",
    "unity_LODFade", "unity_WorldTransformParams", "unity_RenderingLayer",
}
SKIP_PROPS = {"unity_Lightmaps", "unity_LightmapsInd", "unity_ShadowMasks"}
C = "xyzw"
BLEND = ["Zero", "One", "DstColor", "SrcColor", "OneMinusDstColor", "SrcAlpha", "OneMinusSrcColor",
         "DstAlpha", "OneMinusDstAlpha", "SrcAlphaSaturate", "OneMinusSrcAlpha"]
ZTEST = ["Always", "Never", "Less", "Equal", "LEqual", "Greater", "NotEqual", "GEqual", "Always"]
CULL = ["Off", "Front", "Back"]


# dxbc parsing

def signature(b, big):
    n = struct.unpack_from("<I", b, 0)[0]
    out = []
    for k in range(n):
        if big:
            _, name, si, sv, ct, reg, mask = struct.unpack_from("<6IB", b, 8 + 32 * k)
        else:
            name, si, sv, ct, reg, mask = struct.unpack_from("<5IB", b, 8 + 24 * k)
        out.append(dict(name=b[name:b.index(b"\0", name)].decode(), index=si, sv=sv, type=ct, reg=reg, mask=mask))
    return out


class Op:
    def __init__(self, t, i):
        tok = t[i]; i += 1
        self.ncomp = tok & 3
        self.sel = (tok >> 2) & 3
        cdata = (tok >> 4) & 0xFF
        self.type = (tok >> 12) & 0xFF
        idim = (tok >> 20) & 3
        reps = [(tok >> 22) & 7, (tok >> 25) & 7, (tok >> 28) & 7]
        self.mod = 0
        ext = tok >> 31
        while ext:
            e = t[i]; i += 1
            if e & 0x3F == 1:
                self.mod = (e >> 6) & 0xFF
            ext = e >> 31
        if self.ncomp == 2:
            if self.sel == 0:
                self.comps = [k for k in range(4) if cdata & (1 << k)]
                self.swz = [0, 1, 2, 3]
            elif self.sel == 1:
                self.swz = [(cdata >> (2 * k)) & 3 for k in range(4)]
                self.comps = None
            else:
                self.swz = [cdata & 3] * 4
                self.comps = None
        else:
            self.swz = [0, 0, 0, 0]
            self.comps = [0] if self.ncomp == 1 else []
        self.imm = None
        self.idx = []
        if self.type == 4:  # immediate32
            n = 4 if self.ncomp == 2 else 1
            self.imm = list(t[i:i + n]); i += n
            if n == 1:
                self.imm *= 4
        for d in range(idim):
            r = reps[d]
            if r == 0:
                self.idx.append(t[i]); i += 1
            elif r == 1:
                self.idx.append(t[i] | (t[i + 1] << 32)); i += 2
            else:
                raise NotImplementedError(f"relative operand index (rep {r})")
        self.end = i


class Ins:
    pass


def instructions(code):
    t = struct.unpack_from(f"<{len(code) // 4}I", code)
    i = 2
    out = []
    while i < len(t):
        tok = t[i]
        op = tok & 0x7FF
        ln = (tok >> 24) & 0x7F
        if op == 53:  # customdata
            cls = tok >> 11
            ln = t[i + 1]
            if cls == 3:
                raise NotImplementedError("immediate constant buffer")
            i += ln; continue
        name = OPS[op] if op < len(OPS) else f"op{op}"
        ins = Ins()
        ins.name, ins.op = name, op
        ins.sat = bool((tok >> 13) & 1)
        ins.nz = bool((tok >> 18) & 1)
        ins.offset = (0, 0, 0)
        j = i + 1
        ext = tok >> 31
        while ext:
            e = t[j]; j += 1
            if e & 0x3F == 1:
                def s4(v): return v - 16 if v & 8 else v
                ins.offset = (s4((e >> 9) & 15), s4((e >> 13) & 15), s4((e >> 17) & 15))
            ext = e >> 31
        ins.ops = []
        ins.raw = t[j:i + ln]
        if name.startswith("dcl") or name in ("label", "nop"):
            if name == "dcl_temps":
                ins.ntemps = t[j]
            if name in ("dcl_input_ps", "dcl_input_ps_siv", "dcl_input_ps_sgv"):
                ins.interp = (tok >> 11) & 15
                ins.ops = [Op(t, j)]
            if name == "dcl_resource":
                ins.dim = (tok >> 11) & 31
                ins.ops = [Op(t, j)]
            out.append(ins)
            i += ln; continue
        while j < i + ln:
            o = Op(t, j); j = o.end
            ins.ops.append(o)
        out.append(ins)
        i += ln
    return out


def parse_program(dx):
    ch, _ = container(dx)
    p = {}
    for k, big in (("ISGN", False), ("ISG1", True)):
        if k in ch: p["in"] = signature(ch[k], big)
    for k, big in (("OSGN", False), ("OSG1", True), ("OSG5", True)):
        if k in ch: p["out"] = signature(ch[k], big)
    code = ch.get("SHEX") or ch.get("SHDR")
    p["kind"] = "ps" if struct.unpack_from("<I", code)[0] >> 16 == 0 else "vs"
    p["ins"] = instructions(code)
    return p


# reflection

# inline sampler flags, filter in bits 0-1 and wrap U/V/W in bits 2-7 (TextureWrapMode).
# figured out by lining up the game's flags 0, 1, 84, 85 with the donor's
# sampler_PointRepeat, LinearRepeat, PointClamp and LinearClamp
FILTER = {0: "Point", 1: "Linear", 2: "Trilinear"}
WRAP = {0: "Repeat", 1: "Clamp", 2: "Mirror", 3: "MirrorOnce"}


def inline_sampler(flags):
    f, u, v = flags & 3, (flags >> 2) & 3, (flags >> 4) & 3
    if u != v:
        raise NotImplementedError(f"inline sampler {flags} with different U/V wrap")
    return f"sampler_cug_{FILTER[f]}_{WRAP[u]}"


class Refl:
    """names for one program's cbuffer registers, textures and samplers"""
    def __init__(self, prog, names):
        cp = prog["m_CommonParameters"]
        self.cb = {}  # (slot, reg, comp) -> expression
        self.cbname = {}
        self.uniforms = {}  # name -> (cbuffer name, hlsl type)
        slot_of = {b["m_NameIndex"]: b["m_Index"] for b in cp["m_ConstantBufferBindings"]}
        for cb in cp["m_ConstantBuffers"]:
            cbn = names[cb["m_NameIndex"]]
            slot = slot_of[cb["m_NameIndex"]]
            self.cbname[slot] = cbn
            for v in cb["m_VectorParams"]:
                n = names[v["m_NameIndex"]]
                base, c0, dim = v["m_Index"] // 16, (v["m_Index"] % 16) // 4, v["m_Dim"]
                arr = max(v["m_ArraySize"], 1)
                ty = ("float", "int", "uint", "bool")[v["m_Type"]] if v["m_Type"] < 4 else "float"
                self.uniforms[n] = (cbn, ty + (str(dim) if dim > 1 else ""), v["m_ArraySize"])
                for a in range(arr):
                    for k in range(dim):
                        el = f"{n}[{a}]" if v["m_ArraySize"] else n
                        self.cb[(slot, base + a, c0 + k)] = (f"{el}.{C[k]}" if dim > 1 else el, ty)
            for m in cb["m_MatrixParams"]:
                n = names[m["m_NameIndex"]]
                base = m["m_Index"] // 16
                rows = m["m_RowCount"]
                self.uniforms[n] = (cbn, "float4x4", m["m_ArraySize"])
                arr = max(m["m_ArraySize"], 1)
                for a in range(arr):
                    el = f"{n}[{a}]" if m["m_ArraySize"] else n
                    for col in range(4):
                        for r in range(rows):
                            self.cb[(slot, base + a * 4 + col, r)] = (f"{el}._m{r}{col}", "float")
            if cb["m_StructParams"]:
                raise NotImplementedError("struct params")
        self.tex = {}
        self.samp = {}
        for t in cp["m_TextureParams"]:
            n = names[t["m_NameIndex"]]
            self.tex[t["m_Index"]] = n
            if t["m_SamplerIndex"] >= 0:
                self.samp.setdefault(t["m_SamplerIndex"], "sampler" + n)
        for s in cp.get("m_Samplers", []):
            self.samp.setdefault(s["bindPoint"], inline_sampler(s["sampler"]))


# translation

def fl(bits):
    f = struct.unpack("<f", struct.pack("<I", bits))[0]
    if bits == 0:
        return "0.0"
    if bits & 0x7F800000 in (0, 0x7F800000):
        return f"asfloat(0x{bits:08x}u)"
    s = repr(f)
    if struct.unpack("<I", struct.pack("<f", float(s)))[0] == bits:
        return s if ("e" in s or "." in s) else s + ".0"
    return f"asfloat(0x{bits:08x}u)"


class Translator:
    def __init__(self, prog, refl, tag, infields, outfields):
        self.p, self.r, self.tag = prog, refl, tag
        self.infields = infields  # (reg, comp) -> expr (typed, raw input)
        self.outfields = outfields  # list of (field expr, reg, comps)
        self.used_cb = set()
        self.used_tex = set()
        self.used_samp = set()
        self.ntemps = 0

    def raw(self, o, c):
        """uint expression for component c of operand o"""
        t = o.type
        if t == 4:
            return f"0x{o.imm[c]:08x}u"
        if t == 0:
            return f"r{o.idx[0]}.{C[c]}"
        if t == 1:
            e = self.infields.get((o.idx[0], c))
            if e is None:
                return "0u"
            return f"asuint({e})"
        if t == 8:
            key = (o.idx[0], o.idx[1], c)
            e = self.r.cb.get(key)
            if e is None:
                return "0u"
            self.used_cb.add(e[0].split(".")[0].split("[")[0])
            return f"asuint({e[0]})"
        if t == 2:
            return f"o{o.idx[0]}.{C[c]}"
        raise NotImplementedError(f"operand type {t}")

    def comp(self, o, pos):
        return o.swz[pos] if o.ncomp == 2 else 0

    def src(self, o, pos, kind):
        c = self.comp(o, pos)
        if o.type == 4 and kind == "f" and o.mod == 0:
            return fl(o.imm[c])
        e = self.raw(o, c)
        if kind == "f":
            e = f"asfloat({e})"
            if o.mod & 2: e = f"abs({e})"
            if o.mod & 1: e = f"(-{e})"
        elif kind == "i":
            e = f"asint({e})"
            if o.mod & 2: e = f"abs({e})"
            if o.mod & 1: e = f"(-{e})"
        else:
            if o.mod & 1: e = f"(0u - {e})"
        return e

    def dst(self, o, c):
        if o.type == 0: return f"r{o.idx[0]}.{C[c]}"
        if o.type == 2: return f"o{o.idx[0]}.{C[c]}"
        raise NotImplementedError(f"dest type {o.type}")

    def assign(self, o, vals, kind, sat=False):
        """vals is comp -> expression of type kind. two phase so writing dst cant clobber a src still being read"""
        if o.type == 13:
            return []
        lines = []
        tmp = []
        for k, c in enumerate(o.comps):
            v = vals[c]
            if kind == "f":
                if sat: v = f"saturate({v})"
                v = f"asuint({v})"
            elif kind == "i":
                v = f"asuint({v})"
            tmp.append((f"t{k}", v, self.dst(o, c)))
        if len(tmp) == 1:
            return [f"{tmp[0][2]} = {tmp[0][1]};"]
        return ["{ " + " ".join(f"uint {n} = {v};" for n, v, _ in tmp) + " " + " ".join(f"{d} = {n};" for n, _, d in tmp) + " }"]

    def translate(self):
        L = []
        ind = 1
        FB = {"add": "{0} + {1}", "mul": "{0} * {1}", "div": "{0} / {1}", "min": "min({0}, {1})", "max": "max({0}, {1})"}
        FC = {"lt": "<", "ge": ">=", "eq": "==", "ne": "!="}
        IC = {"ieq": ("i", "=="), "ine": ("i", "!="), "ilt": ("i", "<"), "ige": ("i", ">="), "ult": ("u", "<"), "uge": ("u", ">=")}
        F1 = {"frc": "frac({0})", "round_ni": "floor({0})", "round_pi": "ceil({0})", "round_z": "trunc({0})",
              "round_ne": "round({0})", "rsq": "rsqrt({0})", "sqrt": "sqrt({0})", "exp": "exp2({0})", "log": "log2({0})",
              "rcp": "rcp({0})", "deriv_rtx": "ddx({0})", "deriv_rty": "ddy({0})", "deriv_rtx_coarse": "ddx_coarse({0})",
              "deriv_rty_coarse": "ddy_coarse({0})", "deriv_rtx_fine": "ddx_fine({0})", "deriv_rty_fine": "ddy_fine({0})"}
        IB = {"iadd": ("u", "{0} + {1}"), "and": ("u", "{0} & {1}"), "or": ("u", "{0} | {1}"), "xor": ("u", "{0} ^ {1}"),
              "ishl": ("u", "{0} << ({1} & 31u)"), "ushr": ("u", "{0} >> ({1} & 31u)"),
              "ishr": ("i", "{0} >> ({1} & 31)"), "imax": ("i", "max({0}, {1})"), "imin": ("i", "min({0}, {1})"),
              "umax": ("u", "max({0}, {1})"), "umin": ("u", "min({0}, {1})")}
        for ins in self.p["ins"]:
            n = ins.name
            pad = "    " * ind
            if n == "dcl_temps":
                self.ntemps = ins.ntemps; continue
            if n.startswith("dcl") or n in ("label", "nop"):
                continue
            o = ins.ops
            out = []
            if n in FB:
                d = o[0]; out = self.assign(d, {c: FB[n].format(self.src(o[1], c, "f"), self.src(o[2], c, "f")) for c in d.comps}, "f", ins.sat)
            elif n == "mad":
                d = o[0]; out = self.assign(d, {c: f"mad({self.src(o[1], c, 'f')}, {self.src(o[2], c, 'f')}, {self.src(o[3], c, 'f')})" for c in d.comps}, "f", ins.sat)
            elif n in FC:
                d = o[0]; out = self.assign(d, {c: f"(({self.src(o[1], c, 'f')} {FC[n]} {self.src(o[2], c, 'f')}) ? 0xffffffffu : 0u)" for c in d.comps}, "u")
            elif n in IC:
                k, cmp = IC[n]; d = o[0]
                out = self.assign(d, {c: f"(({self.src(o[1], c, k)} {cmp} {self.src(o[2], c, k)}) ? 0xffffffffu : 0u)" for c in d.comps}, "u")
            elif n in F1:
                d = o[0]; out = self.assign(d, {c: F1[n].format(self.src(o[1], c, "f")) for c in d.comps}, "f", ins.sat)
            elif n == "mov":
                d = o[0]
                if ins.sat or o[1].mod:
                    out = self.assign(d, {c: self.src(o[1], c, "f") for c in d.comps}, "f", ins.sat)
                else:
                    out = self.assign(d, {c: self.raw(o[1], self.comp(o[1], c)) for c in d.comps}, "u")
            elif n == "movc":
                d = o[0]
                vals = {}
                for c in d.comps:
                    if ins.sat or o[2].mod or o[3].mod:
                        raise NotImplementedError("movc with modifiers")
                    vals[c] = f"(({self.raw(o[1], self.comp(o[1], c))}) != 0u ? {self.raw(o[2], self.comp(o[2], c))} : {self.raw(o[3], self.comp(o[3], c))})"
                out = self.assign(d, vals, "u")
            elif n in ("dp2", "dp3", "dp4"):
                k = int(n[2]); d = o[0]
                e = " + ".join(f"{self.src(o[1], p, 'f')} * {self.src(o[2], p, 'f')}" for p in range(k))
                out = [f"{{ float dp = {e};"] + self.assign(d, {c: "dp" for c in d.comps}, "f", ins.sat) + ["}"]
            elif n == "sincos":
                ds, dc, s = o
                if ds.type != 13: out += self.assign(ds, {c: f"sin({self.src(s, c, 'f')})" for c in ds.comps}, "f", ins.sat)
                if dc.type != 13: out += self.assign(dc, {c: f"cos({self.src(s, c, 'f')})" for c in dc.comps}, "f", ins.sat)
            elif n in IB:
                k, f = IB[n]; d = o[0]
                vals = {c: f.format(self.src(o[1], c, k), self.src(o[2], c, k)) for c in d.comps}
                out = self.assign(d, vals, "i" if k == "i" else "u")
            elif n in ("imul", "umul"):
                hi, lo, a, b = o
                if hi.type != 13: raise NotImplementedError("imul hi")
                out = self.assign(lo, {c: f"{self.src(a, c, 'u')} * {self.src(b, c, 'u')}" for c in lo.comps}, "u")
            elif n in ("imad", "umad"):
                d = o[0]; out = self.assign(d, {c: f"{self.src(o[1], c, 'u')} * {self.src(o[2], c, 'u')} + {self.src(o[3], c, 'u')}" for c in d.comps}, "u")
            elif n == "udiv":
                q, r, a, b = o
                if q.type != 13: out += self.assign(q, {c: f"{self.src(a, c, 'u')} / {self.src(b, c, 'u')}" for c in q.comps}, "u")
                if r.type != 13: out += self.assign(r, {c: f"{self.src(a, c, 'u')} % {self.src(b, c, 'u')}" for c in r.comps}, "u")
            elif n == "not":
                d = o[0]; out = self.assign(d, {c: f"~{self.src(o[1], c, 'u')}" for c in d.comps}, "u")
            elif n == "ineg":
                d = o[0]; out = self.assign(d, {c: f"-{self.src(o[1], c, 'i')}" for c in d.comps}, "i")
            elif n == "ftoi":
                d = o[0]; out = self.assign(d, {c: f"(int){self.src(o[1], c, 'f')}" for c in d.comps}, "i")
            elif n == "ftou":
                d = o[0]; out = self.assign(d, {c: f"(uint){self.src(o[1], c, 'f')}" for c in d.comps}, "u")
            elif n == "itof":
                d = o[0]; out = self.assign(d, {c: f"(float){self.src(o[1], c, 'i')}" for c in d.comps}, "f")
            elif n == "utof":
                d = o[0]; out = self.assign(d, {c: f"(float){self.src(o[1], c, 'u')}" for c in d.comps}, "f")
            elif n in ("sample", "sample_b", "sample_l", "sample_c_lz", "sample_d"):
                d, a, t, s = o[:4]
                tex = self.r.tex[t.idx[0]]; smp = self.r.samp[s.idx[0]]
                self.used_tex.add(tex); self.used_samp.add(smp)
                uv = f"float2({self.src(a, 0, 'f')}, {self.src(a, 1, 'f')})"
                off = f", int2({ins.offset[0]}, {ins.offset[1]})" if any(ins.offset) else ""
                if n == "sample":
                    call = f"{tex}.Sample({smp}, {uv}{off})"
                elif n == "sample_b":
                    call = f"{tex}.SampleBias({smp}, {uv}, {self.src(o[4], 0, 'f')}{off})"
                elif n == "sample_l":
                    call = f"{tex}.SampleLevel({smp}, {uv}, {self.src(o[4], 0, 'f')}{off})"
                elif n == "sample_d":
                    gx = f"float2({self.src(o[4], 0, 'f')}, {self.src(o[4], 1, 'f')})"
                    gy = f"float2({self.src(o[5], 0, 'f')}, {self.src(o[5], 1, 'f')})"
                    call = f"{tex}.SampleGrad({smp}, {uv}, {gx}, {gy}{off})"
                else:
                    raise NotImplementedError(n)
                out = [f"{{ float4 sm = {call};"] + self.assign(d, {c: f"sm.{C[t.swz[c]]}" for c in d.comps}, "f", ins.sat) + ["}"]
            elif n == "ld":
                d, a, t = o
                tex = self.r.tex[t.idx[0]]; self.used_tex.add(tex)
                call = f"{tex}.Load(int3({self.src(a, 0, 'i')}, {self.src(a, 1, 'i')}, {self.src(a, 3, 'i')}))"
                out = [f"{{ float4 sm = {call};"] + self.assign(d, {c: f"sm.{C[t.swz[c]]}" for c in d.comps}, "f") + ["}"]
            elif n == "discard":
                out = [f"if (({self.raw(o[0], self.comp(o[0], 0))}) {'!=' if ins.nz else '=='} 0u) discard;"]
            elif n == "if":
                L.append(pad + f"if (({self.raw(o[0], self.comp(o[0], 0))}) {'!=' if ins.nz else '=='} 0u) {{"); ind += 1; continue
            elif n == "else":
                L.append("    " * (ind - 1) + "} else {"); continue
            elif n in ("endif", "endloop"):
                ind -= 1; L.append("    " * ind + "}"); continue
            elif n == "loop":
                L.append(pad + "[loop] for (;;) {"); ind += 1; continue
            elif n == "break":
                out = ["break;"]
            elif n == "breakc":
                out = [f"if (({self.raw(o[0], self.comp(o[0], 0))}) {'!=' if ins.nz else '=='} 0u) break;"]
            elif n == "continue":
                out = ["continue;"]
            elif n == "continuec":
                out = [f"if (({self.raw(o[0], self.comp(o[0], 0))}) {'!=' if ins.nz else '=='} 0u) continue;"]
            elif n == "ret":
                out = ["return CUG_RET;"]
            elif n == "retc":
                out = [f"if (({self.raw(o[0], self.comp(o[0], 0))}) {'!=' if ins.nz else '=='} 0u) return CUG_RET;"]
            else:
                raise NotImplementedError(f"instruction {n}")
            L += [pad + x for x in out]
        return L


# shader assembly

def sig_fields(sig, prefix):
    """struct fields for a signature, plus (reg, comp) -> field component"""
    fields, comp = [], {}
    used = collections.Counter()
    for e in sig:
        cs = [k for k in range(4) if e["mask"] & (1 << k)]
        ty = {1: "uint", 2: "int", 3: "float"}.get(e["type"], "float")
        sem = e["name"].upper()
        if sem == "SV_POSITION": sem = "SV_POSITION"
        elif sem.startswith("SV_"): pass
        else: sem = f"{e['name']}{e['index']}"
        fname = f"{prefix}{e['reg']}_{''.join(C[k] for k in cs)}"
        fields.append((f"{ty}{len(cs) if len(cs) > 1 else ''}", fname, sem, e))
        for k, c in enumerate(cs):
            comp[(e["reg"], c)] = f"{fname}{'.' + C[k] if len(cs) > 1 else ''}"
    return fields, comp


def decl_type(ty):
    return ty


class Graph:
    def __init__(self, tt, blob):
        self.tt, self.blob = tt, blob
        self.pf = tt["m_ParsedForm"]
        self.name = self.pf["m_Name"][14:]
        n = struct.unpack_from("<I", blob, 0)[0]
        self.entries = [struct.unpack_from("<3I", blob, 4 + 12 * k) for k in range(n)]

    def dxbc(self, idx):
        off, ln, _ = self.entries[idx]
        e = self.blob[off:off + ln]
        p = e.find(b"DXBC")
        total = struct.unpack_from("<I", e, p + 24)[0]
        return e[p:p + total]

    def program(self, pas, stage):
        pv = pas[stage]
        subs = [s for x in pv["m_PlayerSubPrograms"] for s in x]
        return pv, subs


def translate_pass(g, pas, names, uniforms, textures, extra_out=None):
    """(decl names, code lines) for one pass's vertex+fragment pair"""
    pv, vsubs = g.program(pas, "progVertex")
    pf_, fsubs = g.program(pas, "progFragment")
    vs = parse_program(g.dxbc(vsubs[0]["m_BlobIndex"]))
    ps = parse_program(g.dxbc(fsubs[0]["m_BlobIndex"]))
    vr, fr = Refl(pv, names), Refl(pf_, names)
    for r in (vr, fr):
        for n, (cbn, ty, arr) in r.uniforms.items():
            uniforms[n] = (cbn, ty, arr)
    vin, vin_comp = sig_fields(vs["in"], "v")
    v2f, v2f_comp = sig_fields(vs["out"], "o")
    # fragment inputs: map by semantic to the vertex outputs
    by_sem = {(e["name"].upper(), e["index"]): e for e in vs["out"]}
    fin_comp = {}
    for e in ps["in"]:
        ve = by_sem.get((e["name"].upper(), e["index"]))
        for c in range(4):
            if not e["mask"] & (1 << c): continue
            if ve is None:
                continue
            # assumes the same component layout, unity links them that way anyway
            fin_comp[(e["reg"], c)] = "i." + v2f_comp[(ve["reg"], c)]
    L = []
    L.append("struct CUG_VSIn {")
    for ty, fn, sem, e in vin:
        L.append(f"    {ty} {fn} : {sem};")
    L.append("};")
    L.append("struct CUG_V2F {")
    for ty, fn, sem, e in v2f:
        L.append(f"    {ty} {fn} : {sem};")
    if extra_out:
        L += ["    " + x for x in extra_out]
    L.append("};")
    # vertex
    vt = Translator(vs, vr, "vs", {k: "i." + v for k, v in vin_comp.items()}, None)
    vb = vt.translate()
    nout = max([e["reg"] for e in vs["out"]] + [0]) + 1
    L.append("CUG_V2F CUG_VS(CUG_VSIn i)")
    L.append("{")
    L.append("    CUG_V2F O = (CUG_V2F)0;")
    L += [f"    uint4 r{k} = 0;" for k in range(vt.ntemps)]
    L += [f"    uint4 o{k} = 0;" for k in range(nout)]
    L.append("#define CUG_RET CUG_VS_Out(O" + "".join(f", o{k}" for k in range(nout)) + ")")
    L += vb
    L.append("#undef CUG_RET")
    L.append("}")
    # output packer, declared before CUG_VS
    pk = ["CUG_V2F CUG_VS_Out(CUG_V2F O" + "".join(f", uint4 o{k}" for k in range(nout)) + ")", "{"]
    for ty, fn, sem, e in v2f:
        cs = [k for k in range(4) if e["mask"] & (1 << k)]
        base = ty.rstrip("1234")
        cast = {"float": "asfloat", "int": "asint", "uint": ""}[base]
        sw = "".join(C[k] for k in cs)
        pk.append(f"    O.{fn} = {cast}(o{e['reg']}.{sw});")
    pk += ["    return O;", "}"]
    # fragment
    ft = Translator(ps, fr, "ps", fin_comp, None)
    fb = ft.translate()
    F = ["float4 CUG_PS(CUG_V2F i)", "{"]
    F += [f"    uint4 r{k} = 0;" for k in range(ft.ntemps)]
    F.append("    uint4 o0 = 0;")
    F.append("#define CUG_RET asfloat(o0)")
    F += fb
    F.append("#undef CUG_RET")
    F.append("}")
    for t in (vt, ft):
        for tx in t.used_tex: textures.setdefault(tx, set())
        for tx, s in ((tx, s) for tx in t.used_tex for s in t.used_samp):
            pass
    used = vt.used_cb | ft.used_cb
    return L[:L.index("CUG_V2F CUG_VS(CUG_VSIn i)")] + pk + L[L.index("CUG_V2F CUG_VS(CUG_VSIn i)"):] + F, used, ft.used_tex | vt.used_tex, ft.used_samp | vt.used_samp, (vs, ps)


def prop_line(p):
    n, d, ty = p["m_Name"], p["m_Description"], p["m_Type"]
    dv = [p[f"m_DefValue[{k}]"] for k in range(4)]
    if ty == 0: return f'{n}("{d}", Color) = ({dv[0]}, {dv[1]}, {dv[2]}, {dv[3]})'
    if ty == 1: return f'{n}("{d}", Vector) = ({dv[0]}, {dv[1]}, {dv[2]}, {dv[3]})'
    if ty == 2: return f'{n}("{d}", Float) = {dv[0]}'
    if ty == 3: return f'{n}("{d}", Range({dv[1]}, {dv[2]})) = {dv[0]}'
    if ty == 4:
        dn = p.get("m_DefTexture", {}).get("m_DefaultName", "white") or "white"
        return f'{n}("{d}", 2D) = "{dn}" {{}}'
    if ty == 5: return f'{n}("{d}", Int) = {int(dv[0])}'
    return None


def build(g, outdir):
    names_all = {}
    passes = g.pf["m_SubShaders"][0]["m_Passes"]
    uniforms, textures = {}, {}
    blocks = []
    fwd = None
    for k, pas in enumerate(passes):
        tags = dict(pas["m_State"]["m_Tags"]["tags"])
        if tags.get("LIGHTMODE") == "UniversalForward":
            fwd = k
    for k, pas in enumerate(passes):
        names = {v: n for n, v in pas["m_NameIndices"]}
        st = pas["m_State"]
        tags = dict(st["m_Tags"]["tags"])
        lm = tags.get("LIGHTMODE", "")
        _, fsubs = g.program(pas, "progFragment")
        hybrid = len(fsubs) > 1
        if hybrid:
            if lm != "Universal2D" or fwd is None:
                raise NotImplementedError(f"{len(fsubs)} variants in pass {st['m_Name']}")
            src = passes[fwd]
            names = {v: n for n, v in src["m_NameIndices"]}
            code, used, tex, smp, _ = translate_pass(g, src, names, uniforms, textures, ["float2 cuLightUV : TEXCOORD7;"])
        else:
            code, used, tex, smp, _ = translate_pass(g, pas, names, uniforms, textures)
        blocks.append(dict(k=k, st=st, lm=lm, hybrid=hybrid, code=code, used=used, tex=tex, smp=smp))

    # material cbuffer is the union of every pass so they all see the same layout
    mat = {n: v for n, v in uniforms.items() if v[0] == "UnityPerMaterial"}
    props = [p for p in g.pf["m_PropInfo"]["m_Props"] if p["m_Name"] not in SKIP_PROPS]
    for p in props:
        if p["m_Type"] == 4:
            mat.setdefault(p["m_Name"] + "_TexelSize", ("UnityPerMaterial", "float4", 0))
        else:
            mat.setdefault(p["m_Name"], ("UnityPerMaterial", "float4" if p["m_Type"] in (0, 1) else "float", 0))

    H = [f"// generated by scripts/dx2hlsl.py from Shader Graphs/{g.name} (D3D11 bytecode), dont edit, rerun the script",
         "#include \"Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl\"",
         "#include \"Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/Core2D.hlsl\"",
         "CBUFFER_START(UnityPerMaterial)"]
    for n, (cbn, ty, arr) in sorted(mat.items()):
        H.append(f"{ty} {n}{f'[{arr}]' if arr else ''};")
    H.append("CBUFFER_END")
    for b in blocks:
        H.append(f"#if defined(CUG_PASS_{b['k']})")
        for n in sorted(b["used"]):
            if n in BUILTIN or n in mat: continue
            cbn, ty, arr = uniforms[n]
            H.append(f"{ty} {n}{f'[{arr}]' if arr else ''};")
        for t in sorted(b["tex"]):
            H.append(f"TEXTURE2D({t});")
        for s in sorted(b["smp"]):
            H.append(f"SAMPLER({s});")
        H += b["code"]
        if b["hybrid"]:
            H += ["CUG_V2F vert(CUG_VSIn i)", "{", "    CUG_V2F o = CUG_VS(i);",
                  "    float4 cs = o.o0_xyzw;",
                  "    o.cuLightUV = ComputeScreenPos(cs / cs.w).xy;", "    return o;", "}",
                  "#include \"Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/LightingUtility.hlsl\"",
                  "#if USE_SHAPE_LIGHT_TYPE_0", "SHAPE_LIGHT(0)", "#endif",
                  "#if USE_SHAPE_LIGHT_TYPE_1", "SHAPE_LIGHT(1)", "#endif",
                  "#if USE_SHAPE_LIGHT_TYPE_2", "SHAPE_LIGHT(2)", "#endif",
                  "#if USE_SHAPE_LIGHT_TYPE_3", "SHAPE_LIGHT(3)", "#endif",
                  "#include \"Packages/com.unity.render-pipelines.universal/Shaders/2D/Include/CombinedShapeLightShared.hlsl\"",
                  "half4 frag(CUG_V2F i) : SV_Target", "{",
                  "    half4 c = (half4)CUG_PS(i);",
                  "    clip(c.a == 0 ? -1 : 1);",
                  "    SurfaceData2D surfaceData;", "    InputData2D inputData;",
                  "    InitializeSurfaceData(c.rgb, c.a, half4(1, 1, 1, 1), surfaceData);",
                  "    InitializeInputData(float2(0, 0), i.cuLightUV, inputData);",
                  "    return max(CombinedShapeLightShared(surfaceData, inputData), 0);", "}"]
        else:
            H += ["CUG_V2F vert(CUG_VSIn i) { return CUG_VS(i); }",
                  "float4 frag(CUG_V2F i) : SV_Target { return CUG_PS(i); }"]
        H.append("#endif")
    hl = outdir / f"CUG-{g.name}.hlsl"
    hl.write_text("\n".join(H) + "\n")

    S = [f"// generated by scripts/dx2hlsl.py from Shader Graphs/{g.name}, dont edit, rerun the script",
         f'Shader "CUG/{g.name}"', "{", "    Properties", "    {"]
    for p in props:
        ln = prop_line(p)
        if ln: S.append("        " + ln)
    S += ["    }", "    SubShader", "    {"]
    full = all(b["lm"] == "" for b in blocks)
    if full:
        S.append('        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" }')
    else:
        S.append('        Tags { "Queue"="Transparent" "RenderType"="Transparent" "RenderPipeline"="UniversalPipeline" }')
    for b in blocks:
        st = b["st"]; bl = st["rtBlend0"]
        v = lambda x: int(x["val"])
        S += ["        Pass", "        {", f'            Name "{st["m_Name"]}"']
        if b["lm"]:
            S.append(f'            Tags {{ "LightMode"="{b["lm"]}" }}')
        S.append(f"            Blend {BLEND[v(bl['srcBlend'])]} {BLEND[v(bl['destBlend'])]}, {BLEND[v(bl['srcBlendAlpha'])]} {BLEND[v(bl['destBlendAlpha'])]}")
        S.append(f"            ZWrite {'On' if v(st['zWrite']) else 'Off'}")
        S.append(f"            ZTest {ZTEST[v(st['zTest'])]}")
        S.append(f"            Cull {CULL[v(st['culling'])]}")
        S += ["            HLSLPROGRAM", "            #pragma vertex vert", "            #pragma fragment frag"]
        if b["hybrid"]:
            S += [f"            #pragma multi_compile USE_SHAPE_LIGHT_TYPE_{n} __" for n in range(4)]
        S += [f"            #define CUG_PASS_{b['k']}", f'            #include "CUG-{g.name}.hlsl"', "            ENDHLSL", "        }"]
    S += ["    }", "}"]
    (outdir / f"CUG-{g.name}.shader").write_text("\n".join(S) + "\n")
    return [(b["k"], b["st"]["m_Name"], b["lm"], "lit-hybrid" if b["hybrid"] else "direct") for b in blocks]


def main():
    data, out = sys.argv[1], pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    want = set(sys.argv[3:])
    env = UnityPy.load(data)
    for obj in env.objects:
        if obj.type.name != "Shader": continue
        tt = obj.read_typetree(); n = tt["m_ParsedForm"]["m_Name"]
        if not n.startswith("Shader Graphs/") or (want and n[14:] not in want): continue
        pi = tt["platforms"].index(4)
        blob = b"".join(lz4.block.decompress(bytes(tt["compressedBlob"])[o:o + c], uncompressed_size=d)
                        for o, c, d in zip(tt["offsets"][pi], tt["compressedLengths"][pi], tt["decompressedLengths"][pi]))
        g = Graph(tt, blob)
        try:
            res = build(g, out)
            print(f"ok   {g.name}: " + "; ".join(f"{k} {nm} {lm or '-'} {how}" for k, nm, lm, how in res))
        except NotImplementedError as e:
            print(f"FAIL {g.name}: {e}")


if __name__ == "__main__":
    main()
