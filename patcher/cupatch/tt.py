"""json for UnityPy typetrees. they mix raw bytes in with normal values so plain json chokes"""
import base64


def encode(v):
    if isinstance(v, (bytes, bytearray)):
        return {"__b": base64.b64encode(v).decode()}
    if isinstance(v, dict):
        return {k: encode(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [encode(x) for x in v]
    return v


def decode(v):
    if isinstance(v, dict):
        if len(v) == 1 and "__b" in v:
            return base64.b64decode(v["__b"])
        return {k: decode(x) for k, x in v.items()}
    if isinstance(v, list):
        return [decode(x) for x in v]
    return v
