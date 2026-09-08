"""Sinkronkan identitas cabang (system_name/system_version/address/phone)
ke system_config tiap DB cabang — idempoten (8 Sep 2026, v2.37.7).

Jalankan: docker exec bbm_web python3 /app/scripts_sync_stamp_tmp.py
"""
import sys
sys.path.insert(0, '/app')
from modules import branch_manager as bm

ok, fail = [], []
for b in bm.list_branches():
    if not b.get('is_active') or b['code'] == 'SBY':
        continue  # SBY = master (identitas tinggal di system_config master)
    try:
        bm.write_branch_identity(b)
        ok.append(b['code'])
    except Exception as e:
        fail.append((b['code'], str(e)[:60]))
print('sinkron OK :', ok)
print('gagal      :', fail)
