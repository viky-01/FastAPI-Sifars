import subprocess
import sys

if __name__ == "__main__":
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"])
    raise SystemExit(result.returncode)
