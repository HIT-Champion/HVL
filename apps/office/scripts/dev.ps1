# Copyright 2026 Signet Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

param([int]$Port = 3000)

$ErrorActionPreference = 'Stop'
$officeRoot = Split-Path -Parent $PSScriptRoot
$systemNode = Get-Command node -ErrorAction SilentlyContinue
$bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$candidates = @($systemNode.Source, $bundledNode) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$nodeBinary = $null
foreach ($candidate in $candidates) {
    $version = & $candidate --version
    if ([version]($version.TrimStart('v')) -ge [version]'24.0.0') {
        $nodeBinary = $candidate
        break
    }
}
if (-not $nodeBinary) {
    throw 'Can Node.js 24+. Cai Node.js 24, mo lai terminal roi chay lai script.'
}

$previousPath = $env:Path
Push-Location -LiteralPath $officeRoot
try {
    # Chi thay PATH trong tien trinh nay de npm va Nuxt dung cung Node.
    $env:Path = (Split-Path -Parent $nodeBinary) + [IO.Path]::PathSeparator + $previousPath
    if (-not (Test-Path -LiteralPath 'node_modules/nuxt/bin/nuxt.mjs')) {
        $npmCommand = Get-Command npm.cmd -ErrorAction Stop
        $npmCli = Join-Path (Split-Path -Parent $npmCommand.Source) 'node_modules/npm/bin/npm-cli.js'
        if (-not (Test-Path -LiteralPath $npmCli)) { throw 'Khong tim thay npm CLI. Cai Node.js 24 kem npm.' }
        & $nodeBinary $npmCli ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'npm ci that bai.' }
    }
    Write-Host "Node: $(& $nodeBinary --version)"
    Write-Host "FE preview: http://localhost:$Port/__fe"
    & $nodeBinary node_modules/nuxt/bin/nuxt.mjs dev --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Nuxt dev that bai.' }
} finally {
    $env:Path = $previousPath
    Pop-Location
}
