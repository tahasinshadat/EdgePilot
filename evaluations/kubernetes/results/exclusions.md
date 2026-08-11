# Excluded Pilot Runs

## Open-port setup run 1

- Provider: Claude
- Tool calls: 0
- Result: excluded from reliability statistics
- Reason: capability mismatch

The prompt requested namespace-scoped Kubernetes Service and port
inspection. The existing `inspect_kubernetes_cluster` tool accepts no
arguments and reports cluster capacity rather than Services or ports.

The response rendered a proposed tool call as text using unsupported
`namespace` and `resource_type` arguments. No tool call was executed.


## Claude capacity pilot run 1

- Endpoint: `POST /api/ask`
- HTTP status: 200
- Latency: 3.686529 seconds
- Prompt tokens: 1207
- Response tokens: 259
- Recorded tool calls: 0
- Result: excluded from Kubernetes reliability statistics
- Category: TOOL_CALL_NOT_EXECUTED

The prompt directly matched the zero-argument
`inspect_kubernetes_cluster` tool. Claude emitted XML-like function-call
markup twice, but EdgePilot returned it as plain answer text and recorded
zero tool calls. The response subsequently asked whether a Kubernetes
cluster was available, even though the test cluster was running.

This indicates a provider/endpoint tool-execution issue before Kubernetes
inspection and is not scored as Kubernetes reasoning accuracy.


### Root cause

`POST /api/ask` creates the provider and calls `generate()` without first
calling `enable_tools()` with the MCP tool schemas. Therefore, Claude is
not given structured tool definitions through this endpoint.

The streaming chat endpoint contains the complete tool-execution and
follow-up-response loop. The reliability evaluation will use
`POST /api/chats/{chat_id}/messages/stream`.


## Evaluation interface

Experiments use:

`POST /api/chats/{chat_id}/messages/stream`

A fresh chat is created for every independent run. This endpoint enables
the MCP tool schemas, executes structured tool calls, returns tool results
to the model, and records the final response.

`POST /api/ask` is not used because its provider instance is not configured
with tool schemas.