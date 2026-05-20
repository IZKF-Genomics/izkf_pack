# ScType Annotation Config

`scrna_annotate_sctype` uses the ScType marker database as the primary marker source for human or
mouse cluster annotation.

The default primary catalog is:

```text
download:sctype
```

which downloads and converts:

```text
https://raw.githubusercontent.com/IanevskiAleksandr/sc-type/master/ScTypeDB_full.xlsx
```

For project-specific manual marker gene annotation, use the separate
`scrna_annotate_manual_markers` template. This ScType template intentionally only runs ScType-style
catalog scoring.
