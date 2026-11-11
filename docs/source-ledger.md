# Library and source records

Adeptory stores acquired documents and authored entries in the specialist's own profile library. These records preserve the evidence needed to inspect a recommendation and decide whether it applies to the current task.

## Captured documents

| Field | Meaning |
|---|---|
| Identity and URL | The source record and its publisher location. |
| Title and authority | The document's identity and the recorded basis for its authority. |
| Role | Governing, instructional, technical, reference, worked-example, or user material. |
| Capture scope | The full document, selected sections, an excerpt, or an unknown extent. |
| Dates | Publication, effective period, retrieval, and declared next review. Unknown values remain explicit. |
| Jurisdiction | The location or legal jurisdiction that controls applicability when relevant. |
| Reuse terms | The source's recorded license or other reuse limits. |
| Retrieval metadata | The host tool, capture time, available response evidence, and retrieval limitations. |
| Hash and history | The captured content identity and earlier source versions. |

The source's role and authority type describe its use. Normative force records whether the material is binding, advisory, instructional, or unverified. A law, an agency explanation, a vendor manual, and a textbook have distinct authority and scope.

Retrieval metadata is host-reported. A content hash checks the integrity of a stored capture. Capture completeness, source authority, applicability, and substantive support require their own assessments.

## Authored entries

An entry contains a reference, procedure, diagnostic, law, or worked example. Its title and aliases support retrieval by professional terms, symptoms, and actual input fields.

Each entry keeps its applicability, exceptions, dependencies, and evidence gaps beside the advice. Source references identify the captured document, section locator, and exact supporting passage. The library checks that each cited passage occurs in the capture. Claim review records the separate judgment about what that passage supports.

A useful diagnostic explains the mechanism, required evidence, relevant branches, concrete remedy, and verification. Partial evidence supports a limited conclusion and identifies the additional evidence needed. A vendor's default priority retains the vendor's scope. Task-specific priority requires the site's or business's circumstances.

## Freshness and revisions

Retrieval time records when a tool acquired a source. Publication and effective dates record the source's own time scope. Amendments, new editions, changed vendor behavior, and dated tasks can require another source check.

The library preserves source history. Replacing source content marks dependent entries for review and changes the specialist's library fingerprint. Search and read results expose that state with the entry's conditions and source metadata.

## Claims and workflows

Source excerpts can also support package-level claims. A claim records its support status, source IDs, exact passage checks, reviewer, rationale, contradictions, and inference assumptions. A workflow links its instructions to those claims and states the evidence and exceptions that govern each step.

Independent task evaluation records the actual output and an expected result established from a specification, authoritative worked example, reconciliation, or qualified review. Source counts and stored passages describe the acquired evidence. The evaluation comparison describes the demonstrated task result.

The [build skill](../skills/build/SKILL.md) defines the complete document, entry, claim, and demonstration input contracts.
