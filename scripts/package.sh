#!/usr/bin/env bash
# Build out/Ubermoc-Warcraft-Mod-Updater.zip in the layout Decky expects.
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="Ubermoc Warcraft Mod Updater"
ZIP="Ubermoc-Warcraft-Mod-Updater.zip"

pnpm install --frozen-lockfile
pnpm run build

rm -rf out
mkdir -p "out/$NAME/dist"
cp dist/index.js "out/$NAME/dist/"
cp -r py_modules "out/$NAME/"
cp main.py plugin.json package.json catalog.json LICENSE README.md "out/$NAME/"
find "out/$NAME" -name __pycache__ -type d -prune -exec rm -rf {} +

(cd out && python3 -c "
import os, sys, zipfile
name, target = sys.argv[1:]
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
    for folder, _, files in os.walk(name):
        for file in files:
            z.write(os.path.join(folder, file))
" "$NAME" "$ZIP")
ls -la out
