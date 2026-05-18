#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'MESSAGE'
scrna_annotate is currently a design-only scaffold.

This template has been reset to document the planned provider-based
annotation architecture. Provider execution code has not been generated yet.

Read:
  README.md
  DESIGN.md
  schema/annotation_result.schema.json
  providers/README.md
MESSAGE

exit 2
