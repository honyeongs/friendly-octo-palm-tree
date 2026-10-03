# Cloud source snapshot

This repository contains the original workspace sources, the standalone delivery
game `index.html`, documentation, screenshots, tests, and dependency lockfile.
The frontend/backend/shared application is retained alongside the delivery game.

The migration branch is `codex/cloud-migration-20261003`. It is based on the
existing remote `main` commit, preserving that repository's history. The local
workspace had no ordinary commits at migration time; its existing Git objects and
Codex snapshot refs remain untouched locally.

## Exclusions

Local environment files, private keys, credential files, personal runtime data,
`node_modules`, `dist`, `.tools`, `.parcel-build`, coverage and logs are not
uploaded. Non-secret `.env.example` templates and `package-lock.json` are retained.
Nothing was deleted from the original workspace.

`index.html` is intentionally included as the playable standalone deliverable,
not treated as a disposable cache. It embeds its runtime and requires no build
to play. No deployment or GitHub Pages publication is configured by this migration.

## Rebuilding the standalone delivery game

The excluded `.parcel-build` directory contains a downloaded, unmodified Three.js
0.169.0 package, which can be recreated. Use Node.js 22.12 or newer and npm.
From the repository root, on a shell with `tar` available:

```sh
npm ci
mkdir -p .parcel-build
npm pack three@0.169.0 --pack-destination .parcel-build
tar -xzf .parcel-build/three-0.169.0.tgz -C .parcel-build
node parcel/build.mjs
```

On PowerShell, replace `mkdir -p .parcel-build` with
`New-Item -ItemType Directory -Path .parcel-build -Force`.
The lockfile's Vite dependency includes esbuild used by `parcel/build.mjs`.
The source files `parcel/game.html`, `parcel/runtime-entry.js` and
`parcel/build.mjs` are preserved without modification by this migration.

For the separate frontend/backend/shared application, consult `README.md` and
the workspace scripts in `package.json`. Supply real environment variables
locally or through your cloud platform's secret manager, never through Git.
