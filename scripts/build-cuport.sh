#!/bin/zsh
# compiles cuport/CUPort.cs into patcher/payload/CUPort.dll against the mac
# players own class libs. needs mono (mcs) and players never run this
set -e
ROOT=${0:A:h:h}
M=$ROOT/patcher/payload/Shell.app/Contents/Resources/Data/Managed
mcs -target:library -nostdlib -noconfig -optimize+ -langversion:7 \
  -r:$M/mscorlib.dll -r:$M/netstandard.dll -r:$M/System.dll -r:$M/UnityEngine.CoreModule.dll -r:$M/UnityEngine.InputLegacyModule.dll \
  -out:$ROOT/patcher/payload/CUPort.dll $ROOT/cuport/CUPort.cs
echo built $ROOT/patcher/payload/CUPort.dll
