# SciAgent Module Registry

Each SciAgent architectural module is represented by a machine-readable
`module.yaml` passport.

The registry is the source of truth for the Architecture Workbench.

Each module will describe:

- identity and architectural layer
- purpose
- status
- input and output contracts
- dependencies
- implementation location
- models/providers
- fixtures and gold datasets
- acceptance metrics
- known issues

The Architecture Workbench must render its graph from these module passports
instead of maintaining a separate manually drawn architecture.
