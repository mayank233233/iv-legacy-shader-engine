from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "analyze_shader_constant_cache.py"), "--self-test"],
    cwd=ROOT, text=True, capture_output=True,
)
if result.returncode:
    print(result.stdout)
    print(result.stderr)
    raise SystemExit(result.returncode)
print(result.stdout.strip())
