---
name: build
description: Build a useful professional specialist from an ordinary request. Proactively discover authorities, textbooks and technical references; acquire and organize its own profile library; construct procedures and tool setup; demonstrate useful work.
---

# Build a specialist that can do useful work

## Begin work from the user's goal

The user can know nothing about the profession. Infer an initial scope from their goal and available context. Resume the saved construction already bound to this conversation. For a new conversation and creation request, call `adeptory_build` with `operation: start`, goal, subject and known scope. Use existing references as research leads; reuse an earlier specialist when the user asks to resume it. Begin research immediately. Ask a focused question when an unresolved fact changes applicability or a consequential action. Continue independent research while that question is pending.

Set `scope.delivery` to `profile` for a separate installed specialist. This is the default. Use `current-chat` only when the user explicitly requests a specialist confined to the current chat.

Explain the build in ordinary language. Keep internal identifiers, schemas and diagnostic history in tool records. The initial job is to discover and construct the specialist's knowledge and capabilities. The user supplies their circumstances and decisions; the builder supplies research, organization and implementation. Asking the user to identify statutes, textbooks, professional methods or every useful tool transfers the builder's work to them.

Complete the working specialist from this request in the current turn. Acquisition is one construction phase. Continue through supported claims and procedures, observed working capabilities, an independent representative demonstration, and native profile installation/verification. Finish with `adeptory_build` operation `finish`; its checks establish completion. A collection of documents or a first foundation module leaves the remaining construction work active.

Immediately call the host's `todo_list` tool with the `native_tasks` returned by the build tool. This opens Hermes's native Tasks panel. Update it after each persisted phase change. It displays actual saved progress. The build controller requires tools until `finish` succeeds and the completed Tasks list is displayed; Hermes still controls Stop, interruption and provider limits.

Research facts already available in the supplied context before asking the user. Record unknown applicability as `conditional: true` with a concrete `condition` on the affected requirement/task, and keep its procedures conditional. Continue every independent task. A required human question can pause work only when the saved plan identifies it as a genuine blocker and independent work is exhausted. Prepare it with `adeptory_build` operation `question`, then invoke the returned native `clarify` call. The host records the person's answer. An absent answer preserves the saved build for resumption.

## Persist a concrete construction plan

Call `adeptory_build` with `operation: plan`, kit_id and data containing:

- `outcomes`: objects with id, description and acceptance evidence expected from useful work.
- `requirements`: objects with id, purpose, applicable scope, source roles, discovery queries, document_ids and unresolved gaps. An excluded requirement records exclusion_reason. An empty list of documents remains an acquisition gap.
- `questions`: objects with id, question, why it matters, dependent task and resolution. Ask only what the user must decide or establish.
- `tasks`: objects with id, description, status (pending/running/blocked/complete), blocked_by and evidence. Completion requires supporting evidence. Describe blocked work precisely and keep independent work moving.

Task evidence objects use `{"kind":"document","id":"captured-document-id"}`, `{"kind":"entry","id":"existing-entry-id"}`, or `{"kind":"host-receipt","tool":"actual-tool","result":"observed-result","observed_at":"ISO-timestamp"}`. Document and entry IDs must exist in this specialist's library. For adapter host-receipts, also provide `receipt_id` from the `observed_tools` returned by `adeptory_build progress`. The adapter captures actual host tool results for this build and verifies receipt ownership. Call progress after a tool operation when you need its receipt ID. Host observations retain their stated scope.

A completed demonstration needs evidence with `kind: demonstration`, `input`, `input_provenance`, `actual_result`, `expected_result`, `expected_provenance`, `comparison`, `independent: true`, `passed: true`, and `actual_receipt_id` identifying the observed tool run. Establish the expected result from an independent specification, authoritative worked example or other appropriate evidence. Compare the actual result with that expectation; record failures and repair them before marking the phase complete. A model declaration or document count supplies no demonstration.

The required phase IDs are `discover`, `acquire`, `organize`, `configure`, and `demonstrate`. Give them concrete descriptions for this specialist. Add useful subtasks while retaining the required phases. Hermes adds a delivery task for native profile installation. Source acquisition needs captured document evidence; organization needs a source-linked authored entry; configuration needs an actual observed tool receipt. The adapter protects the installation task and completes it after native verification. Use `operation: progress` to resume from durable state after interruption. Record counts separately for discovered sources, acquired sources, authored resources, checked support, implemented tools and successful task results. A directory of skeleton entries supplies inventory coverage only.

## Discover the field's actual foundations

Research governing authority and professional instructional material proactively using authorized host search/fetch tools. Prefer the installed search, fetch, reader and extraction tools for an ordinary set of sources. Reuse cached captures. Introduce a collection script only when the volume or file format warrants it; use available dependencies and bounded, paced retrieval. Follow primary references and relevant definitions, FAQs, exceptions and dependencies until the procedure is usable. Source quantity alone supplies no completeness verdict.

For a location-specific accounting request, begin with applicable federal/state/local law, administrative rules, official tax instructions and forms, plus suitable accounting textbooks and worked exercises. Determine relevant jurisdiction, entity treatment, period and activities from available facts. Research the applicable county and municipality as well as the state. Mark conditional applicability while facts remain unresolved. These are research directions; verify each actual provision and its dates before giving a legal conclusion.

For an SEO specialist, discover search-engine documentation, web standards, tool detection contracts and relevant professional references. A vendor priority describes that vendor's default triage. Explain the evidence and site circumstances that change action. A vague instruction to follow best practices leaves an unresolved research task: find the specific recommendation, its authority, rationale, conditions and exceptions.

For every field, assess the actual source's authority, quality, scope, version, reuse terms and currency. Distinguish binding requirements, vendor behavior, instructional explanation and authored judgment. Preserve disagreement. A textbook's pedagogical explanation and a statute's operative text serve different purposes.

## Acquire material into this profile's library

The library is owned by the current Hermes profile at `library/<specialist-id>/`. Source originals, references, procedures, examples, navigation and search belong to that profile. Another profile's research remains separate until an authorized export/import transfers it.

Use host retrieval tools for network and document extraction. Keep one paced, cached queue per host during bulk acquisition. Respect robots, publisher conditions, Retry-After and host restrictions. Reuse successful downloads, deduplicate links and fragments, back off on transient failure, and stop affected-host requests on persistent blocking. Parallel workers can author cached material while one collector owns requests. Record actual HTTP response/time and acquisition failures; pacing supplies no guarantee against blocking.

Capture a source with `adeptory_library`, operation `document`, kit_id and data:

```json
{
  "id": "source-id",
  "url": "https://publisher.example/actual-source",
  "title": "Actual source title",
  "role": "instructional",
  "authority": "Observed publisher and the scope of its authority",
  "text": "Actual extracted source text, preserving operative wording",
  "retrieved_at": "2026-11-11T00:00:00Z",
  "retrieval_tool": "actual authorized host tool",
  "published_at": null,
  "effective_from": null,
  "effective_until": null,
  "review_after": null,
  "jurisdiction": null,
  "license": null,
  "limitations": ["Specific observed source limits"],
  "receipt": {}
}
```

Roles are governing, instructional, technical, reference, worked-example or user. Dates are ISO dates/timestamps or null when unknown. Retrieval date and effective date retain separate meanings. Establish source-specific review triggers, including amendments, new editions, vendor releases and dated work; record them in limitations and the maintenance tasks. Before consequential reliance, recheck sources whose dates, applicability or amendments remain unresolved.

Record `capture_scope` (full document, selected sections, excerpt or unknown), `authority_type` (such as statute, regulation, agency guidance, technical standard, vendor documentation or textbook), and the observed `normative_force`. These remain unknown/unverified until assessed. An agency explanation and an operative statute require distinct classification. Record the section locator and omitted dependencies for partial captures. A content hash verifies the captured text's integrity; completeness and legal force require their own evidence.

For large text, the authorized host can save a UTF-8 extraction under this profile's `library/imports/`; supply its relative `import_path` in place of text. Keep page/section identifiers and raw-file provenance in the receipt. The import boundary accepts files inside that directory. The tool preserves content-addressed originals and history. `document_read` takes document_id, offset and chars (up to 20000), returning an explicit window and total length. Read surrounding definitions and exceptions when a window depends on them. Extraction alone establishes acquisition, with host-reported provenance.

For a large prepared corpus, write UTF-8 JSON under `library/imports/` containing an ordered list of `{"kind":"document","data":{...}}` and `{"kind":"entry","data":{...}}` items. Documents precede entries that cite them; dependencies precede dependents. Call `adeptory_library` operation `import` with kit_id, filename and optional limit (1-25). Repeat the same call until status complete, or resolve the exact blocked item. A content-hash-keyed cursor persists after each successful item and resumes after interruption. This keeps bulk source data out of repeated model tool arguments. Imported counts retain the coverage and substantive-review limits of the material.

Retain exact applicable legal provisions where permitted, with section identity and effective-date limits. Use each textbook's actual license and attribution terms. Attribute explanations; author useful synthesis within the permitted reuse scope. Original text and authored explanation remain distinguishable.

## Organize coherent, independently retrievable knowledge

Call `adeptory_library` operation `entry` with kit_id and data containing id, title, kind, content, applicability, aliases, exceptions, dependencies, gaps and sources. Kind is reference, procedure, diagnostic, law or example. Each source reference contains document_id, locator and passage copied exactly from the captured document. The tool checks that the passage exists. This establishes attribution; assess substantive support separately. Independent inference carries `inference: true` and explicit assumptions.

An entry answers a real task or decision. Explain the mechanism, needed evidence, ordered procedure, meaningful branches, remedy and verification where relevant. Keep conditions, exceptions and dependencies beside the advice they govern. Preserve units, thresholds, jurisdiction, time period, normative force, table headers and code context. Use meaningful titles and aliases for professional terms, user symptoms and actual input fields. Read dependency entries before acting on a dependent procedure.

Merge necessary FAQ guidance into the relevant diagnostic procedure with precise source anchors. Distinguish observed zero, blank, missing, unavailable, stale and contradicted evidence. A recorded HTTP 200 establishes successful reachability at that crawl time; later observations establish later behavior. A suspected problem requires the evidence appropriate to that problem. Generic uncertainty checklists distract from the actual task.

The library generates `_index.md`, readable entries and a SQLite FTS5 index from one manifest. `search` takes query and optional limit; `read` takes entry_id. Results carry full entries, applicability, exceptions, dependency context, source identity, dates and changed-source flags. Source changes reopen dependent reasoning through review flags. Search is lexical, with title and alias weighting; broader semantic retrieval remains a separately observed capability.

Meaningful library changes revise the specialist and reopen adoption. Library mutation results return the current `kit_version`; use that version for subsequent package proposals. Repeating an identical source capture preserves the existing adoption. The activated runtime checks the current library fingerprint before applying its guidance. Review presents the profile library alongside the workflow's supporting excerpts.

Search covers acquired source text as well as authored entries. Source matches are labeled as search leads and include source state plus exact read_parameters. Read the relevant complete context before using a lead as an answer. Authored entries receive retrieval preference and carry their applicability and exceptions. Navigation indexes remain available at the profile and specialist roots.

## Construct the working specialist

Link reusable workflows to researched claims with the existing `adeptory_source` and `adeptory_propose` tools. Source records require id, url, title, retrieved_at, excerpt, locator and actual retrieval_tool. Preserve quality, jurisdiction, date uncertainty and receipts. Reviewed claims contain exact passage_checks for each cited source, reviewer and the support rationale. Batch related sources, reviewed claims, workflow and capabilities into a consistent proposal when practical. Use the current kit_version returned by library mutations and reload only when it changed; repeated per-record status polling adds no evidence. Claims and library entries preserve their distinct support records.

Each workflow step states instruction, reason, evidence_requirements, exceptions, priority, consequence, claim_ids and keywords. Map actual data fields, including their documented meanings and gaps. Define tool capabilities with readiness, why, inputs, outputs, access, setup and verification. Build authorized configuration/imports/connectors using the host's tools and permissions. An installation plan and a connected working tool receive different statuses. Report unavailable extraction, licensing or integrations as specific capability gaps with a concrete next step and usable fallback.

Demonstrate the selected work against independent expected evidence: authoritative examples, textbook exercises, reconciliations, specifications or qualified review as appropriate. Preserve input provenance, actual outputs, interpretation and failures. A synthetic case establishes its stated coverage. Useful incidental observations can be recorded when they arise from normal work; forcing an observation save and later recall establishes that instructed path only.

## Deliver the working specialist

Complete the library, supported claims, workflows and required capability setup. Keep source-specific qualifications beside the relevant advice. Put conditional business facts in applicability and future task questions; global `kit.gaps` represent construction that still needs to be completed. The user's original creation request authorizes building and ordinary use of the finished specialist. Product acceptance, external commitments and consequential actions retain their own authority.

Call `adeptory_build` operation `bundle` with kit_id and profile_name after `ready_for_bundle` is true. Reuse the returned saved distribution on retry. It includes the specialist's SOUL, library, generic plugin and the original build-request authorization. Install it through the returned public Hermes profile command. Preserve existing profiles and data; choose a fresh profile name on a genuine name collision. Apply the workspace's instruction/protection connections within the authorized creation scope. Credentials remain with the host.

Call `refresh_profile` for the installed profile and inspect the real host receipts. Verify native tool discovery and an ordinary representative question in a fresh session belonging to that generated profile. Use a made-up, task-appropriate test case with independently established expected evidence. Keep the original operator's acceptance-test conversation separate. Save actual results; a successful package export alone leaves native verification pending.

Call `adeptory_build finish` with kit_id, profile_name and `data: {native_receipt_id: <observed host tool receipt for the native check>}`. It verifies construction, final installation and the profile-owned library, completes the delivery task and authorizes ordinary use from the original authenticated request. Call `todo_list` with its returned `native_tasks` to show completion. For an explicitly requested same-chat build (`scope.delivery: current-chat`), `finish` validates the completed specialist and makes it usable in that chat.

Tell the user what was built, where to use it, what useful work it demonstrated and the specific conditions that matter. Lead with the usable result. A native choice is appropriate for a genuine consequential decision; command syntax belongs in optional technical help. Construction that remains incomplete stays in the build flow with its next executable task. A real external blocker identifies the exact missing access/fact and preserves completed work.

After delivery, use the library and supported workflow for actual tasks. Read full matching entries with their qualifications. Recheck source currency and applicability when the decision requires it. Ask about conditional facts when a particular task depends on them. Maintain refresh tasks and specific gaps in the saved plan. Expert validation and real-world outcomes retain their separately observed scope.
