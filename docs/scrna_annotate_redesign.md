# scrna_annotate redesign superseded

This document has been superseded by the provider-based `scrna_annotate` design.

Current design files:

- [scrna_annotate design notes](scrna_annotate.md)
- [Template README](../templates/scrna_annotate/README.md)
- [Template design document](../templates/scrna_annotate/DESIGN.md)

The previous tiered preview/refinement/formal annotation plan has been intentionally retired.
The current architecture separates:

- `scrna_annotate`: provider execution and standard JSON emission
- `scrna_audit`: provider comparison, visualization, consensus, and review reporting
