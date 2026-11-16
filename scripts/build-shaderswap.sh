#!/bin/zsh
# compiles shaderswap/ShaderSwap.cs into patcher/payload/ShaderSwap.dll, the
# BepInEx plugin the launcher drops in with the mod loader. needs mono (mcs)
# and the BepInEx rebuild in build/modloader
set -e
ROOT=${0:A:h:h}
M=$ROOT/patcher/payload/Shell.app/Contents/Resources/Data/Managed
B=$ROOT/build/modloader/BepInEx/core
mcs -target:library -nostdlib -noconfig -optimize+ -langversion:7 \
  -r:$M/mscorlib.dll -r:$M/netstandard.dll -r:$M/System.dll -r:$M/System.Core.dll \
  -r:$M/UnityEngine.dll -r:$M/UnityEngine.CoreModule.dll -r:$M/UnityEngine.AssetBundleModule.dll \
  -r:$B/BepInEx.dll -r:$B/0Harmony.dll \
  -out:$ROOT/patcher/payload/ShaderSwap.dll $ROOT/shaderswap/ShaderSwap.cs
echo built $ROOT/patcher/payload/ShaderSwap.dll
