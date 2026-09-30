# Test Notes

This directory contains the test sources used by `plan-audit-map`.

## Main Entry Points

- `unit-test-runner.ts`: runs the TypeScript unit suites compiled into `dist/test`.
- `plan-audit-map.e2e.ts`: stdio end-to-end runner for the MCP server.
- `mcp-compliance.test.js`: protocol-level smoke checks.
- `transport-failure.test.js`: transport and disconnect handling checks.
- `prompt-evaluation/`: optional prompt-evaluation tooling.

## Typical Workflow

```bash
npm run build
npm test
node test/mcp-compliance.test.js
node test/transport-failure.test.js
```

## Notes

- The e2e runner writes logs to `logs/` and structured results to `test-results/`.
- The JavaScript protocol and transport scripts run directly from `test/`; they are not compiled into `dist/`.
- Debug mode increases verbosity but still keeps request-content redaction enabled.
