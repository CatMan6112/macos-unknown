#!/bin/zsh
# builds build/ShaderShell.app. its the shell with every non shader graph shader
# compiled for metal (list is in shell/shader-wanted.txt)
set -e
ROOT=${0:A:h:h}
mkdir -p "$ROOT/logs"
U=${UNITY:-/Applications/Unity/Hub/Editor/2022.3.62f3/Unity.app/Contents/MacOS/Unity}
"$U" -batchmode -nographics -projectPath "$ROOT/shell" \
  -executeMethod ShaderBuild.Build -logFile "$ROOT/logs/shaderbuild.log"
grep SHADERBUILD "$ROOT/logs/shaderbuild.log"
