# Tool setup

A specialist records the capabilities its work requires. Each capability states why it matters, the inputs and outputs, required access, setup steps, and the observation that verifies it.

## Readiness states

| State | Meaning |
|---|---|
| `available` | The package records an available capability and its verification requirement. |
| `configurable` | The host has an integration that needs configuration. |
| `build-required` | The selected work needs additional implementation. |
| `missing` | The required capability is unavailable in the current setup. |

Readiness is a recorded assessment. An observed tool result establishes the operation actually exercised. Each result retains its input, time, target, and stated limits.

## Setup records

A setup plan identifies the specific tool, required version or license, intended records, permitted paths or endpoints, access needs, configuration, and verification. The host governs permissions and credentials.

For a CSV specialist, setup can use an authorized local file reader and a parser. Verification uses a known file and compares duplicate-ID and required-value findings with independent expected rows. The procedure records how blanks, missing columns, repeated IDs, and malformed input affect the result.

For an SEO specialist, a crawl export can provide evidence even when a live crawler integration is unavailable. The specialist maps the actual export headers, records the crawl date and configuration, and requests additional evidence when an export cannot establish the needed fact. A proposed connector setup retains its own unverified status until the connection and representative read pass.

## Native profile delivery

Adeptory prepares the specialist's instructions and library as a local Hermes profile distribution. The host installs the distribution. Adeptory checks the installed starter identity, refreshes plugin exposure through the public CLI, and requires an observed ordinary task in the new profile.

Model and provider selection can travel with the distribution as non-secret configuration. Credential setup remains with Hermes. A completed profile retains the source qualifications and unresolved applicability conditions that govern later work.

## Failures and fallbacks

A setup failure records the affected capability, the observed error, and the next action. Independent construction tasks can continue. A fallback describes the evidence it can supply and the conclusions that evidence supports. The build's completion status reflects required capabilities and their recorded verification.
