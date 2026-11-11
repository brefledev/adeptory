# Hermes integration

Adeptory registers a Python plugin through `register(ctx)`. The portable `core/` modules contain specialist records, evidence checks, library storage, retrieval, and package operations. `adapter_hermes/` connects those operations to Hermes.

The manifest requires Hermes 0.23.1 or later. The implementation uses the host's plugin APIs described in the [Hermes plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).

## Registered tools

| Tool | Operations |
|---|---|
| `adeptory_build` | Start a specialist, persist its plan, inspect progress, prepare a profile distribution, refresh the installed plugin, prepare a blocking question, and check completion. |
| `adeptory_library` | Capture and read documents, author entries, search and read knowledge, inspect coverage, and resume a corpus import. |
| `adeptory_propose` | Create or revise a specialist package. |
| `adeptory_source` | Record a source excerpt and its retrieval metadata. |
| `adeptory_lookup` | Read specialist package records. |
| `adeptory_note` | Save an expiring observation with its evidence and origin. |
| `adeptory_check` | Check a proposed asset-removal operation against the specialist's declared rules. |

The `/adeptory` command opens the welcome message and supports specialist requests. The bundled `adeptory:build` skill describes research, source capture, authoring, configuration, demonstration, and delivery contracts.

## Hooks and middleware

| Registration | Purpose |
|---|---|
| `pre_llm_call` hook | Select the current specialist's applicable guidance or construction instructions. |
| `pre_tool_call` hook | Apply construction sequencing and declared consequence checks. |
| `post_tool_call` hook | Record tool observations and host-returned choices. |
| `on_session_end` hook | Preserve unfinished construction as paused. |
| `llm_request` middleware | Require tool use during an active build until completion and final task synchronization. |
| `tool_request` middleware | Project durable build tasks and prepared questions into native controls. |

Hermes controls the model, tool permissions, Stop, provider limits, and session routing. The middleware applies to the active build turn. A stopped build waits for an explicit resumption request.

## First-use reply permission

A command-submitted specialist request starts the host's normal agent turn through `ctx.inject_message`. Hermes gates this operation with the profile's `plugins.entries.adeptory.allow_gateway_injection` setting.

For a verified direct local command, Adeptory can ask for permission through `ctx.ask_choice`. If the user allows automatic replies, Adeptory runs the public Hermes CLI to save that setting for the current profile, then submits the saved request. Declining preserves the request and keeps automatic replies off.

## Generated profiles

The builder prepares a local Hermes profile distribution containing the specialist's instructions, package, library, and build-request authorization. The host installs that distribution through `hermes profile install`. The distribution preserves the builder's non-secret model and provider selection when present. Credentials remain under host management.

After installation, `refresh_profile` verifies that the target contains the expected generated specialist. It runs these public CLI operations for that target profile.

```text
hermes -p <profile> plugins disable adeptory
hermes -p <profile> plugins enable adeptory
```

The builder records both command results. Delivery also requires an observed native task in the installed profile. The finish check records that delivery evidence and ordinary-use authorization from the original request.

## Storage and external access

`plugin_data_dir("adeptory")` supplies profile-local storage for specialist packages, saved requests, construction state, observations, and receipts. The active profile's `library/` stores source captures and authored entries. Search uses SQLite FTS5.

Network retrieval, source extraction, terminal commands, and model calls use authorized Hermes tools and the configured provider. Exported packages contain their specialist knowledge and instructions. Saved command-request records stay in the builder profile.

Source text is evidence supplied to the model. Host permissions govern execution. Package content and consequence checks carry the scope described in [Record reference](interfaces.md).
