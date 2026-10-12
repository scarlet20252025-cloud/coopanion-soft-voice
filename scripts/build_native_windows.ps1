param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Toolchain,
    [Parameter(Mandatory=$true)][string]$CMake,
    [Parameter(Mandatory=$true)][string]$NinjaDirectory,
    [Parameter(Mandatory=$true)][string]$VulkanHeaders,
    [Parameter(Mandatory=$true)][string]$VulkanLibrary,
    [Parameter(Mandatory=$true)][string]$Glslc,
    [Parameter(Mandatory=$true)][string]$SpirvPrefix
)
$ErrorActionPreference = 'Stop'
$revision = git -C $Source rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $revision -ne '51512f129a7419567f4b8abfb06801451789b8f1') {
    throw 'Check out the pinned qwentts.cpp revision before building.'
}
$ggmlRevision = git -C (Join-Path $Source 'ggml') rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $ggmlRevision -ne '2eddaf94a8cdbbf1c30017d28313cd661a9da543') {
    throw 'Initialize the pinned ggml submodule before building.'
}
$patch = Join-Path $PSScriptRoot '../evidence/2026-10-12-native/qwentts-experiment.patch'
$ErrorActionPreference = 'Continue'
git -C $Source apply --reverse --check $patch 2>$null
$alreadyPatched = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Stop'
if (-not $alreadyPatched) {
    git -C $Source apply --check $patch
    if ($LASTEXITCODE -ne 0) { throw 'Source does not match the experiment patch.' }
    git -C $Source apply $patch
    if ($LASTEXITCODE -ne 0) { throw 'Cannot apply native experiment patch.' }
}
$oldPath = $env:Path
$oldCC = $env:CC
$oldCXX = $env:CXX
try {
    $env:Path = "$Toolchain;$NinjaDirectory;$oldPath"
    $env:CC = 'x86_64-w64-mingw32-clang.exe'
    $env:CXX = 'x86_64-w64-mingw32-clang++.exe'
    $build = Join-Path $Source 'build-vulkan'
    & $CMake -S $Source -B $build -G Ninja `
        "-DCMAKE_MAKE_PROGRAM=$NinjaDirectory/ninja.exe" `
        "-DCMAKE_C_COMPILER=$Toolchain/x86_64-w64-mingw32-clang.exe" `
        "-DCMAKE_CXX_COMPILER=$Toolchain/x86_64-w64-mingw32-clang++.exe" `
        -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=OFF -DGGML_VULKAN=ON -DGGML_BLAS=OFF `
        -DGGML_OPENMP=OFF -DGGML_NATIVE=ON -DQWEN_SHARED=ON `
        "-DVulkan_INCLUDE_DIR=$VulkanHeaders" "-DVulkan_LIBRARY=$VulkanLibrary" `
        "-DVulkan_GLSLC_EXECUTABLE=$Glslc" "-DCMAKE_PREFIX_PATH=$SpirvPrefix" `
        "-DCMAKE_CXX_FLAGS=-I`"$SpirvPrefix/include`""
    if ($LASTEXITCODE -ne 0) { throw 'Native configure failed.' }
    & $CMake --build $build --target qwen -j4
    if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }
    Get-FileHash (Join-Path $build 'libqwen.dll') -Algorithm SHA256
} finally {
    $env:Path = $oldPath
    $env:CC = $oldCC
    $env:CXX = $oldCXX
}
