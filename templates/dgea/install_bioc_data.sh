#!/usr/bin/env bash
set -euo pipefail

ENV_DIR="$(pixi info --json | python -c 'import json,sys; data=json.load(sys.stdin); print(data["environments_info"][0]["prefix"])')"
export PREFIX="$ENV_DIR"
export PATH="$ENV_DIR/bin:$PATH"

stamp="${ENV_DIR}/.linkar_bioc_data_installed"
if [[ -f "${stamp}" ]]; then
  echo "Bioconductor data packages already installed for this Pixi environment."
  exit 0
fi

for p in genomeinfodbdata-1.2.13 org.mm.eg.db-3.20.0 org.hs.eg.db-3.20.0 org.ss.eg.db-3.20.0 go.db-3.20.0; do
  installBiocDataPackage.sh "$p"
done

touch "${stamp}"
