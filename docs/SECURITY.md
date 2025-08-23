# Security Policy

- No telemetry: local-only logs
- No memory injection: input simulated via OS APIs only
- Logs redact PII; artifacts are local and user-owned
- Secrets are never committed; runtime configs live under %APPDATA%/Gangware. Sample configs at docs/examples/

## Reporting a Vulnerability
Please open a confidential issue or contact maintainers directly with reproduction steps.
