"""Run packaged checks and preserve an honest machine-readable result."""
from pathlib import Path
import json
import platform
import subprocess
import sys
import unittest
import numpy
import PIL
from riglib.data import read_json,write_json,digest

ROOT=Path(__file__).resolve().parents[1]


def main():
    suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    numeric=subprocess.run([sys.executable,str(ROOT/"scripts"/"rig.py"),"validate-templates",
                            "--out",str(ROOT/"reports"/"template-validation.json")],capture_output=True,text=True)
    schema=subprocess.run([sys.executable,str(ROOT/"scripts"/"validate_templates.py"),"--self-test",
                           "--output",str(ROOT/"reports"/"schema-validation.json")],capture_output=True,text=True)
    boundary=subprocess.run([sys.executable,"-B","-X","utf8",str(ROOT/"scripts"/"verify_njc_boundary.py"),"--self-test",
                             "--output",str(ROOT/"reports"/"njc-boundary.json")],capture_output=True,text=True,encoding="utf-8")
    manifest=read_json(ROOT/"templates"/"manifest.json")
    # Manifest layouts are declared by its author; verify every declared hash.
    hashes=[]
    def visit(value):
        if isinstance(value,dict):
            if "sha256" in value and any(k in value for k in ("file","path")):
                raw=value.get("file",value.get("path"))
                candidates=[ROOT/raw,ROOT/"templates"/raw]
                found=next((p for p in candidates if p.is_file()),None)
                hashes.append({"path":raw,"matches":found is not None and digest(found)==value["sha256"]})
            for v in value.values(): visit(v)
        elif isinstance(value,list):
            for v in value: visit(v)
    visit(manifest)
    skill=(ROOT/"SKILL.md").read_text(encoding="utf8")
    front=skill.split("---",2)
    skill_valid=len(front)==3 and "name: nijigenerate-deterministic-rig" in front[1] and "description:" in front[1]
    report={"schema_version":"rig-verification/1","python":platform.python_version(),
            "numpy":numpy.__version__,"pillow":PIL.__version__,"tests_run":result.testsRun,
            "tests_passed":result.wasSuccessful(),"failures":len(result.failures),"errors":len(result.errors),
            "numeric_templates_passed":numeric.returncode==0,"numeric_stderr":numeric.stderr.strip(),
            "catalog_schema_passed":schema.returncode==0,"catalog_schema_stderr":schema.stderr.strip(),
            "njc_boundary_passed":boundary.returncode==0,"njc_boundary_stderr":boundary.stderr.strip(),
            "template_hashes":hashes,"skill_frontmatter_basic_valid":skill_valid,
            "real_model_appearance_approved":False,"live_model_modified":False}
    report["passed"]=bool(result.wasSuccessful() and numeric.returncode==0 and schema.returncode==0 and boundary.returncode==0 and skill_valid and hashes and
                          all(row["matches"] for row in hashes))
    write_json(ROOT/"reports"/"verification.json",report)
    print(json.dumps({k:v for k,v in report.items() if k not in ("template_hashes",)},ensure_ascii=False,indent=2))
    return 0 if report["passed"] else 1


if __name__=="__main__": raise SystemExit(main())
