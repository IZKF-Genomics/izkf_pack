# Feature Barcode catalogs

These files are versioned snapshots used to compile a Cell Ranger Feature Reference without network access at analysis time. They are broad vendor catalogs, not proof that every listed reagent was used in an experiment.

The checked-in snapshots cover BioLegend TotalSeq-A, -B, and -C antibody and hashing products for human and mouse. They are sourced from BioLegend's public TotalSeq barcode lookup and use the vendor-provided Cell Ranger identifiers, barcode sequences, and read layouts. Hashing snapshots use `Antibody Capture`, as required by Cell Ranger 9 and later for antibody hashing. `Multiplexing Capture` is reserved for 10x CellPlex/CMO libraries.

Validate the experimental panel whenever possible. An unused catalog barcode usually has no counts, but large superset references can introduce ambiguous one-mismatch correction, misleading low background rows, or incorrect annotations if a sequence is assigned to the wrong product.

To refresh a snapshot deliberately:

```bash
python3 scripts/update_biolegend_catalog.py \
  --family C \
  --species Mouse \
  --output catalogs/biolegend_totalseq_c_mouse.tsv
```

Review the diff, update `manifest.tsv` and its retrieval date, run `python3 test.py`, and commit the snapshot. Rendering and analysis never update catalogs automatically.
