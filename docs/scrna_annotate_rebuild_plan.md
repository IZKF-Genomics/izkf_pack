# scrna_annotate rebuild plan superseded

This plan has been superseded by the provider-based annotation architecture.

The next implementation should not rebuild the old tiered workflow. It should follow:

- [scrna_annotate design notes](scrna_annotate.md)
- [Template design document](../templates/scrna_annotate/DESIGN.md)
- [Provider manifests](../templates/scrna_annotate/providers/README.md)
- [Annotation result schema](../templates/scrna_annotate/schema/annotation_result.schema.json)

Recommended new milestone order:

1. dataset profiler
2. provider manifest reader
3. JSON schema validation
4. `mock_provider`
5. `marker_based`
6. `provider_index.json`
7. first `scrna_audit` reader/report
