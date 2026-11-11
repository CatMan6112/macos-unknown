# third party source

the mod loader in the launcher has two LGPL-2.1 libraries that i had to change so they run native on apple silicon. this folder has the changes as patches against the upstream tags plus their licenses. the full changed source trees are also attached to every release that ships them.

## UnityDoorstop v4.4.1

upstream is https://github.com/NeighTools/UnityDoorstop at tag v4.4.1. plthook-fat-slice.patch makes plthook pick the slice for the cpu its running on. stock picks x86_64 out of a fat binary and crashes on arm64.

```sh
git clone https://github.com/NeighTools/UnityDoorstop && cd UnityDoorstop
git checkout v4.4.1 && git apply ../plthook-fat-slice.patch
clang -arch arm64 -arch x86_64 -shared -Os -fPIC -Wno-deprecated-declarations \
  -o libdoorstop.dylib src/*.c src/config/*.c src/nix/*.c src/nix/plthook/*.c src/util/*.c src/runtimes/*.c
```

## BepInEx 5.4.23.4

upstream is https://github.com/BepInEx/BepInEx at tag v5.4.23.4. macos-arm64.patch moves it to HarmonyX 2.16.1 and MonoMod 25 cause MonoMod 22 has no arm64. it also targets net452, adds a Platform/PlatformHelper shim for old plugins, opens libc with dlopen in UnixStreamHelper and drops the x86 only XTermFix detour.

HarmonyXInterop.dll isnt rebuilt. take it from the stock BepInEx_macos_x64_5.4.23.4.zip release (BepInEx/core) and put it in lib/ next to the repo before building.

```sh
git clone https://github.com/BepInEx/BepInEx && cd BepInEx
git checkout v5.4.23.4 && git apply ../macos-arm64.patch
dotnet build BepInEx.Preloader/BepInEx.Preloader.csproj -c Release
```

the release also ships System.ValueTuple.dll from the net47 folder of the System.ValueTuple 4.5.0 nuget package. the netstandard one fails to load.

HarmonyX, MonoMod and Mono.Cecil are MIT and ship unchanged.
