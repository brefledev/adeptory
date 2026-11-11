# Validate a release

Run the checks from the repository root with the Python environment used by Hermes. The test suite uses `unittest` and temporary data directories. Hermes supplies PyYAML for profile configuration.

## Run the tests

In PowerShell, run the unit and integration tests.

```powershell
python -m unittest discover -s tests -v
```

The synthetic fixtures exercise package records, source attribution, library retrieval, construction readiness, native controls, request preservation, and profile delivery. Their assertions establish the cases they execute. A real model run establishes its own observed behavior.

## Run the catalog check

In PowerShell, run the same validator used for catalog submissions.

```powershell
hermes plugins validate . --install-deps
```

Resolve every failure and read every warning. Validate the exact checkout and commit that the catalog entry will pin. Keep local recordings, diagnostic traces, generated profiles, and build artifacts outside the plugin directory. The install scanner inspects files in that directory.

In PowerShell, inspect registration with Plugin Doctor.

```powershell
hermes plugins doctor . --ci
```

The manifest declares seven tools, four hooks, and two middleware registrations. Doctor and the catalog validator compare declarations with actual registration.

## Verify the native workflow

1. Install the candidate through Hermes's plugin installer in a separate test profile.
2. Open a new chat and submit a made-up specialist request once.
3. Exercise the first-use reply permission and confirm that the saved request starts the response.
4. Observe the native Tasks panel and the saved construction evidence.
5. Confirm that the generated profile installs through the public Hermes profile installer.
6. Give that profile an ordinary task and compare its result with independent expected evidence.
7. Stop a separate unfinished test build, reopen its conversation, and confirm that an explicit request resumes its saved progress.

Record the candidate commit, host version, model, input, tool results, expected result, comparison, and remaining limits. Use isolated synthetic inputs. Preserve other people's profiles, requests, and sessions.

## Prepare the catalog entry

Follow the [official catalog submission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission). Pin the entry to the full 40-character commit that passed validation. Disclose model usage, host tool access, profile storage, generated-profile installation, and the CLI actions listed in [Hermes integration](api-evidence.md).
