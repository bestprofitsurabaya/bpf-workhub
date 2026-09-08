/* BPF WorkHub — Diagram Alir Sistem: interaksi (nav, highlight seksi aktif, zoom). */
(function () {
  'use strict'
  var toc = document.querySelector('#toc')
  var secs = Array.prototype.slice.call(document.querySelectorAll('section'))

  // Nav: klik tombol → scroll ke seksi
  if (toc) {
    for (const b of toc.querySelectorAll('button')) {
      b.addEventListener('click', () => {
        var el = document.getElementById(b.dataset.s)
        if (el) el.scrollIntoView({ behavior: 'smooth' })
      })
    }
  }

  // Highlight seksi aktif saat scroll
  if ('IntersectionObserver' in window) {
    var sp = new IntersectionObserver(function (es) {
      for (const e of es) {
        if (e.isIntersecting) {
          for (const b of toc.querySelectorAll('button')) {
            b.className = (b.dataset.s === e.target.id) ? 'on' : ''
          }
        }
      }
    }, { rootMargin: '-40% 0px -55% 0px' })
    secs.forEach(function (s) { sp.observe(s) })
  }

  // Zoom +/- / reset untuk semua SVG
  var z = 1
  function applyZoom() {
    for (const s of secs) {
      var w = s.querySelector('svg')
      if (w) { w.style.transform = 'scale(' + z + ')'; w.style.transformOrigin = '0 0' }
    }
  }
  var zb = document.createElement('div')
  zb.className = 'zoom'
  zb.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:50;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:4px 10px;font-size:12px;color:#cbd5e1;'
  zb.innerHTML = '<span>&#128269; </span><button id="zi">+</button> <button id="zo">&minus;</button> <button id="zr">100%</button>'
  document.body.appendChild(zb)
  document.getElementById('zi').addEventListener('click', function () { z = Math.min(2, z + 0.2); applyZoom() })
  document.getElementById('zo').addEventListener('click', function () { z = Math.max(0.5, z - 0.2); applyZoom() })
  document.getElementById('zr').addEventListener('click', function () { z = 1; applyZoom() })
})()
