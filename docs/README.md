# Janus Edge Documentation

This folder contains the long-form project documentation for the repository.

## Documentation Map

- [Getting Started](./getting-started.md)
  Local setup options, Docker Compose usage, mixed local plus Docker workflow, update steps for existing clones, and service URLs.
- [Usage Guide](./usage.md)
  A non-technical walkthrough of every main section of the app and the most common daily workflows.
- [Architecture Overview](./architecture/architecture.md)
  High-level system structure, runtime topology, core data flows, and the full system-level diagram set.
- [Backend Architecture](./architecture/backend.md)
  Flask app structure, startup flow, modules, configuration behavior, backend workflow, and the full backend diagram set.
- [Frontend Architecture](./architecture/frontend.md)
  Vite and React app structure, routing, API integration, frontend workflow, and the full frontend diagram set.
- [Database Architecture](./architecture/database.md)
  MongoDB collections, major document shapes, relationships, indexes, backup and restore implications, and the full database diagram set.
- [API Reference](./api.md)
  HTTP endpoints exposed by the Flask backend, including auth requirements, request shapes, and inferred responses.
- [Configuration](./configuration.md)
  Environment files, backend and frontend configuration variables, and development versus production notes.
- [Deployment](./deployment.md)
  What is supported today based on the repository, and what is still not defined in code or infrastructure files.
- [Troubleshooting](./troubleshooting.md)
  Common local setup failures and concrete recovery steps.