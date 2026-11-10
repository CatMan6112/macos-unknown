#!/bin/zsh
# builds build/SteamLib.app from steamlib/ (Steamworks.NET 2025.164.0 source)
# for the mac steamworks dll (small callback packing and DllImport steam_api) and
# steam_api.bundle. metalize.sh copies both into the port
set -e
ROOT=${0:A:h:h}
mkdir -p "$ROOT/logs"
U=${UNITY:-/Applications/Unity/Hub/Editor/2022.3.62f3/Unity.app/Contents/MacOS/Unity}
mkdir -p "$ROOT/logs"
"$U" -batchmode -nographics -buildTarget OSXUniversal -projectPath "$ROOT/steamlib" \
  -executeMethod SteamBuild.Build -logFile "$ROOT/logs/steamlib-build.log"
grep STEAMBUILD "$ROOT/logs/steamlib-build.log"
