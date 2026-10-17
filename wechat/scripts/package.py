"""Make reviewable source and CloudBase ZIPs; exclude all secrets and user data."""
from pathlib import Path
import json
import zipfile
ROOT = Path(__file__).resolve().parents[1]
output = ROOT / "artifacts"
output.mkdir(exist_ok=True)
def safe(path):
    parts = path.relative_to(ROOT).parts
    return not any(p in {".env", ".data", ".venv", "__pycache__", ".git", ".pytest_cache", "node_modules", "artifacts", "project.private.config.json"} for p in parts) and path.suffix not in {".pyc", ".zip"}
files = [p for p in ROOT.rglob("*") if p.is_file() and safe(p)]
for name, selected in [
    ("SuperJLU-wechat-source.zip", files),
    ("SuperJLU-cloudbase-deploy.zip", [p for p in files if p.parts[len(ROOT.parts)] == "server" and p.name != "test_app.py"] + [ROOT / "Dockerfile", ROOT / ".dockerignore"])
]:
    with zipfile.ZipFile(output / name, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in selected:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output / name) as archive:
        names = archive.namelist()
        assert not any(Path(n).name in {".env", "project.private.config.json"} or "/.data/" in n for n in names)
    print(name, len(names), "files; no .env, private project config or personal cache included")
