# tests/test_tkd_core_sampling.py
import random
from modules.tkd_core import (DEFAULT_QUOTA, select_questions, readiness,
                              validate_settings, public_state)

def _q(code, category, tier=None, active=1, type_='MCQ', points=1):
    return {'id': hash(code) % 10000, 'code': code, 'category': category,
            'type': type_, 'prompt': code, 'options': [{'id': 'a', 'text': 'A'},
            {'id': 'b', 'text': 'B'}], 'answer': {'option': 'a'},
            'points': points, 'modal_tier': tier, 'active': active,
            'sort_order': 0}

def _bank():
    rows = []
    for i in range(8): rows.append(_q(f'REG-{i}', 'REGULASI'))
    for i in range(5): rows.append(_q(f'PER-{i}', 'PERUSAHAAN'))
    for i in range(7): rows.append(_q(f'PRO-{i}', 'PRODUK'))
    for i in range(4): rows.append(_q(f'HIT-G-{i}', 'HITUNG'))
    for tier in ('30k', '50k', '100k'):
        for i in range(2): rows.append(_q(f'HIT-{tier}-{i}', 'HITUNG', tier))
    rows.append(_q('PROF-1', 'PROFIL', type_='PROFILE_TEXT', points=0))
    return rows

SETTINGS = {'question_count': 20, 'duration_minutes': 25, 'pass_score': 70,
            'max_attempts': 2, 'quota': dict(DEFAULT_QUOTA), 'active': 1}

def test_sampling_memenuhi_kuota_dan_menambah_satu_profil():
    picked = select_questions(_bank(), SETTINGS, '30k', rng=random.Random(1))
    assert len(picked) == 21
    valued = [q for q in picked if q['type'] != 'PROFILE_TEXT']
    assert len(valued) == 20
    assert {c: sum(1 for q in valued if q['category'] == c) for c in DEFAULT_QUOTA} == DEFAULT_QUOTA
    assert picked[-1]['category'] == 'PROFIL'

def test_hanya_tier_terpilih_yang_muncul():
    picked = select_questions(_bank(), SETTINGS, '100k', rng=random.Random(2))
    tiers = {q['modal_tier'] for q in picked if q['category'] == 'HITUNG'}
    assert '100k' in tiers
    assert not ({'30k', '50k'} & tiers)

def test_bank_kurang_mengembalikan_none():
    rows = [q for q in _bank() if not q['code'].startswith('REG')]
    assert select_questions(rows, SETTINGS, '30k') is None

def test_kesiapan_butuh_kuota_tiap_kategori_dan_tier():
    ok = readiness(_bank(), SETTINGS)
    assert ok['ready'] is True
    assert all(ok['tier_ok'].values())

    short = [q for q in _bank() if q['code'] not in ('PRO-0', 'PRO-1')]
    bad = readiness(short, SETTINGS)
    assert bad['ready'] is False
    assert 'PRODUK' in ' '.join(bad['reasons'])

def test_kesiapan_kuota_pas_tanpa_cadangan_tetap_ready():
    rows = [q for q in _bank() if q['code'] != 'PRO-0']
    result = readiness(rows, SETTINGS)
    assert result['ready'] is True
    assert result['quota_ok']['PRODUK'] is True

def test_validate_settings_menolak_kuota_tidak_sama_dan_attempt_bukan_2():
    payload = dict(SETTINGS, quota={'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 2})
    data, errors = validate_settings(payload)
    assert data is None and any('kuota' in e.lower() for e in errors)

    data, errors = validate_settings(dict(SETTINGS, max_attempts=3))
    assert data is None and any('2' in e for e in errors)

def test_state_publik_lulus_habis_dan_dikecualikan():
    case = {'tkd_score': 85, 'tkd_score_source': 'AUTO', 'tkd_passed': 1}
    state = public_state(case, [], [], SETTINGS)
    assert state['state'] == 'LULUS' and state['can_start'] is False

    case = {'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0}
    attempts = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 60},
                {'id': 'TKD-2', 'status': 'SELESAI', 'score': 55}]
    assert public_state(case, attempts, [], SETTINGS)['state'] == 'HABIS'

    steps = [{'step_type': 'TKD', 'status': 'DIKECUALIKAN'}]
    assert public_state(case, [], steps, SETTINGS)['state'] == 'DIKECUALIKAN'

def test_state_publik_memakai_flag_lulus_tersimpan_bukan_ambang_baru():
    # Ambang diturunkan: percobaan lama yang gagal tidak boleh berubah LULUS.
    case = {'tkd_score': 85, 'tkd_score_source': 'AUTO', 'tkd_passed': 0}
    attempts = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 85}]
    lower = dict(SETTINGS, pass_score=60)
    assert public_state(case, attempts, [], lower)['state'] == 'BISA_COBA'

    # Ambang dinaikkan: percobaan lama yang lulus tetap LULUS.
    case = {'tkd_score': 65, 'tkd_score_source': 'AUTO', 'tkd_passed': 1}
    higher = dict(SETTINGS, pass_score=90)
    assert public_state(case, attempts, [], higher)['state'] == 'LULUS'


def test_state_publik_belum_berlangsung_dan_bisa_coba():
    empty = {'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
    assert public_state(empty, [], [], SETTINGS)['state'] == 'BELUM'
    active = [{'id': 'TKD-1', 'status': 'BERLANGSUNG', 'score': None,
               'expires_at': '2099-01-01 00:00:00'}]
    st = public_state(empty, active, [], SETTINGS)
    assert st['state'] == 'BERLANGSUNG' and st['active_attempt']['id'] == 'TKD-1'
    done = [{'id': 'TKD-1', 'status': 'SELESAI', 'score': 60}]
    assert public_state({'tkd_score': 60, 'tkd_score_source': 'AUTO', 'tkd_passed': 0},
                        done, [], SETTINGS)['state'] == 'BISA_COBA'

def test_state_skor_belum_tercatat_untuk_kasus_lama():
    case = {'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
    steps = [{'step_type': 'TKD', 'status': 'SELESAI'}]
    assert public_state(case, [], steps, SETTINGS)['state'] == 'SKOR_BELUM_TERCATAT'

def test_validate_settings_menolak_flag_bukan_boolean():
    data, errors = validate_settings(dict(SETTINGS, shuffle_options=0.5))
    assert data is None and any('shuffle_options' in e for e in errors)

def test_settings_nonaktif_menjadi_segera_walaupun_ada_attempt_aktif():
    case = {'tkd_score': None, 'tkd_score_source': None, 'tkd_passed': None}
    active = [{'id': 'TKD-1', 'status': 'BERLANGSUNG', 'expires_at': None}]
    state = public_state(case, active, [], dict(SETTINGS, active=0))
    assert state['state'] == 'SEGERA' and state['can_start'] is False
    assert state['active_attempt'] is None

def test_readiness_mengabaikan_soal_tidak_aktif():
    rows = _bank()
    for row in rows:
        if row['code'] in ('REG-0', 'REG-1'):
            row['active'] = 0
    bad = readiness(rows, SETTINGS)
    assert bad['ready'] is False
    assert 'REGULASI' in ' '.join(bad['reasons'])
