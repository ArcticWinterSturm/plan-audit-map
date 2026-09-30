# Skill: MCP stdio protocol — handshake, framing, EOF, proxies

## Framing: newline-delimited JSON-RPC 2.0, NOT LSP headers

MCP over stdio is one JSON object per line on both stdin and stdout.
There are NO `Content-Length` headers (that is LSP). A correct client
writes `{"jsonrpc":"2.0","id":1,"method":"…","params":{…}}\n` and reads
lines. A proxy between client and server must forward BYTES verbatim
and never write to the server-facing stdout — stdout belongs to the
protocol. Application logs go to stderr, always.

## The handshake, in order

1. Client → `initialize` with `params.protocolVersion` (e.g.
   "2024-11-05"), `capabilities`, `clientInfo` — WITH an `id`.
2. Server → response with `serverInfo` and its `capabilities`
   (tools, resources, prompts, completions, …).
3. Client → `notifications/initialized` — a NOTIFICATION (no id).
   Skipping it is the classic "tools/list hangs forever" bug: many
   servers will not answer other requests before it.
4. Then `tools/list` (id), `tools/call` (id), `prompts/list`, etc.

Tool call result shape:
`{"result":{"content":[{"type":"text","text":"…"}],"isError":false}}`.
The payload is the `text` field — often JSON-as-string that must be
parsed again. `isError: true` still arrives as a normal response.

## ids, notifications, and server-initiated requests

- Client request: has BOTH `id` and `method`. Server response: `id`,
  NO `method`, either `result` or `error`.
- Notifications (either direction): `method`, NO `id`, never answered.
- Server-to-client REQUESTS exist: `sampling/createMessage`,
  `roots/list`, `elicitation/createMessage` — `id` + `method` on the
  outbound stream. A tap or client that treats every id-bearing message
  as "a response to something" will corrupt its bookkeeping; classify
  by direction AND shape.

## EOF semantics and clean shutdown

Stdin closing means the client is gone. Per the spec the server SHOULD
exit; in practice a naive server never notices (no `end` handler on
stdin) and leaks a process per client — watch for orphaned `node …
dist/index.js` in the process list. There is NO LSP-style
`shutdown`/`exit` request pair in MCP; do not send one, just close the
pipe. A proxy MUST forward EOF by closing the child's stdin
(half-close) or the child idles forever. Health-check pattern for a
server: if it stops responding, first check whether its stdin is still
open and whether it ever saw EOF from a previous session.

## Other transports, briefly

- **SSE (legacy)**: server runs HTTP; `GET /sse` opens the event
  stream (first event `endpoint` carries the message URL), client
  `POST`s JSON-RPC to `/messages?sessionId=…`. plan-audit-map serves this
  with `--sse --host --port [--token]`; token via `?token=` or Bearer.
- **Streamable HTTP**: the newer single-endpoint POST model replacing
  SSE. Clients configured by URL pick this up automatically.
- A client that supports URL configs can use the SSE launcher scripts
  (`planauditmap_localhost.bat`, `--remote --tunnel …` for public URLs).

## Writing a tap/proxy: the five invariants

1. Read with `os.read(fd, N)` — buffered `read(N)` blocks until N bytes
   and deadlocks small-message protocols.
2. Forward bytes verbatim; inject nothing into the protocol streams.
3. On client EOF, close the child's stdin; then reap the child.
4. Classify messages by direction + shape (see ids section) before
   pairing on `id`.
5. All side-channel output (logging, IPC) to stderr or sockets — never
   stdout.

## Full worked session (byte-accurate skeleton)

```
→ {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"tap-test","version":"1.0"}}}
← {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{},"resources":{},"completions":{},"prompts":{}},"serverInfo":{"name":"plan-audit-map","version":"1.0.0"}}}
→ {"jsonrpc":"2.0","method":"notifications/initialized"}
→ {"jsonrpc":"2.0","id":2,"method":"tools/list"}
← {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"plan-audit-map","description":"…","inputSchema":{…}}]}}
→ {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"plan-audit-map","arguments":{"thought":"…","thought_number":1,"total_thoughts":3,"next_thought_needed":true}}}
← {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"{…server payload JSON…}"}],"isError":false}}
```
Then the client closes stdin; a compliant server exits within seconds
(exit 0). If your transcript shows tools/list BEFORE
notifications/initialized, that ordering is your hang, not the server.

## Server-initiated requests in a tap

A server may send `{"jsonrpc":"2.0","id":501,"method":"sampling/
createMessage","params":{…}}` — this is a REQUEST the CLIENT must
answer (id 501, result or error). A wire tap must (a) classify it
server-request, (b) NOT pair it with any client request despite having
an id, (c) forward it verbatim and let the client decide. Same for
`roots/list` pings. Dropping or mispairing these breaks clients that
use sampling (that is how some Qwen/Claude flows stall behind proxies).

## Version and capability notes

`protocolVersion` is echoed/negotiated in initialize ("2024-11-05" is
widely accepted). Server capabilities seen from plan-audit-map: tools,
resources, prompts, completions. SDK line 1.11 → 1.26+ moved several
fixes (SSE transport hardening, completions); the overlay pins
`@modelcontextprotocol/sdk ^1.26.0`. If a client rejects the server
over protocol version, bump the SDK before blaming the client — the
server advertises what the SDK supports.
