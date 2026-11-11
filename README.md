# Adeptory

Build a Hermes specialist for the work you need done.

Describe the job and your circumstances. Adeptory researches the relevant authorities and instructional material, builds a searchable library, writes procedures, and configures the tools the specialist needs. It tests representative work before delivering the specialist's own Hermes profile.

## Install in your Hermes profile

Adeptory requires Hermes 0.23.1 or later and a configured model. Use the Hermes profile where you normally work.

In Hermes Desktop, open **Capabilities > Plugins** and install from this repository's Git source. Review the permissions and enable Adeptory. Follow any reload instruction Hermes displays.

In PowerShell, install the same source with the Hermes CLI.

```powershell
hermes plugins install https://github.com/brefledev/adeptory `
	--enable
```

After the Hermes catalog accepts Adeptory, you can also install it by name through the catalog.

## Build your first specialist

Open a new chat in the profile where you installed Adeptory. Send your request with `/adeptory build`.

```text
/adeptory build a specialist that checks small CSV files for
duplicate IDs and missing required values. Explain each finding
and show how to verify the corrected file.
```

You can also describe the job in ordinary conversation and ask Hermes to use Adeptory. Send `/adeptory` for the welcome message.

On first use, Hermes may ask whether Adeptory can start an AI reply when you submit a specialist request. Choose **Allow automatic replies** to continue from the request you already sent. The reply uses your current model and its normal usage charges.

Adeptory displays the build in Hermes's **Tasks** panel. It researches sources, organizes the library, prepares the specialist's procedures and tools, and checks a representative result. Required questions appear in Hermes's native question controls. Adeptory continues work that can proceed while facts remain unresolved.

When the build passes its completion checks, Adeptory reports the installed profile, its library, and the demonstrated result. Select that profile in Hermes and give the specialist a task. Your original request authorizes ordinary use of the specialist. Actions that require host permission retain that permission step.

## Keep working after an interruption

The original request and construction progress stay in the builder profile. Return to the same conversation and ask Adeptory to continue. Hermes controls Stop and interruption. Adeptory resumes the saved build when you request it.

Each specialist keeps its own `library/` directory. The library contains source captures, authored references, procedures, examples, a navigation index, and a search index. Entries retain their applicability, exceptions, source passages, and review requirements. Search works across acquired sources and authored entries.

The library also keeps a capability roadmap. During later work, the specialist can identify a missing tool or repeated procedure, record its implementation and verification plan, and build an improvement through authorized host tools. It retains the test result before reporting verification. Your original request continues to authorize ordinary work within the same mission. Changes to that mission reopen review.

Read [Library and source records](docs/source-ledger.md) for the evidence fields and freshness rules. Read [Tool setup](docs/tool-setup.md) for capability requirements and verification.

## Data, permissions, and costs

Adeptory stores the request, specialist records, construction progress, observations, and receipts in the active Hermes profile. A generated profile receives its specialist instructions and library. Source retrieval and tool execution use the host tools you authorize. Your model provider and connected tools apply their usual data policies and charges.

Building a specialist can require many model calls and source downloads. The size of the task, the available tools, and the chosen model determine the work. Adeptory records missing capabilities and source-access failures with the affected build tasks.

Source capture, passage matching, and a successful demonstration establish their recorded scope. Professional conclusions still depend on the supplied evidence, applicable rules, source currency, and the task. Consequential decisions may require a qualified professional's review.

## Reference

The [Hermes integration](docs/api-evidence.md) lists the registered tools, hooks, middleware, and host actions. The [record reference](docs/interfaces.md) describes specialist packages and construction state. [Development checks](docs/development.md) cover tests and catalog validation.
