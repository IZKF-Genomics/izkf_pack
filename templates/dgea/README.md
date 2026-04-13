# dgea

This template provides a clean DGEA workspace for Linkar projects.

It keeps the analyst-facing workflow in R/Quarto:

- editable [DGEA_constructor.R](/home/ckuo/github/izkf_pack/templates/dgea/DGEA_constructor.R)
- bundled Quarto reports
- bundled [pixi.toml](/home/ckuo/github/izkf_pack/templates/dgea/pixi.toml) and [pixi.lock](/home/ckuo/github/izkf_pack/templates/dgea/pixi.lock)
- bundled Positron settings in [.vscode/settings.json](/home/ckuo/github/izkf_pack/templates/dgea/.vscode/settings.json)

Instead of BPM Jinja rendering, Linkar now writes a small `dgea_inputs.R` file through [build_dgea_inputs.py](/home/ckuo/github/izkf_pack/templates/dgea/build_dgea_inputs.py). The constructor stays editable and programmable.

## Runtime model

`linkar render dgea`:

- stages an editable analyst workspace
- does not execute the analysis

`linkar run dgea`:

- runs the standalone [run.sh](/home/ckuo/github/izkf_pack/templates/dgea/run.sh:1)
- writes `dgea_inputs.R`
- installs the Pixi environment
- runs `install_bioc_data.sh`
- executes `DGEA_constructor.R`
- records `software_versions.json`

## Bindings

With `--binding default`, the pack resolves:

- `salmon_dir` from the latest upstream nf-core outputs
- `samplesheet` from the latest upstream nf-core params
- `organism` from upstream genome or organism
- `application` from the latest upstream template id
- `name` from the project name
- `authors` from project author metadata

## Editing

The main control surface is [DGEA_constructor.R](/home/ckuo/github/izkf_pack/templates/dgea/DGEA_constructor.R).

The rendered constructor:

- always renders the all-samples overview
- auto-creates one comparison only if exactly two groups are present
- otherwise expects you to edit the `comparisons` list manually

That keeps the workflow flexible for:

- many pairwise comparisons
- selective sample exclusion
- relabeling groups
- changing design formulas
- enabling or disabling optional reports

## Test commands

```bash
cd /home/ckuo/github/izkf_pack/templates/dgea
python3 test.py
```
