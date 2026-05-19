# Built-in Zebrafish Catalogs

These catalogs are bundled so `scrna_annotate_zebrafish` can run without a project-local catalog.

Available ids:

```text
builtin:zebrafish_core
```

Important: these are starter catalogs for workflow testing and broad review. They are not a
substitute for a project-specific curated catalog with tissue/stage-appropriate citations.

To make a project catalog:

```bash
cp config/default_catalogs/zebrafish_core.tsv config/marker_catalog.tsv
```

Then edit `config/marker_catalog.tsv` and run with:

```bash
MARKER_CATALOG=config/marker_catalog.tsv ./run.sh
```
