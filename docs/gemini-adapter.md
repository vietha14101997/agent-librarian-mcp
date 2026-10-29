# Gemini adapter boundary

Version 0.3.0 implements four source-derived parsing operations against an injected
AuthenticatedReadTransport and AccountCapability. MockGeminiTransport remains the default. A restricted GeminiHTTPS implementation
and session manager are now supplied behind protected-runtime gates; they have
only synthetic HTTP verification. Protected initial login capture is pending review. `mcp-serve --provider google` refuses startup. The ordinary synthetic service command supports only
fake and gemini-mock; protected provider-runtime construction can select HTTPS. Mock success does not prove Google compatibility.

| Method | Reviewed protocol detail |
|---|---|
| list_notebooks | RPC wXbhsf, known notebook row layout |
| get_notebook | RPC rLM1Ne, wrapped notebook metadata |
| query | GenerateFreeFormStreamed path, byte-counted wrb.fr stream, answer/citation layout |
| get_source | RPC hizoJc, source metadata and indexed text blocks |

The adapter checks injected account identity before sending requests, notebook
and source allowlists, query length/destination patterns, response byte/depth/node
bounds and returned identities. Injection is trusted service code, not an MCP
argument. AccountCapability is a binding declaration, not live account attestation.
No arbitrary RPC method or HTTP path is accepted from the agent.

Known upstream layouts are parsed narrowly. Missing citations yield an empty
list. Thinking-only and unknown layouts return UNIMPLEMENTED_SOURCE_GAP rather
than a fabricated answer. Citation numbers/source IDs and known text segments are
preserved. Table citations and unreviewed response variants remain unsupported.
Provider protocol errors and expired authentication have safe codes. No raw
response logging or authenticated HTML dump exists.

Gateway results identify the notebook/source, title where available, answer and
citation references. They explicitly report SOURCE_NOT_VERIFIED: a citation is
an association, not proof of semantic support or exact revision. Text is untrusted
data and cannot become instructions or tool calls. Querying may persist Notebook
conversation history in an eventual live deployment.

No administrative operations, source registration/deletion/Drive sync, notebook
sharing/deletion, account switching, generic APIs or shell execution are exposed.
The adapter reads no environment, browser state, cookie database, Keychain or
upstream profile. See THIRD_PARTY_NOTICES.md for exact pinned source attribution
and modifications. Wire envelopes and lifecycle are now implemented and mock-tested. Actual host
isolation, Keychain access, protected login capture, live account identity and
Google compatibility remain acceptance gates. See transport-security.md and session-auth.md.
