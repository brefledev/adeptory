# Record reference

Schema version 1 is defined in `core/model.py`. A specialist package uses the `Kit` record. Construction state and library records remain separate files linked to that package.

## Specialist package

| Record | Contents |
|---|---|
| `Kit` | Identity, goal, subject, version, scope, sources, claims, workflow, capabilities, input-field mappings, choices, rules, gaps, and adoption. |
| `SourceRecord` | URL, title, retrieval time and tool, excerpt, locator, quality, jurisdiction, date information, limitations, and receipt. |
| `Claim` | Claim text, supporting source IDs, support review, contradictions, and inference status. |
| `WorkflowStep` | Instruction, reason, required evidence, exceptions, priority, consequence, supporting claim IDs, and search terms. |
| `ToolCapability` | Readiness, purpose, inputs, outputs, access, setup, and verification. |
| `AdoptionRecord` | Status, origin, actor, time, package version, and recorded choices. |

Package revisions reopen adoption. Model proposals preserve a proposed state. The completed-build path derives ordinary-use authorization from the original request and its host-provided user identity. Unresolved business choices retain their unknown status until the person supplies the relevant fact.

`Observation` records an expiring lead with its subject, origin, evidence, and keywords. `CheckResult` records the declared rules considered for an operation and whether the host must request approval. Host authorization remains a separate decision.

## Construction plan

`build-plan.json` contains outcomes, knowledge requirements, questions, and tasks. The required task IDs are `discover`, `acquire`, `organize`, `configure`, and `demonstrate`. The Hermes adapter adds the native profile-delivery task.

Tasks have pending, running, blocked, or complete status. Completed tasks require typed evidence. Acquisition references a captured document. Organization references an authored entry with current source links. Configuration references an observed host operation. A completed demonstration records its input, actual result, independent expected result, comparison, and successful observed run.

The adapter binds host evidence to the current build and session through recorded receipt IDs. Required user questions use the host-returned answer to the prepared question. Conditional tasks retain the condition that controls their applicability.

## Library

Each specialist has a directory under the active profile's `library/`. The library retains its manifest, construction plan, source history, content-addressed captures, authored entries, navigation, and SQLite FTS5 index.

Documents carry their capture scope, authority, role, jurisdiction, dates, reuse terms, and limitations. Entries carry their content, applicability, exceptions, aliases, dependencies, gaps, and exact source-passage references.

Changing source or entry content revises the library fingerprint and specialist version. Repeating the same captured content preserves the existing version. Changed sources mark affected entries for review.

Search returns authored entries and captured-source leads. Results include source state and retrieval parameters for complete context. Lexical search weights entry titles and aliases. Large results provide explicit read parameters when automatic context inclusion would exceed its size limit.

## Portable core

`KitStore` saves, loads, lists, adopts, and exports specialist packages. `Builder` starts and revises packages, records sources, and evaluates readiness. `KnowledgeLibrary` stores and retrieves sources and authored entries. `BuildPlan` persists tasks and derives progress. `select_context` selects applicable adopted guidance. `NoteStore` manages expiring observations. `check_consequences` evaluates declared asset-removal rules.

The portable core uses Python's standard library. Hermes supplies profile configuration support through PyYAML in the adapter. The bundled [build skill](../skills/build/SKILL.md) contains the model-facing input contracts.
