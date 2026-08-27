#!/usr/bin/env python3
"""
Create linkable content pages on BPF Surabaya WordPress site.

These pages are designed to attract natural backlinks from:
- Financial education sites
- Student/research papers
- Other financial blogs
- Forum discussions
- Google featured snippets

Run: python3 scripts/create_linkable_pages.py
"""

import json
import os
import sys
import requests
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_scraper')
WP_SITES_FILE = os.path.join(DATA_DIR, 'wp_sites.json')

def load_sites():
    with open(WP_SITES_FILE) as f:
        return json.load(f)

def get_session():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 BPF-LinkablePages/1.0'})
    return s

def login(site, session):
    """Login via app password (preferred) or basic auth."""
    wp_base = site['wp_url'].split('/wp-json')[0]
    username = site.get('username', '')
    
    # Try app password first (works for Surabaya), then basic auth
    for pw in [site.get('app_password', ''), site.get('basic_password', '')]:
        if not pw:
            continue
        r = session.get(f"{wp_base}/wp-json/wp/v2/users/me", auth=(username, pw), timeout=15)
        if r.status_code == 200:
            nonce = r.headers.get('X-WP-Nonce', '')
            print(f"  Auth method: {'app_password' if pw == site.get('app_password') else 'basic_auth'}")
            return True, wp_base, (username, pw), nonce
    
    print(f"  Login failed: tried both auth methods")
    return False, wp_base, None, None

def create_page(wp_base, auth, nonce, title, slug, content, status='publish'):
    """Create a WordPress page."""
    url = f"{wp_base}/wp-json/wp/v2/pages"
    headers = {'Content-Type': 'application/json'}
    if nonce:
        headers['X-WP-Nonce'] = nonce
    
    data = {
        'title': title,
        'slug': slug,
        'content': content,
        'status': status,
    }
    
    r = requests.post(url, json=data, auth=auth, headers=headers, timeout=30)
    if r.status_code in (200, 201):
        page = r.json()
        print(f"  ✅ Created: {title} (ID: {page['id']})")
        return page
    else:
        print(f"  ❌ Failed: {title} (HTTP {r.status_code}): {r.text[:200]}")
        return None


# ══════════════════════════════════════════════════════════════════════
# PAGE 1: KALKULATOR EMAS
# ══════════════════════════════════════════════════════════════════════

KALKULATOR_EMAS_HTML = '''<article style="max-width:800px;margin:0 auto;font-family:Georgia,serif;line-height:1.8;color:#1f2937;">

<h1 style="font-size:28px;color:#1a1a1a;margin-bottom:8px;">Kalkulator Emas Antam Gratis</h1>
<p style="color:#64748b;font-size:14px;margin-bottom:24px;">📅 Update: ''' + datetime.now().strftime('%d %B %Y') + ''' | Hitung harga beli &amp; jual emas secara instan</p>

<div style="background:linear-gradient(135deg,#fef3c7,#fde68a);border:2px solid #f59e0b;border-radius:16px;padding:24px;margin-bottom:24px;">
  <h2 style="margin:0 0 16px;font-size:20px;color:#92400e;">🧮 Kalkulator Harga Emas</h2>
  
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
    <div>
      <label style="display:block;font-weight:600;margin-bottom:4px;color:#78350f;">Berat (gram)</label>
      <input type="number" id="emasBerat" value="1" min="0.5" step="0.5" 
        style="width:100%;padding:12px;border:2px solid #d97706;border-radius:8px;font-size:18px;font-weight:bold;">
    </div>
    <div>
      <label style="display:block;font-weight:600;margin-bottom:4px;color:#78350f;">Harga per Gram (Rp)</label>
      <input type="text" id="emasHarga" value="2723000" 
        style="width:100%;padding:12px;border:2px solid #d97706;border-radius:8px;font-size:18px;font-weight:bold;">
    </div>
  </div>
  
  <div style="background:white;border-radius:12px;padding:16px;text-align:center;">
    <div style="font-size:14px;color:#92400e;">Total Harga Beli</div>
    <div id="emasTotal" style="font-size:32px;font-weight:bold;color:#b45309;">Rp 2.723.000</div>
    <div style="font-size:12px;color:#a16207;margin-top:4px;">*Belum termasuk PPh 22 (0,45% dengan NPWP)</div>
  </div>
  
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px;">
    <div style="background:white;border-radius:8px;padding:12px;text-align:center;">
      <div style="font-size:12px;color:#92400e;">Harga Buyback</div>
      <div id="emasBuyback" style="font-size:18px;font-weight:bold;color:#059669;">Rp 2.583.000</div>
    </div>
    <div style="background:white;border-radius:8px;padding:12px;text-align:center;">
      <div style="font-size:12px;color:#92400e;">PPh 22 (0,45%)</div>
      <div id="emasPajak" style="font-size:18px;font-weight:bold;color:#dc2626;">Rp 12.254</div>
    </div>
  </div>
</div>

<script>
function hitungEmas() {
  var berat = parseFloat(document.getElementById('emasBerat').value) || 1;
  var hargaStr = document.getElementById('emasHarga').value.replace(/[^0-9]/g, '');
  var harga = parseInt(hargaStr) || 2723000;
  
  var total = berat * harga;
  var pajak = Math.round(total * 0.0045);
  var buybackRate = 0.948; // ~94.8% buyback rate
  var buyback = Math.round(total * buybackRate);
  
  document.getElementById('emasTotal').textContent = 'Rp ' + total.toLocaleString('id-ID');
  document.getElementById('emasPajak').textContent = 'Rp ' + pajak.toLocaleString('id-ID');
  document.getElementById('emasBuyback').textContent = 'Rp ' + buyback.toLocaleString('id-ID');
}

document.getElementById('emasBerat').addEventListener('input', hitungEmas);
document.getElementById('emasHarga').addEventListener('input', hitungEmas);
hitungEmas();
</script>

<h2 style="font-size:22px;margin-top:32px;">Cara Menggunakan Kalkulator Emas</h2>
<ol>
  <li><strong>Masukkan berat emas</strong> dalam gram (minimal 0,5 gram)</li>
  <li><strong>Masukkan harga per gram</strong> sesuai harga Antam terkini</li>
  <li><strong>Lihat hasil</strong> — total harga beli, harga buyback, dan estimasi PPh 22</li>
</ol>

<h2 style="font-size:22px;margin-top:32px;">Harga Emas Antam Hari Ini</h2>
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;margin:16px 0;">
  <thead>
    <tr style="background:#f8fafc;">
      <th style="padding:12px;text-align:left;border-bottom:2px solid #e2e8f0;">Berat</th>
      <th style="padding:12px;text-align:right;border-bottom:2px solid #e2e8f0;">Harga Beli</th>
      <th style="padding:12px;text-align:right;border-bottom:2px solid #e2e8f0;">Harga Buyback</th>
    </tr>
  </thead>
  <tbody>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;">0,5 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;">Rp 1.411.500</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;color:#059669;">Rp 1.339.102</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;background:#fafafa;">1 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;background:#fafafa;">Rp 2.723.000</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;background:#fafafa;color:#059669;">Rp 2.583.000</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;">5 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;">Rp 13.390.000</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;color:#059669;">Rp 12.693.720</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;background:#fafafa;">10 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;background:#fafafa;">Rp 26.725.000</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;background:#fafafa;color:#059669;">Rp 25.335.300</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;">25 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;">Rp 66.687.000</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;color:#059669;">Rp 63.219.276</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;background:#fafafa;">50 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;background:#fafafa;">Rp 133.295.000</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;background:#fafafa;color:#059669;">Rp 126.363.660</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;">100 gram</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;">Rp 266.512.000</td><td style="padding:10px 12px;text-align:right;border-bottom:1px solid #f1f5f9;color:#059669;">Rp 252.653.376</td></tr>
    <tr><td style="padding:10px 12px;background:#fafafa;">1.000 gram (1 kg)</td><td style="padding:10px 12px;text-align:right;background:#fafafa;font-weight:bold;">Rp 2.663.600.000</td><td style="padding:10px 12px;text-align:right;background:#fafafa;color:#059669;font-weight:bold;">Rp 2.525.092.800</td></tr>
  </tbody>
</table>
</div>
<p style="font-size:13px;color:#64748b;">*Harga dapat berubah sewaktu-waktu. Hubungi PT Bestprofit Futures untuk harga terkini.</p>

<h2 style="font-size:22px;margin-top:32px;">FAQ Kalkulator Emas</h2>

<h3 style="font-size:18px;">Berapa PPh 22 untuk pembelian emas?</h3>
<p>Berdasarkan PMK Nomor 34 Tahun 2017, pembelian emas batangan dikenakan PPh 22 sebesar <strong>0,9%</strong>. Jika menyertakan NPWP, tarifnya lebih rendah yaitu <strong>0,45%</strong>.</p>

<h3 style="font-size:18px;">Apa itu harga buyback?</h3>
<p>Harga buyback adalah harga di mana Antam akan membeli kembali emas Anda. Biasanya <strong>sekitar 94-95%</strong> dari harga beli. Artinya jika Anda menjual emas 1 gram yang dibeli Rp 2.723.000, Antam akan membelinya sekitar Rp 2.583.000.</p>

<h3 style="font-size:18px;">Berapa minimal pembelian emas Antam?</h3>
<p>Pembelian emas Antam minimal <strong>0,5 gram</strong>. Untuk ukuran terkecil (0,5 gram), harga beli sekitar Rp 1.411.500.</p>

<div style="margin-top:32px;padding:16px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;">
  <p style="margin:0;font-size:14px;color:#0369a1;">💡 <strong>Tips:</strong> Gunakan kalkulator ini untuk membandingkan harga sebelum membeli emas. Selalu cek harga terkini di <a href="https://www.logammulia.com/" target="_blank" rel="nofollow">Logam Mulia Antam</a>.</p>
</div>

</article>'''


# ══════════════════════════════════════════════════════════════════════
# PAGE 2: GLOSSARIUM TRADING
# ══════════════════════════════════════════════════════════════════════

GLOSSARIUM_HTML = '''<article style="max-width:800px;margin:0 auto;font-family:Georgia,serif;line-height:1.8;color:#1f2937;">

<h1 style="font-size:28px;color:#1a1a1a;margin-bottom:8px;">Glossarium Trading &amp; Investasi Lengkap</h1>
<p style="color:#64748b;font-size:14px;margin-bottom:24px;">Kamus istilah trading, forex, komoditas, dan investasi untuk pemula hingga profesional</p>

<div style="background:#f8fafc;border-radius:12px;padding:16px;margin-bottom:24px;">
  <p style="margin:0;font-size:14px;color:#475569;">📌 <strong>Daftar Isi:</strong>
  <a href="#a">A</a> · <a href="#b">B</a> · <a href="#c">C</a> · <a href="#d">D</a> · <a href="#f">F</a> · <a href="#g">G</a> · <a href="#h">H</a> · <a href="#i">I</a> · <a href="#j">J</a> · <a href="#k">K</a> · <a href="#l">L</a> · <a href="#m">M</a> · <a href="#n">N</a> · <a href="#o">O</a> · <a href="#p">P</a> · <a href="#q">Q</a> · <a href="#r">R</a> · <a href="#s">S</a> · <a href="#t">T</a> · <a href="#u">U</a> · <a href="#v">V</a> · <a href="#w">W</a></p>
</div>

<!-- A -->
<h2 id="a" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">A</h2>

<h3 style="font-size:17px;">Ask Price (Harga Penawaran)</h3>
<p>Harga yang ditawarkan oleh penjual/pembuat pasar (market maker) untuk suatu instrumen. Ask price selalu lebih tinggi dari bid price. Selisih antara bid dan ask disebut spread.</p>

<h3 style="font-size:17px;">Arbitrase</h3>
<p>Strategi trading yang memanfaatkan perbedaan harga antara dua atau lebih pasar untuk mendapatkan keuntungan tanpa risiko. Contoh: membeli emas di pasar A seharga Rp 100 dan langsung menjualnya di pasar B seharga Rp 105.</p>

<h3 style="font-size:17px;">ATR (Average True Range)</h3>
<p>Indikator teknikal yang mengukur volatilitas pasar dengan menghitung rentang harga rata-rata selama periode tertentu. Semakin tinggi ATR, semakin tinggi volatilitasnya.</p>

<!-- B -->
<h2 id="b" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">B</h2>

<h3 style="font-size:17px;">Backtest</h3>
<p>Proses menguji strategi trading menggunakan data historis untuk melihat bagaimana strategi tersebut akan berperforma di masa lalu. Backtest membantu mengevaluasi efektivitas strategi sebelum digunakan di pasar nyata.</p>

<h3 style="font-size:17px;">Bear Market (Pasar Bear)</h3>
<p>Kondisi pasar yang mengalami penurunan harga secara signifikan dan berkelanjutan, biasanya lebih dari 20% dari puncak sebelumnya. Kebalikan dari bull market.</p>

<h3 style="font-size:17px;">Bid Price</h3>
<p>Harga yang ditawarkan oleh pembeli untuk suatu instrumen. Bid price selalu lebih rendah dari ask price.</p>

<h3 style="font-size:17px;">Breakout</h3>
<p>Kondisi ketika harga menembus level support atau resistance dengan volume yang tinggi. Breakout sering kali diikuti oleh pergerakan harga yang signifikan ke arah penembusan.</p>

<h3 style="font-size:17px;">Bull Market (Pasar Bull)</h3>
<p>Kondisi pasar yang mengalami kenaikan harga secara signifikan dan berkelanjutan. Dinamakan "bull" karena sapi menanduk ke atas.</p>

<!-- C -->
<h2 id="c" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">C</h2>

<h3 style="font-size:17px;">Carry Trade</h3>
<p>Strategi meminjam mata uang dengan suku bunga rendah untuk menginvestasikannya di mata uang dengan suku bunga lebih tinggi. Keuntungan berasal dari selisih suku bunga (carry).</p>

<h3 style="font-size:17px;">Candlestick</h3>
<p>Jenis chart yang menampilkan harga open, high, low, dan close dalam satu batang. Body candle menunjukkan selisih open-close, shadow menunjukkan high-low.</p>

<h3 style="font-size:17px;">CFD (Contract for Difference)</h3>
<p>Kontrak derivative yang memungkinkan trader untuk berspekulasi pada pergerakan harga tanpa memiliki aset dasarnya. Keuntungan/kerugian berdasarkan selisih harga saat pembukaan dan penutupan kontrak.</p>

<h3 style="font-size:17px;">Commission (Komisi)</h3>
<p>Biaya yang dikenakan oleh broker untuk setiap transaksi. Komisi bisa berupa fixed fee atau persentase dari nilai transaksi.</p>

<h3 style="font-size:17px;">Currency Pair</h3>
<p>Pasangan mata uang yang diperdagangkan dalam forex. Contoh: EUR/USD, GBP/USD, USD/JPY. Mata uang pertama disebut base currency, yang kedua quote currency.</p>

<!-- D -->
<h2 id="d" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">D</h2>

<h3 style="font-size:17px;">Day Trading</h3>
<p>Strategi trading di mana posisi dibuka dan ditutup dalam hari yang sama. Day trader tidak menahan posisi overnight untuk menghindari risiko gap harga.</p>

<h3 style="font-size:17px;">Demo Account</h3>
<p>Akun trading simulasi yang menggunakan uang virtual. Memungkinkan trader pemula untuk belajar trading tanpa risiko kehilangan uang nyata.</p>

<h3 style="font-size:17px;">Drawdown</h3>
<p>Penurunan nilai akun trading dari puncak (peak) ke titik terendah. Drawdown diukur dalam persentase dan menunjukkan seberapa besar kerugian yang dialami.</p>

<!-- F -->
<h2 id="f" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">F</h2>

<h3 style="font-size:17px;">Forex (Foreign Exchange)</h3>
<p>Pasar global untuk perdagangan mata uang. Forex adalah pasar terbesar di dunia dengan volume perdagangan harian mencapai $6,6 triliun (2024).</p>

<h3 style="font-size:17px;">Fundamental Analysis</h3>
<p>Analisis yang berdasarkan faktor-faktor ekonomi, keuangan, dan geopolitik untuk menentukan nilai intrinsik suatu aset. Contoh: data inflasi, suku bunga, laporan keuangan perusahaan.</p>

<h3 style="font-size:17px;">Futures (Perdagangan Berjangka)</h3>
<p>Kontrak standar untuk membeli atau menjual suatu aset pada harga tertentu di masa depan. Di Indonesia, perdagangan berjangka diawasi oleh BAPPEBTI dan diperdagangkan di Bursa Berjangka Jakarta (BBJ) dan ICDX.</p>

<!-- G -->
<h2 id="g" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">G</h2>

<h3 style="font-size:17px;">Gap</h3>
<p>Perbedaan harga antara penutupan sesi sebelumnya dengan pembukaan sesi berikutnya. Gap bisa terjadi karena berita penting atau pergerakan pasar di luar jam trading.</p>

<h3 style="font-size:17px;">Going Long</h3>
<p>Membeli suatu instrumen dengan harapan harga akan naik. Sebaliknya, going short berarti menjual dengan harapan harga akan turun.</p>

<!-- H -->
<h2 id="h" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">H</h2>

<h3 style="font-size:17px;">Hedge (Lindung Nilai)</h3>
<p>Strategi untuk melindungi diri dari risiko pergerakan harga yang merugikan. Contoh: membeli kontrak futures emas untuk melindungi portofolio saham dari penurunan pasar.</p>

<h3 style="font-size:17px;">High Frequency Trading (HFT)</h3>
<p>Strategi trading yang menggunakan komputer berkecepatan tinggi untuk melakukan transaksi dalam milidetik. HFT memanfaatkan perbedaan harga kecil dalam waktu sangat singkat.</p>

<!-- I -->
<h2 id="i" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">I</h2>

<h3 style="font-size:17px;">Inflation (Inflasi)</h3>
<p>Kenaikan harga barang dan jasa secara umum dan terus-menerus. Inflasi tinggi biasanya mendorong harga emas naik karena emas dianggap sebagai lindung nilai terhadap inflasi.</p>

<h3 style="font-size:17px;">Interest Rate (Suku Bunga)</h3>
<p>Biaya meminjam uang atau imbalan dari menabung. Suku bunga yang lebih tinggi biasanya memperkuat mata uang dan melemahkan harga emas.</p>

<h3 style="font-size:17px;">IB (Introducing Broker)</h3>
<p>Pihak yang memperkenalkan klien kepada broker dan menerima komisi dari setiap transaksi klien tersebut. IB berperan sebagai perantara antara trader dan broker.</p>

<!-- J -->
<h2 id="j" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">J</h2>

<h3 style="font-size:17px;">Jarvis (Just A Rather Very Intelligent System)</h3>
<p>Istilah populer untuk sistem trading otomatis atau robot trading yang menggunakan algoritma untuk membuat keputusan trading.</p>

<!-- K -->
<h2 id="k" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">K</h2>

<h3 style="font-size:17px;">Kelly Criterion</h3>
<p>Rumus matematika untuk menentukan ukuran posisi optimal berdasarkan probabilitas menang dan rasio risk-reward. Membantu mengoptimalkan pertumbuhan modal jangka panjang.</p>

<h3 style="font-size:17px;">Kontrak Berjangka</h3>
<p>Kontrak standar yang diperdagangkan di bursa berjangka untuk membeli atau menjual aset tertentu pada harga dan waktu yang sudah ditentukan. Contoh: kontrak emas, minyak kelapa sawit (CPO), valuta asing.</p>

<!-- L -->
<h2 id="l" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">L</h2>

<h3 style="font-size:17px;">Leverage (Daya Ungkit)</h3>
<p>Penggunaan dana pinjaman untuk meningkatkan potensi keuntungan (dan risiko). Contoh: leverage 1:100 berarti dengan margin $100, Anda bisa bertransaksi senilai $10.000.</p>

<h3 style="font-size:17px;">Limit Order</h3>
<p>Order untuk membeli atau menjual pada harga tertentu atau lebih baik. Buy limit dieksekusi pada harga yang lebih rendah, sell limit pada harga yang lebih tinggi.</p>

<h3 style="font-size:17px;">Liquidation</h3>
<p>Proses penutupan paksa posisi trading oleh broker karena margin yang tidak mencukupi (margin call). Terjadi saat kerugian melebihi margin yang tersedia.</p>

<!-- M -->
<h2 id="m" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">M</h2>

<h3 style="font-size:17px;">Margin</h3>
<p>Jaminan yang harus disetorkan trader kepada broker untuk membuka posisi. Margin bukan biaya, melainkan jaminan yang akan dikembalikan saat posisi ditutup.</p>

<h3 style="font-size:17px;">Margin Call</h3>
<p>Kondisi ketika margin tidak mencukupi untuk menahan posisi trading yang merugikan. Trader harus menambah dana (margin) atau posisi akan dilikuidasi.</p>

<h3 style="font-size:17px;">Market Order</h3>
<p>Order untuk membeli atau menjual segera pada harga pasar terkini. Market order dijamin dieksekusi tapi harga bisa berubah dari yang diharapkan.</p>

<h3 style="font-size:17px;">Moving Average (MA)</h3>
<p>Indikator teknikal yang menampilkan rata-rata harga selama periode tertentu. MA membantu mengidentifikasi tren dan level support/resistance.</p>

<!-- N -->
<h2 id="n" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">N</h2>

<h3 style="font-size:17px;">Non-Farm Payrolls (NFP)</h3>
<p>Data ketenagakerjaan AS yang dirilis setiap bulan. NFP menunjukkan jumlah pekerjaan baru yang diciptakan di luar sektor pertanian. Data ini sangat mempengaruhi pergerakan USD dan emas.</p>

<h3 style="font-size:17px;">News Trading</h3>
<p>Strategi trading berdasarkan rilis berita ekonomi penting. Trader mencoba memanfaatkan pergerakan harga cepat yang terjadi setelah berita dirilis.</p>

<!-- O -->
<h2 id="o" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">O</h2>

<h3 style="font-size:17px;">OCO (One Cancels the Other)</h3>
<p>Jenis order yang menggabungkan stop loss dan take profit. Saat salah satu tercapai, yang lain otomatis dibatalkan.</p>

<h3 style="font-size:17px;">Overbought</h3>
<p>Kondisi teknikal ketika harga telah naik terlalu cepat dan terlalu tinggi, sehingga kemungkinan akan mengalami koreksi. Indikator seperti RSI di atas 70 menunjukkan overbought.</p>

<!-- P -->
<h2 id="p" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">P</h2>

<h3 style="font-size:17px;">Pip (Percentage in Point)</h3>
<p>Satuan terkecil perubahan harga dalam forex. Untuk pasangan mata uang dengan 4 desimal, 1 pip = 0,0001. Untuk pasangan dengan JPY, 1 pip = 0,01.</p>

<h3 style="font-size:17px;">Position Sizing</h3>
<p>Menentukan ukuran posisi trading berdasarkan risiko yang mau ditanggung. Position sizing membantu mengontrol risiko agar tidak terlalu besar.</p>

<h3 style="font-size:17px;">PPh 22</h3>
<p>Pajak Penghasilan Pasal 22 yang dikenakan pada pembelian emas batangan. Sesuai PMK 34/2017, tarifnya 0,9% (tanpa NPWP) atau 0,45% (dengan NPWP).</p>

<!-- Q -->
<h2 id="q" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">Q</h2>

<h3 style="font-size:17px;">Quote Currency</h3>
<p>Mata uang kedua dalam pasangan mata uang. Contoh: dalam EUR/USD, USD adalah quote currency. Harga menunjukkan berapa USD yang diperlukan untuk membeli 1 EUR.</p>

<!-- R -->
<h2 id="r" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">R</h2>

<h3 style="font-size:17px;">Risk Management</h3>
<p>Sistem dan strategi untuk mengontrol risiko trading. Termasuk penggunaan stop loss, position sizing, dan diversifikasi. Risk management adalah kunci keberhasilan trading jangka panjang.</p>

<h3 style="font-size:17px;">RSI (Relative Strength Index)</h3>
<p>Indikator momentum yang mengukur kecepatan dan perubahan pergerakan harga. RSI berkisar antara 0-100. Di atas 70 = overbought, di bawah 30 = oversold.</p>

<!-- S -->
<h2 id="s" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">S</h2>

<h3 style="font-size:17px;">Scalping</h3>
<p>Strategi trading jangka sangat pendek yang memanfaatkan pergerakan harga kecil. Scalper membuka dan menutup posisi dalam hitungan detik hingga menit.</p>

<h3 style="font-size:17px;">Spread</h3>
<p>Selisih antara bid price dan ask price. Spread adalah biaya trading yang dikenakan oleh broker. Semakin kecil spread, semakin murah biaya tradingnya.</p>

<h3 style="font-size:17px;">Stop Loss</h3>
<p>Order untuk menutup posisi secara otomatis saat harga mencapai level tertentu untuk membatasi kerugian. Stop loss adalah alat risk management yang paling penting.</p>

<h3 style="font-size:17px;">Support &amp; Resistance</h3>
<p>Support = level harga di mana permintaan cukup kuat untuk mencegah harga turun lebih lanjut. Resistance = level harga di mana penawaran cukup kuat untuk mencegah harga naik lebih lanjut.</p>

<!-- T -->
<h2 id="t" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">T</h2>

<h3 style="font-size:17px;">Take Profit</h3>
<p>Order untuk menutup posisi secara otomatis saat harga mencapai level keuntungan yang diinginkan. Take profit membantu mengunci keuntungan tanpa perlu memantau pasar terus-menerus.</p>

<h3 style="font-size:17px;">Technical Analysis</h3>
<p>Analisis pergerakan harga menggunakan chart, indikator, dan pola-pola harga untuk memprediksi pergerakan harga selanjutnya. Berbeda dengan fundamental analysis yang berdasarkan data ekonomi.</p>

<h3 style="font-size:17px;">Trailing Stop</h3>
<p>Stop loss yang bergerak mengikuti pergerakan harga. Trailing stop mengunci keuntungan saat harga bergerak sesuai prediksi, namun tetap melindungi dari kerugian jika harga berbalik.</p>

<h3 style="font-size:17px;">Trend</h3>
<p>Arah pergerakan harga secara umum. Tiga jenis tren: uptrend (naik), downtrend (turun), dan sideways (datar). "Trend is your friend" — trading searah tren lebih menguntungkan.</p>

<!-- U -->
<h2 id="u" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">U</h2>

<h3 style="font-size:17px;">USD (United States Dollar)</h3>
<p>Mata uang cadangan dunia yang paling banyak diperdagangkan dalam forex. Harga emas umumnya dikutip dalam USD per troy ounce.</p>

<!-- V -->
<h2 id="v" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">V</h2>

<h3 style="font-size:17px;">Volatility (Volatilitas)</h3>
<p>Tingkat fluktuasi harga suatu instrumen dalam periode waktu tertentu. Volatilitas tinggi = peluang besar tapi juga risiko besar. Volatilitas rendah = harga stabil tapi peluang terbatas.</p>

<!-- W -->
<h2 id="w" style="font-size:22px;color:#1e40af;border-bottom:2px solid #3b82f6;padding-bottom:8px;">W</h2>

<h3 style="font-size:17px;">Whipsaw</h3>
<p>Kondisi pasar di mana harga bergerak naik-turun dengan cepat dan tidak menentu. Whipsaw sering kali menyebabkan stop loss terkena sebelum harga bergerak ke arah yang diharapkan.</p>

<div style="margin-top:32px;padding:16px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;">
  <p style="margin:0;font-size:14px;color:#166534;">📚 <strong>Mau belajar lebih lanjut?</strong> Baca artikel trading kami di <a href="https://best-profit-futures-surabaya.com/" style="color:#16a34a;font-weight:600;">Beranda</a> atau daftar <a href="https://demo.bestprofit-futures.com/" target="_blank" rel="nofollow" style="color:#16a34a;font-weight:600;">Demo Account</a> gratis.</p>
</div>

</article>'''


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    sites = load_sites()
    site_name = 'BPF Surabaya'
    
    if site_name not in sites:
        print(f"Site '{site_name}' not found in wp_sites.json")
        return
    
    site = sites[site_name]
    session = get_session()
    
    print(f"🔐 Login ke {site_name}...")
    ok, wp_base, auth, nonce = login(site, session)
    if not ok:
        print("❌ Login gagal!")
        return
    print(f"✅ Login berhasil ke {wp_base}")
    
    pages = [
        {
            'title': 'Kalkulator Emas Antam Gratis - Hitung Harga Beli & Jual',
            'slug': 'kalkulator-emas',
            'content': KALKULATOR_EMAS_HTML,
        },
        {
            'title': 'Glossarium Trading & Investasi Lengkap - Kamus Istilah Forex',
            'slug': 'glossarium-trading',
            'content': GLOSSARIUM_HTML,
        },
    ]
    
    print(f"\n📄 Membuat {len(pages)} halaman linkable...")
    for page_data in pages:
        create_page(wp_base, auth, nonce, **page_data)
    
    print("\n✅ Selesai! Halaman linkable sudah dibuat.")
    print("   Halaman ini dirancang untuk menarik backlink dari:")
    print("   - Situs edukasi keuangan")
    print("   - Paper/penelitian mahasiswa")
    print("   - Forum trading & investasi")
    print("   - Blog keuangan lainnya")
    print("   - Google featured snippets (kalkulator & glossary)")


if __name__ == '__main__':
    main()
