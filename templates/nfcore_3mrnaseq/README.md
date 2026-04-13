# nfcore_3mrnaseq

This template migrates the facility BPM wrapper for `nf-core/rnaseq` into a Linkar pack template.

It remains facility-specific:

- fixed nf-core pipeline revision: `3.22.2`
- fixed execution profile: `docker`
- fixed site genome paths in [nextflow.config](/home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq/nextflow.config)

## Linkar interface

Exposed parameters:

- `samplesheet`
- `genome`
- `agendo_id`
- `umi`
- `spikein`
- `max_cpus`
- `max_memory`

With `--binding default`, the pack can resolve:

- `samplesheet` from the latest `demultiplex` outputs in the active project
- `genome` from Agendo `organism`
- `umi` from Agendo `umi`
- `spikein` from Agendo `spike_in`
- `max_cpus` and `max_memory` from 80 percent of host capacity

## Runtime behavior

The template keeps the execution logic in a standalone [run.sh](/home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq/run.sh:1).

That script:

- validates `genome` before launch
- derives `effective_genome` from `spikein`
- records `software_versions.json`
- runs the fixed `nf-core/rnaseq` invocation
- cleans the named Nextflow work directory when possible

## Test commands

Direct local test:

```bash
cd /home/ckuo/github/izkf_pack/templates/nfcore_3mrnaseq
python3 test.py
```

Through Linkar:

```bash
cd /home/ckuo/github/linkar
pixi run linkar test nfcore_3mrnaseq --pack /home/ckuo/github/izkf_pack
```
