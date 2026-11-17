import importlib.util
import os
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SPEC = importlib.util.spec_from_file_location('k', '/tmp/ktp_ocr_v21110.py')
K = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(K)


def base_image():
    img = Image.new('RGB', (1200, 760), (250, 250, 248))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 30)
    fb = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 34)
    fs = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 22)
    d.text((70, 40), 'PROVINSI JAWA TIMUR', fill=(20, 20, 20), font=fb)
    d.text((70, 85), 'KOTA SURABAYA', fill=(20, 20, 20), font=fb)
    d.text((70, 170), 'NIK', fill=(20, 20, 20), font=f)
    d.text((170, 170), ': 3509 1901 0295 0003', fill=(20, 20, 20), font=f)
    d.text((70, 240), 'Nama', fill=(20, 20, 20), font=f)
    d.text((200, 240), ': BILI DARNANTO SUSILO', fill=(20, 20, 20), font=f)
    d.text((70, 300), 'Tempat/Tgl Lahir', fill=(20, 20, 20), font=fs)
    d.text((360, 300), ': SURABAYA, 19-01-1995', fill=(20, 20, 20), font=fs)
    d.text((70, 350), 'Jenis Kelamin', fill=(20, 20, 20), font=fs)
    d.text((360, 350), ': LAKI-LAKI', fill=(20, 20, 20), font=fs)
    return img


for mode in ('clean', 'blur', 'jpeg', 'dark', 'phone'):
    from PIL import ImageEnhance, ImageOps
    img = base_image()
    if mode == 'blur':
        img = img.filter(ImageFilter.GaussianBlur(1.6))
    if mode == 'jpeg':
        import io
        buf = io.BytesIO(); img.save(buf, 'JPEG', quality=35); buf.seek(0)
        img = Image.open(buf)
    if mode == 'dark':
        img = ImageEnhance.Brightness(img).enhance(0.55).convert('RGB')
        img = ImageEnhance.Contrast(img).enhance(0.6).convert('RGB')
    if mode == 'phone':
        img = img.rotate(2.0, resample=Image.BICUBIC, expand=True, fillcolor=(245, 245, 242))
        buf = io.BytesIO(); img.save(buf, 'JPEG', quality=50); buf.seek(0)
        img = Image.open(buf)
    p = f'/tmp/s2_{mode}.jpg'
    img.save(p, 'JPEG', quality=92)
    t = time.time()
    r = K.extract_ktp(p)
    print(f'{mode:6} {time.time()-t:5.2f}s nik={r["nik"]} nama={r["nama"]!r} conf={r["confidence"]}')
