"""crops an icon png to its content then scales it up and centers it on a square

usage: python -I fit-icon.py <in.png> <out.png> [size=1024] [fill=0.94]
centers sideways on the alpha centroid cause bounding box centering looks off on
anything with a bite or a leaf sticking out
"""
import sys
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
size = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
fill = float(sys.argv[4]) if len(sys.argv) > 4 else 0.94
im = Image.open(src).convert("RGBA")
im = im.crop(im.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox())
s = size * fill / max(im.size)
im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
a = im.getchannel("A"); w, h = im.size
tot = sum(a.getdata()); cx = sum(x * v for i, v in enumerate(a.getdata()) for x in [i % w]) / tot
canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
canvas.paste(im, (round(size / 2 - cx), (size - h) // 2), im)
canvas.save(out)
print(f"content {w}x{h}, centroid x {cx:.0f} of {w}")
