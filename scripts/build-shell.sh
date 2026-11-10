#!/bin/zsh
# builds the empty URP 2D mac player (build/Shell.app) from shell/
set -e
ROOT=${0:A:h:h}
mkdir -p "$ROOT/logs"
U=${UNITY:-/Applications/Unity/Hub/Editor/2022.3.62f3/Unity.app/Contents/MacOS/Unity}
mkdir -p "$ROOT/logs"
"$U" -batchmode -nographics -projectPath "$ROOT/shell" \
  -executeMethod ShellBuild.Build -logFile "$ROOT/logs/build.log"
grep SHELLBUILD "$ROOT/logs/build.log"
