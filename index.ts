#!/usr/bin/env node

import { parseArgs } from 'node:util';

/**
 * Map. Think. Do. MCP Server entry point
 *
 * This is the entry point for the Map. Think. Do. MCP server, which uses sequential thinking
 * methodology to help solve programming problems step by step. It delegates to the main
 * server implementation in src/server.ts after parsing command line arguments.
 *
 * Note: The server now advertises the "plan-audit-map" tool name and still accepts the
 * legacy "code-reasoning" alias for existing clients.
 */

// Parse command line arguments
const { values } = parseArgs({
  options: {
    debug: { type: 'boolean', default: false },
    help: { type: 'boolean', short: 'h', default: false },
    sse: { type: 'boolean', default: false },
    host: { type: 'string', default: '127.0.0.1' },
    port: { type: 'string', default: '8002' },
    token: { type: 'string' },
    'token-file': { type: 'string' },
    local: { type: 'boolean', default: false },
    remote: { type: 'boolean', default: false },
    tunnel: { type: 'string', default: 'ngrok' },
    ngrok: { type: 'string' },
    'ngrok-authtoken': { type: 'string' },
    'ngrok-api': { type: 'string', default: 'http://127.0.0.1:4040' },
    'ngrok-region': { type: 'string' },
    'ngrok-domain': { type: 'string' },
    'cors-origin': { type: 'string' },
    'no-dashboard': { type: 'boolean', default: false },
    'max-connections': { type: 'string', default: '50' },
    quiet: { type: 'boolean', default: false },
    'tls-cert': { type: 'string' },
    'tls-key': { type: 'string' },
  },
});

if (values.help) {
  console.info(`plan-audit-map
 
Usage:
  plan-audit-map [--sse] [--host <host>] [--port <port>] [--token <token>] [--local] [--remote] [--tunnel <tunnel>] [--debug] [--help]

Options:
  --sse              Run an HTTP/SSE MCP server instead of stdio
  --host             Host/interface for SSE mode (default: 127.0.0.1)
  --port             Port for SSE mode (default: 8002)
  --token            Optional token required on GET /sse via ?token= or Bearer auth
  --token-file       Read token from file (more secure than CLI arg)
  --local            Resolve and bind to the local LAN IP (e.g. 192.168.x.x)
  --remote           Run in secure remote mode over SSE tunnel
  --tunnel           Tunnel provider: ngrok, pinggy, localtunnel, localhostrun, serveo (default: ngrok)
  --cors-origin      Restrict CORS to specific origin (default: *)
  --no-dashboard     Disable the web dashboard at /
  --max-connections  Max concurrent SSE connections (default: 50)
  --quiet            Suppress banner output
  --tls-cert         Path to TLS certificate (enables HTTPS)
  --tls-key          Path to TLS private key
  --debug            Enable verbose logging
  --help             Show this help text
`);
  process.exit(0);
}

// Import and run the server
import('./src/server.js')
  .then(module => {
    // Debug flag is passed to runServer
    if (values.debug) {
      console.error('Starting server in debug mode');
    }

    module.runServer(values.debug, values);
  })
  .catch(error => {
    console.error('Error starting server:', error);
    process.exit(1);
  });
