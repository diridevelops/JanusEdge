# Security Policy

## Reporting A Vulnerability

Do not open public GitHub issues or pull requests for suspected security vulnerabilities.

Use GitHub Private Vulnerability Reporting if it is enabled for the repository. If it is not enabled yet, contact the maintainer privately before sharing details publicly.

Please include:

- the affected area or endpoint
- reproduction steps or a proof of concept
- impact assessment
- any relevant logs, screenshots, or request samples

The goal is to acknowledge reports within 5 business days and provide status updates as triage and remediation progress.

## Scope

Examples of in-scope reports include:

- authentication or authorization bypass
- JWT handling weaknesses
- insecure file upload or object storage access
- data exposure across user boundaries
- injection flaws or dependency-based remote code execution

Examples that are usually out of scope unless they enable a broader exploit include:

- missing rate limits on local development endpoints
- attacks that require control of the host running the application
- issues caused only by intentionally insecure local development defaults that were not changed by the deployer

## Disclosure Process

Janus Edge follows coordinated disclosure. Please allow time for triage, patching, verification, and release preparation before public disclosure.

If a report is confirmed, the maintainers should:

1. reproduce and scope the issue
2. prepare and verify a fix privately
3. publish the remediation guidance and upgrade path
4. disclose enough detail for users to assess impact after fixes are available

## Hardening Expectations

Public deployments should, at minimum:

- run behind HTTPS
- use unique secrets for Flask, JWT, and object storage
- restrict CORS to trusted origins
- protect MongoDB and MinIO with authentication and network controls
- keep dependencies current and review security advisories regularly