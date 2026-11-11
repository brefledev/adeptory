"""Portable validation, export and evaluation commands."""
import argparse
import json
import subprocess
from pathlib import Path
import sys

def main(argv=None):
    parser = argparse.ArgumentParser(prog="adeptory")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--kit", required=True)
    export = commands.add_parser("export")
    export.add_argument("--data", required=True)
    export.add_argument("--kit", required=True)
    export.add_argument("--destination", required=True)
    evaluation = commands.add_parser("eval")
    evaluation.add_argument("--suite", required=True)
    evaluation.add_argument("--mechanics-only", action="store_true")
    evaluation.add_argument("--output")
    evaluation.add_argument("--run-live", action="store_true")
    evaluation.add_argument("--profile-root")
    evaluation.add_argument("--kit-id")
    evaluation.add_argument("--runner")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            from .kitstore import kit_from_dict, validate_kit
            path = Path(args.kit)
            if path.is_dir():
                path = path / ("kit.json" if (path / "kit.json").is_file() else "kit.yaml")
            content = path.read_text(encoding="utf-8-sig")
            if path.suffix.lower() in {".yaml", ".yml"}:
                import yaml
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            kit = kit_from_dict(data)
            gaps = validate_kit(kit)
            result = {"kit_id": kit.id, "version": kit.version, "adoption": kit.adoption.status, "gaps": gaps}
        elif args.command == "export":
            from .kitstore import KitStore
            result = {"export": str(KitStore(Path(args.data)).export(args.kit, Path(args.destination)))}
        else:
            if args.run_live:
                if args.mechanics_only or not args.profile_root or not args.kit_id or not args.runner:
                    raise ValueError("live evaluation needs an explicitly reviewed --runner, --profile-root and --kit-id")
                import tempfile
                with tempfile.TemporaryDirectory(prefix="adeptory-eval-") as temp:
                    receipt = Path(temp) / "runner-result.json"
                    subprocess.run([sys.executable, str(Path(args.runner).resolve()), "--suite", args.suite,
                                    "--profile-root", args.profile_root, "--kit-id", args.kit_id,
                                    "--result-file", str(receipt)], check=True)
                    suite_path = json.loads(receipt.read_text(encoding="utf-8"))["suite"]
            else:
                suite_path = args.suite
            from .evalcheck import run_suite
            result = run_suite(Path(suite_path), mechanics_only=args.mechanics_only)
            if args.run_live:
                result.update(execution_mode="live_sessions_then_artifact_report", live_model_calls=None,
                              live_call_evidence=str(suite_path),
                              live_call_count_note="Per-turn API call and token counters are retained in raw artifact results.")
            if args.output:
                Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0
    except (ValueError, OSError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
