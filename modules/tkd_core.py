"""Fungsi murni untuk TKD online (Rilis C).

Modul ini tidak menyentuh DB atau Flask: dipakai oleh layanan/route dan
oleh skrip seed. Aturan angka mengikuti format Indonesia (titik ribuan,
koma desimal), sedangkan kunci jawaban selalu berasal dari snapshot soal
yang dibekukan saat attempt dibuat — bukan bank soal yang bisa berubah.

Konstanta di sini adalah sumber tunggal kuota/kategori/tier untuk skema,
layanan, UI admin, dan import CSV.
"""
import csv
import io
import json
import math
import random
import re
from datetime import date, datetime
from decimal import Decimal


DEFAULT_QUOTA = {'REGULASI': 7, 'PERUSAHAAN': 4, 'PRODUK': 6, 'HITUNG': 3}
MAX_ATTEMPTS = 2
MODAL_TIERS = ('30k', '50k', '100k')
CATEGORIES = ('REGULASI', 'PERUSAHAAN', 'PRODUK', 'HITUNG', 'PROFIL')


def derive_dob_from_nik(nik, today=None):
    """Tanggal lahir (`date`) dari NIK — delegasi ke util NIK bersama.

    Kompatibel dengan pemanggil lama yang mengirim `today`; satu-satunya
    aturan pivot abad kini ada di `modules.nik_utils`.
    """
    from modules.nik_utils import birth_date_from_nik
    text = birth_date_from_nik(nik, today=today)
    return date.fromisoformat(text) if text else None


def parse_numeric(value):
    """Ubah angka-format-Indonesia menjadi float; None untuk input sampah.

    '$1.866,8', 'US$ 1 866,8' dan '159.501' berturut-turut berarti
    1866.8, 1866.8, dan 159501 (titik sebagai pemisah ribuan hanya bila
    polanya persis \\d{1,3}(\\.\\d{3})+). Bool sengaja ditolak karena
    True/False bukan jawaban numerik.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
    elif isinstance(value, str):
        text = re.sub(r'(?i)us\$|\$|rp|\s', '', value.strip())
        if not text:
            return None
        if ',' in text and '.' in text:
            text = text.replace('.', '').replace(',', '.')
        elif ',' in text:
            text = text.replace(',', '.')
        elif re.fullmatch(r'\d{1,3}(\.\d{3})+', text):
            text = text.replace('.', '')
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def normalize_short_text(value):
    """Kunci perbandingan jawaban pendek: huruf besar, tanpa tanda baca."""
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def _points(question):
    return parse_numeric((question or {}).get('points')) or 0.0


def _award(question, correct):
    return _points(question) if correct else 0.0


def grade_answer(question: dict, answer) -> tuple[bool | None, float]:
    """Nilai satu jawaban memakai kunci dari snapshot soal.

    Mengembalikan `(is_correct, points_awarded)`. `PROFILE_TEXT` tidak
    dinilai sama sekali (`None`, 0 poin) meski jawabannya diisi.
    """
    question = question or {}
    qtype = question.get('type')
    key = question.get('answer') or {}
    key = key if isinstance(key, dict) else {}
    given = answer if isinstance(answer, (dict, str, int, float, Decimal)) and not isinstance(answer, bool) else None

    if qtype == 'PROFILE_TEXT':
        return None, 0.0

    if qtype == 'MCQ':
        correct_option = key.get('option')
        answer_option = given.get('option') if isinstance(given, dict) else None
        correct = bool(correct_option) and answer_option == correct_option
    elif qtype == 'NUMERIC':
        expected = parse_numeric(key.get('value'))
        tolerance = parse_numeric(key.get('tolerance')) or 0.0
        raw = given.get('value') if isinstance(given, dict) else given
        received = parse_numeric(raw)
        correct = (expected is not None and received is not None
                   and abs(received - expected) <= tolerance)
    elif qtype == 'SHORT_TEXT':
        text = given.get('text') if isinstance(given, dict) else (given if isinstance(given, str) else None)
        normalized = normalize_short_text(text)
        aliases = key.get('aliases') or []
        if isinstance(aliases, str):
            aliases = aliases.split('|')
        correct = bool(normalized) and any(
            normalize_short_text(alias) == normalized for alias in aliases
        )
    else:
        correct = False
    return correct, _award(question, correct)


def compute_score(items: list[dict], pass_score: float) -> dict:
    """Hitung skor persentase dari item yang dinilai (points > 0)."""
    total_points = 0.0
    awarded = 0.0
    correct_count = 0
    for item in items or []:
        item = item or {}
        points = parse_numeric(item.get('points')) or 0.0
        if points <= 0:
            continue
        total_points += points
        awarded += parse_numeric(item.get('points_awarded')) or 0.0
        if item.get('is_correct'):
            correct_count += 1

    if total_points == 0:
        score, passed = 0.0, False
    else:
        score = round(awarded / total_points * 100, 2)
        passed = score >= (parse_numeric(pass_score) or 0.0)
    return {
        'score': score,
        'total_points': total_points,
        'awarded': awarded,
        'correct_count': correct_count,
        'passed': passed,
    }


def as_json(value, default=None):
    """Terima JSON string/dict/list dari DB; kembalikan `default` bila kosong/rusak."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return default


def _as_flag(value):
    """Normalisasi nilai aktif/boolean dari DB atau form; None bila ambigu."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value) if value in (0, 1) else None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ('1', 'true', 'ya', 'yes', 'on'):
            return True
        if text in ('0', 'false', 'tidak', 'no', 'off', ''):
            return False
    return None


def _active_valued(questions):
    """Soal bernilai yang aktif; kategori PROFIL/PROFILE_TEXT dikecualikan."""
    return [q for q in (questions or [])
            if q and _as_flag(q.get('active')) is True
            and q.get('category') != 'PROFIL'
            and q.get('type') != 'PROFILE_TEXT']


def _in_hit_pool(question, modal_tier):
    """Soal HITUNG umum (tanpa tier) atau tier yang diminta saja."""
    return (question.get('modal_tier') or '') in ('', modal_tier)


def select_questions(questions: list[dict], settings: dict, modal_tier: str,
                     rng=None) -> list[dict] | None:
    """Ambil 20 soal bernilai sesuai kuota + 1 PROFILE_TEXT di urutan terakhir.

    Pool HITUNG hanya berisi soal umum dan soal tier `modal_tier`; varian
    modal lain tidak pernah masuk, termasuk saat menambal kekurangan kuota.
    Mengembalikan None bila bank tidak cukup atau tidak ada soal profil.
    """
    rng = rng or random
    settings = settings or {}
    quota = settings.get('quota') or DEFAULT_QUOTA
    target = int(parse_numeric(settings.get('question_count')) or 0)
    valued = _active_valued(questions)

    pools = {}
    for category in quota:
        source = valued
        if category == 'HITUNG':
            source = [q for q in valued if _in_hit_pool(q, modal_tier)]
        pools[category] = [q for q in source if q.get('category') == category]

    picked = []
    picked_ids = set()
    for category, needed in quota.items():
        needed = int(parse_numeric(needed) or 0)
        pool = pools[category]
        for question in rng.sample(pool, min(max(needed, 0), len(pool))):
            picked.append(question)
            picked_ids.add(id(question))

    # Kekurangan kuota diisi dari sisa pool kategori lain, bukan tier lain.
    if len(picked) < target:
        leftover = [q for pool in pools.values() for q in pool
                    if id(q) not in picked_ids]
        rng.shuffle(leftover)
        picked.extend(leftover[:target - len(picked)])
    if len(picked) < target:
        return None

    profiles = [q for q in (questions or [])
                if q and _as_flag(q.get('active')) is True
                and q.get('type') == 'PROFILE_TEXT']
    if not profiles:
        return None

    rng.shuffle(picked)
    return picked + [profiles[0]]


def readiness(questions: list[dict], settings: dict) -> dict:
    """Periksa kesiapan bank: total soal, kuota, tiap tier, dan soal profil.

    Sesuai §4.3, kuota kategori cukup terpenuhi (≥ kuota); satu soal cadangan
    untuk rotasi dua percobaan bukan syarat kesiapan.
    """
    settings = settings or {}
    quota = settings.get('quota') or DEFAULT_QUOTA
    target = int(parse_numeric(settings.get('question_count')) or 0)
    valued = _active_valued(questions)
    counts = {cat: sum(1 for q in valued if q.get('category') == cat)
              for cat in quota}
    needs = {cat: int(parse_numeric(needed) or 0) for cat, needed in quota.items()}
    quota_ok = {cat: counts[cat] >= needs[cat] for cat in quota}

    hit_needed = needs.get('HITUNG', 0)
    hit_general = sum(1 for q in valued if q.get('category') == 'HITUNG'
                      and not (q.get('modal_tier') or ''))
    tier_counts = {
        tier: hit_general + sum(
            1 for q in valued if q.get('category') == 'HITUNG'
            and (q.get('modal_tier') or '') == tier)
        for tier in MODAL_TIERS
    }
    tier_ok = {tier: count >= hit_needed for tier, count in tier_counts.items()}
    has_profile = any(q and _as_flag(q.get('active')) is True
                      and q.get('type') == 'PROFILE_TEXT'
                      for q in (questions or []))

    reasons = []
    if len(valued) < target:
        reasons.append(f'Soal bernilai aktif {len(valued)}, butuh {target}.')
    for category, needed in needs.items():
        available = counts[category]
        if not quota_ok[category]:
            reasons.append(f'{category}: tersedia {available}, butuh {needed}.')
    for tier, count in tier_counts.items():
        if not tier_ok[tier]:
            reasons.append(f'HITUNG tier {tier}: tersedia {count}, butuh {hit_needed}.')
    if not has_profile:
        reasons.append('Belum ada soal PROFILE_TEXT aktif.')

    ready = (len(valued) >= target and all(quota_ok.values())
             and all(tier_ok.values()) and has_profile)
    return {'ready': ready, 'active_valued': len(valued),
            'quota_ok': quota_ok, 'tier_ok': tier_ok, 'reasons': reasons}


def _int_setting(payload, name, low, high, errors):
    """Ambil bilangan bulat dari payload atau catat error validasi."""
    number = parse_numeric(payload.get(name))
    if (number is None or not float(number).is_integer()
            or not low <= number <= high):
        errors.append(f'{name} harus bilangan bulat {low}–{high}')
        return None
    return int(number)


def validate_settings(payload: dict) -> tuple[dict | None, list[str]]:
    """Normalisasi dan validasi pengaturan TKD; kembalikan error bahasa Indonesia."""
    payload = payload if isinstance(payload, dict) else {}
    errors = []

    question_count = _int_setting(payload, 'question_count', 1, 100, errors)
    duration = _int_setting(payload, 'duration_minutes', 5, 180, errors)
    pass_score = parse_numeric(payload.get('pass_score'))
    if pass_score is None or not 0 <= pass_score <= 100:
        errors.append('pass_score harus antara 0 dan 100')

    attempts = parse_numeric(payload.get('max_attempts'))
    if attempts is None or attempts != 2:
        errors.append('max_attempts wajib 2')

    quota = {}
    raw_quota = payload.get('quota')
    if not isinstance(raw_quota, dict):
        errors.append('kuota harus berisi empat kategori bernilai')
    else:
        if set(raw_quota) != set(DEFAULT_QUOTA):
            errors.append('kuota harus tepat: ' + ', '.join(DEFAULT_QUOTA))
        for category in DEFAULT_QUOTA:
            needed = parse_numeric(raw_quota.get(category))
            if needed is None or not float(needed).is_integer() or needed < 0:
                errors.append(f'kuota {category} harus bilangan bulat non-negatif')
            else:
                quota[category] = int(needed)
        if question_count is not None and sum(quota.values()) != question_count:
            errors.append('Jumlah kuota kategori harus sama dengan question_count')

    flags = {}
    for name in ('shuffle_options', 'active'):
        flag = _as_flag(payload.get(name))
        if flag is None:
            errors.append(f'{name} harus boolean')
        else:
            flags[name] = flag

    if errors:
        return None, errors
    return {
        'question_count': question_count,
        'duration_minutes': duration,
        'pass_score': float(pass_score),
        'max_attempts': 2,
        'quota': quota,
        'shuffle_options': flags['shuffle_options'],
        'active': flags['active'],
    }, []


def _remaining_seconds(expires_at):
    """Sisa waktu attempt dalam detik; None bila expires_at tidak terbaca."""
    if isinstance(expires_at, datetime):
        expiry = expires_at
    elif isinstance(expires_at, str):
        text = expires_at.strip()
        try:
            expiry = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            try:
                expiry = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return None
    else:
        return None
    now = datetime.now(expiry.tzinfo) if expiry.tzinfo else datetime.now()
    return max(0, int((expiry - now).total_seconds()))


def public_state(case: dict, attempts: list[dict], steps: list[dict],
                 settings: dict) -> dict:
    """Ringkasan status publik untuk pelamar (tanpa kunci, poin, atau NIK)."""
    case, settings = case or {}, settings or {}
    attempts, steps = attempts or [], steps or []

    question_count = int(parse_numeric(settings.get('question_count')) or 0)
    duration = int(parse_numeric(settings.get('duration_minutes')) or 0)
    pass_score = parse_numeric(settings.get('pass_score')) or 0.0
    max_attempts = int(parse_numeric(settings.get('max_attempts')) or MAX_ATTEMPTS)
    official_score = case.get('tkd_score')
    if isinstance(official_score, Decimal):
        official_score = float(official_score)

    counted = ('BERLANGSUNG', 'SELESAI', 'KEDALUWARSA')
    statuses = [str((a or {}).get('status') or '').upper() for a in attempts]
    attempts_used = sum(1 for status in statuses if status in counted)
    active_attempt = None
    for attempt, status in zip(attempts, statuses):
        if status == 'BERLANGSUNG':
            attempt = attempt or {}
            expiry = attempt.get('expires_at')
            active_attempt = {
                'id': attempt.get('id'),
                'expires_at': expiry.isoformat(sep=' ') if isinstance(expiry, datetime) else expiry,
                'remaining_seconds': _remaining_seconds(expiry),
            }
            break

    tkd_steps = [s or {} for s in steps
                 if str((s or {}).get('step_type') or '').upper() == 'TKD']
    excluded = any(str(s.get('status') or '').upper() == 'DIKECUALIKAN'
                   for s in tkd_steps)
    step_completed = any(str(s.get('status') or '').upper() == 'SELESAI'
                         for s in tkd_steps)
    score_number = parse_numeric(official_score)
    passed_flag = case.get('tkd_passed') in (1, True, '1')

    # Urutan keputusan mengikuti kontrak: pengaturan → excl → aktif → skor →
    # lulus → habis → bisa coba → belum.
    if (_as_flag(settings.get('active')) is not True
            or settings.get('bank_ready') is False):
        state = 'SEGERA'
    elif excluded:
        state = 'DIKECUALIKAN'
    elif active_attempt is not None:
        state = 'BERLANGSUNG'
    elif score_number is None and step_completed:
        state = 'SKOR_BELUM_TERCATAT'
    elif passed_flag:
        # `tkd_passed` adalah keputusan saat skor dihitung. Jangan menghitung
        # ulang dengan ambang saat ini: perubahan `pass_score` tidak boleh
        # membalik status historis (spec §5.2/§6.3).
        state = 'LULUS'
    elif attempts_used >= max_attempts:
        state = 'HABIS'
    elif attempts_used >= 1:
        state = 'BISA_COBA'
    else:
        state = 'BELUM'

    if state != 'BERLANGSUNG':
        active_attempt = None
    return {
        'state': state,
        'official_score': official_score,
        'score_source': case.get('tkd_score_source'),
        'attempts_used': attempts_used,
        'max_attempts': max_attempts,
        'active_attempt': active_attempt,
        'can_start': state in ('BELUM', 'BISA_COBA'),
        'pass_score': pass_score,
        'question_count': question_count,
        'duration_minutes': duration,
    }


# ---------------------------------------------------------------------------
# Bank soal: validasi, normalisasi, dan CSV
# ---------------------------------------------------------------------------

CSV_COLUMNS = ('code', 'category', 'type', 'prompt',
               'option_a', 'option_b', 'option_c', 'option_d', 'option_e',
               'correct', 'tolerance', 'points', 'modal_tier', 'active')
# CSV_COLUMNS menyediakan option_a..option_e: validator tidak boleh menerima f.
_OPTION_IDS = tuple('abcde')
_QUESTION_TYPES = ('MCQ', 'NUMERIC', 'SHORT_TEXT', 'PROFILE_TEXT')
_CODE_RE = re.compile(r'[A-Z0-9][A-Z0-9_-]{2,39}')
MAX_CSV_ROWS = 500


def _text(value):
    """Teks terpangkas untuk semua field; None/angka tetap aman."""
    return str(value).strip() if value is not None else ''


def _options_list(value):
    """Terima list/dict/JSON string opsi; selalu kembalikan list of dict."""
    parsed = as_json(value, [])
    if isinstance(parsed, dict):
        parsed = list(parsed.values())
    if not isinstance(parsed, (list, tuple)):
        return []
    return [item if isinstance(item, dict) else {'text': item} for item in parsed]


def _answer_dict(value):
    """Terima dict/JSON string kunci; kunci bukan dict dianggap kosong."""
    parsed = as_json(value)
    return parsed if isinstance(parsed, dict) else {}


def _aliases(value):
    """Alias SHORT_TEXT dari list atau string berbentuk `a|b`."""
    if isinstance(value, str):
        parts = value.split('|')
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return []
    return [_text(part) for part in parts]


def _tolerance_value(answer):
    """Toleransi NUMERIC; kosong berarti 0,5 (nilai bawaan soal)."""
    raw = answer.get('tolerance')
    if raw is None or _text(raw) == '':
        return 0.5
    return parse_numeric(raw)


def _validate_options(options, errors):
    if not 2 <= len(options) <= 5:
        errors.append('MCQ harus memiliki 2–5 opsi')
    seen = set()
    for index, option in enumerate(options, 1):
        option = option if isinstance(option, dict) else {}
        option_id = _text(option.get('id')).lower()
        text = _text(option.get('text'))
        if option_id not in _OPTION_IDS:
            errors.append(f'opsi {index}: id harus salah satu a–e')
        if not text:
            errors.append(f'opsi {index}: teks tidak boleh kosong')
        if option_id and option_id in seen:
            errors.append(f'opsi {index}: id opsi duplikat')
        if option_id:
            seen.add(option_id)


def validate_question(data: dict) -> list[str]:
    """Kembalikan daftar error validasi soal (bahasa Indonesia); [] bila valid.

    Kunci yang kosong/putih tidak pernah dianggap valid, termasuk kunci MCQ
    berisi spasi dan alias SHORT_TEXT berisi spasi saja.
    """
    data = data if isinstance(data, dict) else {}
    errors = []

    code = _text(data.get('code'))
    if not _CODE_RE.fullmatch(code):
        errors.append('code harus 3–40 karakter A-Z/0-9/_/- dan diawali A-Z/0-9')
    category = _text(data.get('category'))
    if category not in CATEGORIES:
        errors.append('category tidak dikenal')
    qtype = _text(data.get('type'))
    if qtype not in _QUESTION_TYPES:
        errors.append('type tidak dikenal')
    prompt = _text(data.get('prompt'))
    if not 1 <= len(prompt) <= 2000:
        errors.append('prompt harus 1–2000 karakter')

    tier = _text(data.get('modal_tier'))
    if tier and tier not in MODAL_TIERS:
        errors.append('modal_tier harus 30k/50k/100k')
    if tier and category != 'HITUNG':
        errors.append('modal_tier hanya boleh untuk kategori HITUNG')
    active = data.get('active')
    if active is not None and _as_flag(active) is None:
        errors.append('active harus 0 atau 1')

    points = parse_numeric(data.get('points'))
    options = _options_list(data.get('options'))
    answer = _answer_dict(data.get('answer'))

    if qtype == 'MCQ':
        _validate_options(options, errors)
        option_ids = {_text(item.get('id')).lower()
                      for item in options if isinstance(item, dict)}
        key = _text(answer.get('option')).lower()
        if not key:
            errors.append('kunci jawaban MCQ tidak boleh kosong')
        elif key not in option_ids:
            errors.append('kunci jawaban MCQ harus salah satu id opsi')
        if points is None or points <= 0:
            errors.append('points harus lebih dari 0')
    elif qtype == 'NUMERIC':
        if parse_numeric(answer.get('value')) is None:
            errors.append('kunci NUMERIC harus berupa angka')
        tolerance = _tolerance_value(answer)
        if tolerance is None or tolerance < 0:
            errors.append('tolerance harus angka non-negatif')
        if points is None or points <= 0:
            errors.append('points harus lebih dari 0')
    elif qtype == 'SHORT_TEXT':
        aliases = _aliases(answer.get('aliases'))
        if not 1 <= len(aliases) <= 10:
            errors.append('SHORT_TEXT perlu 1–10 alias')
        elif any(not alias for alias in aliases):
            errors.append('alias tidak boleh kosong')
        if points is None or points <= 0:
            errors.append('points harus lebih dari 0')
    elif qtype == 'PROFILE_TEXT':
        if category != 'PROFIL':
            errors.append('PROFILE_TEXT hanya boleh untuk kategori PROFIL')
        if as_json(data.get('answer')) is not None:
            errors.append('PROFILE_TEXT tidak memiliki kunci jawaban')
        if points is None or points != 0:
            errors.append('PROFILE_TEXT harus 0 poin')
    return errors


def normalize_question(data: dict) -> dict:
    """Bentuk siap INSERT: options/answer adalah JSON string."""
    data = data if isinstance(data, dict) else {}
    qtype = _text(data.get('type'))
    raw_options = _options_list(data.get('options'))
    raw_answer = _answer_dict(data.get('answer'))

    if qtype == 'MCQ':
        options = [{'id': _text(item.get('id')).lower(), 'text': _text(item.get('text'))}
                   for item in raw_options if isinstance(item, dict)]
        answer = {'option': _text(raw_answer.get('option')).lower()}
    elif qtype == 'NUMERIC':
        options = []
        answer = {'value': parse_numeric(raw_answer.get('value')),
                  'tolerance': _tolerance_value(raw_answer)}
    elif qtype == 'SHORT_TEXT':
        options = []
        answer = {'aliases': [alias for alias in _aliases(raw_answer.get('aliases'))
                              if alias]}
    else:
        options = []
        answer = None

    flag = _as_flag(data.get('active'))
    return {
        'code': _text(data.get('code')),
        'category': _text(data.get('category')),
        'type': qtype,
        'prompt': _text(data.get('prompt')),
        'options': json.dumps(options, ensure_ascii=False),
        'answer': json.dumps(answer, ensure_ascii=False),
        'points': parse_numeric(data.get('points')) or 0.0,
        'modal_tier': _text(data.get('modal_tier')) or None,
        'active': 1 if flag else 0,
        'sort_order': int(parse_numeric(data.get('sort_order')) or 0),
    }


def csv_to_question_rows(text: str) -> tuple[list[dict], list[str]]:
    """Ubah teks CSV menjadi baris soal tervalidasi (active=0) dan error.

    Error memakai prefix `baris N:` dengan nomor baris fisik CSV (header = 1).
    Baris yang tidak valid dibuang, baris yang valid tetap dikembalikan.
    """
    reader = csv.DictReader(io.StringIO((text or '').lstrip('\ufeff')))
    header = reader.fieldnames or []
    if len(header) != len(CSV_COLUMNS) or set(header) != set(CSV_COLUMNS):
        return [], ['baris 1: header harus ' + ','.join(CSV_COLUMNS)]

    rows, errors = [], []
    for index, raw in enumerate(reader, 1):
        line = reader.line_num
        if index > MAX_CSV_ROWS:
            errors.append(f'baris {line}: CSV maksimal {MAX_CSV_ROWS} baris soal')
            break
        raw = raw or {}
        qtype = _text(raw.get('type'))
        options = []
        if qtype == 'MCQ':
            for option_id in _OPTION_IDS:
                label = _text(raw.get('option_' + option_id))
                if label:
                    options.append({'id': option_id, 'text': label})
        answer = None
        if qtype == 'MCQ':
            answer = {'option': _text(raw.get('correct')).lower()}
        elif qtype == 'NUMERIC':
            answer = {'value': parse_numeric(_text(raw.get('correct'))),
                      'tolerance': _tolerance_value({'tolerance': _text(raw.get('tolerance'))})}
        elif qtype == 'SHORT_TEXT':
            answer = {'aliases': [alias for alias in _aliases(_text(raw.get('correct')))
                                  if alias]}
        row = {
            'code': _text(raw.get('code')),
            'category': _text(raw.get('category')),
            'type': qtype,
            'prompt': _text(raw.get('prompt')),
            'options': options,
            'answer': answer,
            'points': parse_numeric(_text(raw.get('points'))),
            'modal_tier': _text(raw.get('modal_tier')) or None,
            'active': 0,
            'sort_order': index,
        }
        problems = validate_question(row)
        if problems:
            errors.extend(f'baris {line}: {problem}' for problem in problems)
            continue
        rows.append(row)
    return rows, errors


def import_rows(existing: dict[str, dict], rows: list[dict],
                update_drafts: bool) -> dict:
    """Rencana impor berdasarkan kode: insert/update/skip (validasi di CSV)."""
    existing = existing if isinstance(existing, dict) else {}
    plan = {'insert': [], 'update': [], 'skip': [], 'errors': []}
    for row in rows or []:
        code = _text((row or {}).get('code'))
        current = existing.get(code) or {}
        if not current:
            plan['insert'].append(code)
        elif _as_flag(current.get('active')) is True:
            plan['skip'].append(code)
        elif update_drafts:
            plan['update'].append(code)
        else:
            plan['skip'].append(code)
    return plan


def _number_text(value):
    """Angka untuk kolom CSV tanpa `.0` yang mengganggu kunci."""
    number = parse_numeric(value)
    if number is None:
        return ''
    return str(int(number)) if float(number).is_integer() else repr(number)


def question_row_to_csv(row: dict) -> list[str]:
    """Kebalikan `csv_to_question_rows`; aman untuk baris SELECT parsial."""
    row = row or {}
    values = {column: '' for column in CSV_COLUMNS}
    values['code'] = _text(row.get('code'))
    values['category'] = _text(row.get('category'))
    values['type'] = _text(row.get('type'))
    values['prompt'] = _text(row.get('prompt'))

    options = _options_list(row.get('options'))
    for option in options:
        if not isinstance(option, dict):
            continue
        option_id = _text(option.get('id')).lower()
        if option_id in _OPTION_IDS and not values['option_' + option_id]:
            values['option_' + option_id] = _text(option.get('text'))

    qtype = values['type']
    answer = _answer_dict(row.get('answer'))
    if qtype == 'MCQ':
        values['correct'] = _text(answer.get('option')).lower()
    elif qtype == 'NUMERIC':
        values['correct'] = _number_text(answer.get('value'))
        values['tolerance'] = _number_text(answer.get('tolerance'))
    elif qtype == 'SHORT_TEXT':
        values['correct'] = '|'.join(alias for alias in _aliases(answer.get('aliases'))
                                     if alias)
    values['points'] = _number_text(row.get('points'))
    values['modal_tier'] = _text(row.get('modal_tier'))
    values['active'] = 1 if _as_flag(row.get('active')) else 0
    return [values[column] for column in CSV_COLUMNS]

