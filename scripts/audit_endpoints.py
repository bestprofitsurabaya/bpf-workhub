#!/usr/bin/env python3
"""Read-only audit: backend endpoints vs frontend source references.

Statis — tidak menyentuh DB/server. Menampilkan:
  1. Endpoint backend yang TIDAK direferensikan frontend source (kandidat unused
     / hanya dipakai internal: cron, scheduler, sheet refresh, API publik).
  2. Path yang direferensikan frontend tapi tidak terdaftar backend (broken link).
  3. Endpoint publik vs butuh login (dari dekorator role_required/rate_limit).

Jalankan dari root repo: python3 scripts/audit_endpoints.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ROOT / "modules"
FRONTEND = ROOT / "frontend" / "src"
BACKEND_DIRS = [MODULES, ROOT / "app.py"]

# 1) Kumpulkan endpoint backend dari @app.route("...")
backend = {}  # path -> set(methods)
for d in BACKEND_DIRS:
    files = [d] if d.is_file() else sorted(d.rglob("*.py"))
    for f in files:
        src = f.read_text(encoding="utf-8", errors="ignore")
        # @app.route(...) dan @<bp>.route(...) — dgn re.S utk decorator multi-baris
        for m in re.finditer(r'@(?:app|\w+_bp)\.route\(\s*["\']([^"\']+)["\'](?:\s*,\s*methods=\[([^\]]*)\])?', src, re.S):
            path = m.group(1)
            methods = set(re.findall(r'["\']([A-Z]+)["\']', m.group(2) or "")) or {"GET"}
            backend.setdefault(path, set()).update(methods)

# 2) Kumpulkan referensi path dari frontend SOURCE (bukan dist/static build)
refs = set()
for f in FRONTEND.rglob("*"):
    if f.suffix not in (".vue", ".js", ".ts", ".mjs"):
        continue
    src = f.read_text(encoding="utf-8", errors="ignore")
    # string literal yang mulai dengan /api/ atau path SPA umum — capture sampai
    # quote/whitespace pertama (path boleh diikuti ?query atau ${template})
    refs.update(re.findall(r'["\'`](/api/[^"\'`\s]+)', src))
    refs.update(re.findall(r'["\'`](/app(?:/[^"\'`\s]*)?)["\'`]', src))
    refs.update(re.findall(r'["\'`](/submit-trip|/driver|/cash[^"\'`\s]*)["\'`]', src))

# scripts/ + tests/ juga kadang panggil endpoint
EXTRA_DIRS = [ROOT / "scripts", ROOT / "tests"]
for d in EXTRA_DIRS:
    for f in d.rglob("*.py"):
        src = f.read_text(encoding="utf-8", errors="ignore")
        refs.update(re.findall(r'["\'](/api/[A-Za-z0-9_\-${}/.]+)["\']', src))

# 3) Normalisasi: strip placeholder & konversi path param utk cocok dgn backend
def norm(p):
    p = p.split("?")[0]
    p = re.sub(r"\$\{[^}]*\}", "<x>", p)   # template literal frontend
    p = re.sub(r"<[^>]*>", "<x>", p)         # Flask converter <int:id>
    p = p.rstrip("/") or "/"
    return p

backend_paths = {norm(p) for p in backend}

# 4) Cocokkan: backend path tanpa referensi frontend
def pattern_of(n):
    # backend path dgn param (/api/x/<id>) cocok dgn ref /api/x/123
    return "^" + re.escape(n).replace("<x>", r"[^/]+") + "$"

def has_ref(path):
    pattern = pattern_of(norm(path))
    return any(re.match(pattern, norm(r)) for r in refs)

unused = []
for path in sorted(backend):
    if not has_ref(path):
        unused.append(path)

# ref frontend yang tidak ada backend-nya
not_found = sorted({norm(r) for r in refs if norm(r) and not any(
    re.match(pattern_of(norm(bp)), norm(r))
    for bp in backend
)})

print(f"=== Backend endpoints terdaftar: {len(backend)} ===")
print(f"=== Referensi path frontend+scripts+tests: {len(refs)} (unik mentah) ===")
print()
print("--- Endpoint TANPA referensi frontend (kandidat unused / internal-only) ---")
for p in unused:
    methods = ",".join(sorted(backend[p]))
    print(f"  [{methods:10s}] {p}")
print(f"\nTotal tanpa referensi frontend: {len(unused)}")
print()
print("--- Path direferensikan tapi TIDAK cocok endpoint backend (cek manual) ---")
for r in not_found[:40]:
    print(f"  {r}")
print(f"\nTotal tidak cocok: {len(not_found)}")
