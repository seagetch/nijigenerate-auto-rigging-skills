"""Verify PSD-only intake twice on a real PSD; never synthesize test artwork."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

from riglib.data import digest, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def verify(psd_path, destination):
    source = Path(psd_path).resolve(strict=True)
    output = Path(destination).resolve()
    if source == output or source.is_relative_to(output):
        raise ValueError("verification output cannot contain or replace the source PSD")
    if output.exists() and (not output.is_dir() or next(output.iterdir(), None) is not None):
        raise ValueError("verification output must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    before = digest(source)
    runs = []
    manifests = []
    for name in ("first", "second"):
        target = output / name
        args = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts" / "rig.py"),
                "prepare-psd", "--psd", str(source), "--out", str(target)]
        completed = subprocess.run(args, capture_output=True, encoding="utf-8", timeout=180)
        runs.append({"stage": name, "exit_code": completed.returncode,
                     "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()})
        if completed.returncode != 0:
            write_json(output / "verification.json", {"passed": False, "runs": runs,
                       "source_unchanged": before == digest(source)})
            return False
        manifests.append(read_json(target / "psd-source.json"))
    asset_checks = []
    for left in manifests[0]["assets"]:
        relative = left["path"]
        first, second = output / "first" / relative, output / "second" / relative
        asset_checks.append({"path": relative, "matches": digest(first) == digest(second) == left["sha256"]})
    reject_checks = {}
    for flag in ("--model", "--evidence", "--hints", "--template"):
        # Reuse the real path only as an unrecognized argument. The CLI must
        # reject parsing before it reads any proposed second input.
        args = [sys.executable, "-B", "-X", "utf8", str(ROOT / "scripts" / "rig.py"),
                "prepare-psd", "--psd", str(source), "--out", str(output / "rejected"), flag, str(source)]
        completed = subprocess.run(args, capture_output=True, encoding="utf-8", timeout=30)
        reject_checks[flag] = completed.returncode == 2 and not (output / "rejected").exists()
    checks = {
        "source_unchanged": digest(source) == before,
        "manifests_equal": manifests[0] == manifests[1],
        "assets_equal": bool(asset_checks) and all(row["matches"] for row in asset_checks),
        "sidecar_arguments_rejected": all(reject_checks.values()),
        "observation_stage_only": all(m["status"] == "psd_observation_ready"
                                       and m["rig_complete"] is False for m in manifests),
    }
    report = {"schema_version": "rig-psd-source-verification/1", "passed": all(checks.values()),
              "checks": checks, "source_sha256": before, "source": str(source),
              "summary": manifests[0]["summary"], "runs": runs, "assets": asset_checks,
              "rejected_extra_inputs": reject_checks,
              "implementation_sha256": {name: digest(ROOT / "scripts" / name)
                                        for name in ("rig.py", "riglib/psd_source.py", "verify_psd_source.py")},
              "synthetic_artwork_created": False, "live_model_modified": False,
              "completed_rig_verified": False}
    write_json(output / "verification.json", report)
    return report["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--psd", required=True)
    parser.add_argument("--out", required=True)
    options = parser.parse_args()
    try:
        passed = verify(options.psd, options.out)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"passed": passed, "report": str(Path(options.out).resolve() / "verification.json")}))
    raise SystemExit(0 if passed else 1)
