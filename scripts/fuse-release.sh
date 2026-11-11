#!/bin/zsh
# fuses the arm64 and intel launchers into one universal app and zip
# run scripts/build-release.sh and ARCH=x86_64 scripts/build-release.sh first
# mach-o files in both get lipod. files only one side has get copied, thats the
# simd variants and they only load on their own chip
# anything else that differs like base_library.zip comes from the arm build
set -e
ROOT=${0:A:h:h}
cd "$ROOT"
NAME="MacOS Unknown"
VER=${1:-$(sed -n 's/^VERSION = "\(.*\)"/\1/p' patcher/launcher.py)}
A="build/release/dist/$NAME.app"
X="build/release-x86_64/dist/$NAME.app"
OUT=build/release-universal
U="$OUT/$NAME.app"

for app in $A $X; do
  [[ -d $app ]] || { echo "$app missing, build it first"; exit 1; }
done
[[ -e $OUT ]] && { echo "$OUT already exists, move it aside first"; exit 1; }
mkdir -p $OUT

ditto "$A" "$U"
rm -rf "$U/Contents/_CodeSignature"

fused=0 copied=0
cd "$X"
find . \( -type f -o -type l \) | while read -r f; do
  [[ $f == ./Contents/_CodeSignature/* ]] && continue
  dst="$ROOT/$U/$f"
  if [[ ! -e $dst && ! -L $dst ]]; then
    mkdir -p "${dst:h}"
    ditto "$f" "$dst"
    (( ++copied ))
  elif [[ ! -L $f ]] && lipo -archs "$f" &>/dev/null && [[ $(lipo -archs "$dst") != *x86_64* ]]; then
    lipo -create "$dst" "$f" -output "$dst.fat"
    mv "$dst.fat" "$dst"
    (( ++fused ))
  fi
done
cd "$ROOT"
echo "fused $fused, copied $copied from intel"

# resign inside out so the payload keeps its own signatures
find "$U/Contents/Frameworks" "$U/Contents/Resources" -path '*/payload' -prune -o \
  -type f \( -name '*.so' -o -name '*.dylib' \) -print0 | xargs -0 codesign --force -s -
codesign --force -s - "$U"
codesign --verify --deep --strict "$U"
codesign --verify --deep --strict "$U/Contents/Resources/payload/Shell.app"
lipo -archs "$U/Contents/MacOS/$NAME"

ditto -c -k --keepParent "$U" "$OUT/MacOS-Unknown-$VER.zip"
du -sh "$U" "$OUT/MacOS-Unknown-$VER.zip"
