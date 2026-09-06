#!/usr/bin/env bash
# Build the installable extension zip: alugen-<version>.zip in dist/
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' alugen/blender_manifest.toml)
mkdir -p dist
rm -f "dist/alugen-${VERSION}.zip"
(cd alugen && zip -q -r "../dist/alugen-${VERSION}.zip" blender_manifest.toml ./*.py -x '__pycache__/*')
echo "dist/alugen-${VERSION}.zip"
