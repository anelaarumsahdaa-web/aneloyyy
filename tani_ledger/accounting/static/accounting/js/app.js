(() => {
  'use strict';
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('overlay');
  const menu = document.getElementById('menuToggle');
  const hide = () => { sidebar?.classList.remove('show'); overlay?.classList.remove('show'); };
  menu?.addEventListener('click', () => { sidebar?.classList.toggle('show'); overlay?.classList.toggle('show'); });
  overlay?.addEventListener('click', hide);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
  document.querySelectorAll('[data-table-search]').forEach(input => {
    const table = document.getElementById(input.dataset.tableSearch);
    input.addEventListener('input', () => {
      const keyword = input.value.trim().toLocaleLowerCase('id');
      table?.querySelectorAll('tbody tr').forEach(row => {
        row.hidden = !row.textContent.toLocaleLowerCase('id').includes(keyword);
      });
    });
  });

  // Local canvas drawing with no external chart dependency.
  const chartEl = document.getElementById('performanceChart');
  const chartDataEl = document.getElementById('chart-data');
  if (chartEl && chartDataEl) {
    let chartData;
    try { chartData = JSON.parse(chartDataEl.textContent); } catch { chartData = null; }
    const draw = () => {
      if (!chartData) return;
      const { labels, revenue, costs } = chartData;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const rect = chartEl.getBoundingClientRect();
      if (!rect.width) return;
      const width = rect.width, height = rect.height;
      chartEl.width = Math.round(width * ratio);
      chartEl.height = Math.round(height * ratio);
      const ctx = chartEl.getContext('2d');
      ctx.scale(ratio, ratio);
      const left = 60, right = 20, top = 20, bottom = 48;
      const pw = width - left - right, ph = height - top - bottom;
      const max = Math.max(1, ...revenue, ...costs);
      ctx.font = '11px DM Sans, sans-serif';
      ctx.textBaseline = 'middle';
      for (let i=0; i<5; i++) {
        const y = top + ph * i/4;
        ctx.strokeStyle = '#e9f0eb'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(left,y); ctx.lineTo(width-right,y); ctx.stroke();
        const v = max * (4-i)/4;
        const compact = v >= 1e9 ? `${(v/1e9).toFixed(1)} M` : v >= 1e6 ? `${(v/1e6).toFixed(1)} jt` : v >= 1e3 ? `${(v/1e3).toFixed(0)} rb` : `${v.toFixed(0)}`;
        ctx.fillStyle='#96a89e';ctx.textAlign='right';ctx.fillText(compact,left-9,y);
      }
      const groupW = pw / Math.max(labels.length, 1), barW = Math.min(23,groupW*.25);
      labels.forEach((label,i) => {
        const cx = left + (i+.5)*groupW;
        [revenue[i], costs[i]].forEach((v,j) => {
          const h = Math.max(0,Math.abs(v) / max * ph);
          const x = cx + (j===0 ? -barW-2 : 2);
          ctx.fillStyle=j===0?'#24a580':'#f3b54f';
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(x,top+ph-h,barW,h,[5,5,0,0]);
          else ctx.rect(x,top+ph-h,barW,h);
          ctx.fill();
        });
        ctx.fillStyle='#83998a';ctx.textAlign='center';ctx.fillText(label,cx,height-21);
      });
    };
    window.addEventListener('resize',draw);
    draw();
  }

  // Form pasangan jurnal: satu nominal mengisi debet dan kredit sekaligus.
  const form = document.getElementById('journalForm');
  if (form) {
    const totalField = document.getElementById('id_pairs-TOTAL_FORMS');
    const rows = document.getElementById('journalRows');
    const template = document.getElementById('journalEmptyRow');
    const currency = value => 'Rp ' + new Intl.NumberFormat('id-ID', {maximumFractionDigits:2}).format(value);
    // Form Jurnal Umum: pratinjau akun + nominal debet/kredit otomatis dari server
    // (aturan yang sama dengan saat menyimpan, jadi tampilan = hasil posting).
    const previewUrl = form.dataset.previewUrl;
    if (previewUrl && !rows) {
      const ids = ['date', 'description', 'amount', 'term_text', 'discount_percent', 'discount_rp'];
      const message = document.getElementById('previewMessage');
      const table = document.getElementById('previewTable');
      const body = document.getElementById('previewBody');
      const meta = document.getElementById('previewMeta');
      let timer = null, sequence = 0;
      const params = () => {
        const q = new URLSearchParams();
        ids.forEach(id => { const el = document.getElementById('id_' + id); if (el && el.value) q.set(id, el.value); });
        if (document.getElementById('id_use_term_discount')?.checked) q.set('use_term_discount', '1');
        return q;
      };
      const show = (text, kind) => {
        message.textContent = text;
        message.className = 'notice ' + (kind || 'info');
        message.hidden = false; table.hidden = true; meta.hidden = true;
      };
      const cell = (tr, text, cls) => { const td = document.createElement('td'); td.textContent = text; if (cls) td.className = cls; tr.appendChild(td); };
      const render = async () => {
        const mine = ++sequence;
        let data;
        try {
          const res = await fetch(previewUrl + '?' + params().toString(), {headers: {'Accept': 'application/json'}});
          data = await res.json();
        } catch { if (mine === sequence) show('Pratinjau tidak dapat dimuat. Jurnal tetap dapat disimpan.', 'info'); return; }
        if (mine !== sequence) return;
        if (!data.ok) { show(data.message, data.hint ? 'info' : 'error'); return; }
        body.replaceChildren();
        data.lines.forEach(l => {
          const tr = document.createElement('tr');
          cell(tr, l.code, 'strong-code'); cell(tr, l.name); cell(tr, l.party || '–');
          cell(tr, Number(l.debit) ? currency(Number(l.debit)) : '–', 'right money');
          cell(tr, Number(l.credit) ? currency(Number(l.credit)) : '–', 'right money');
          body.appendChild(tr);
        });
        document.getElementById('previewTotalDebit').textContent = currency(Number(data.total_debit));
        document.getElementById('previewTotalCredit').textContent = currency(Number(data.total_credit));
        const notes = [];
        if (Number(data.discount)) notes.push('Diskon ' + currency(Number(data.discount)));
        if (data.term) notes.push('Termin ' + data.term);
        if (data.due_date) notes.push('Jatuh tempo ' + new Date(data.due_date + 'T00:00:00').toLocaleDateString('id-ID', {day: 'numeric', month: 'long', year: 'numeric'}));
        meta.textContent = notes.join(' · ');
        meta.hidden = notes.length === 0;
        message.hidden = true; table.hidden = false;
      };
      const schedule = () => { clearTimeout(timer); timer = setTimeout(render, 250); };
      [...ids, 'use_term_discount'].forEach(id => {
        const el = document.getElementById('id_' + id);
        el?.addEventListener('input', schedule);
        el?.addEventListener('change', schedule);
      });
      render();
      return;
    }
    if (!totalField || !rows || !template) return;
    const recalc = () => {
      let total = 0;
      rows.querySelectorAll('tr').forEach(row => {
        const removed = row.querySelector('[name$="-DELETE"]')?.checked;
        row.classList.toggle('row-removed', Boolean(removed));
        if (!removed) total += Number(row.querySelector('[name$="-amount"]')?.value || 0);
      });
      document.getElementById('totalDebit').textContent = currency(total);
      document.getElementById('totalCredit').textContent = currency(total);
      document.getElementById('journalDifference').textContent = currency(0);
    };
    rows.addEventListener('input', recalc);
    rows.addEventListener('change', recalc);
    document.getElementById('addLine')?.addEventListener('click', () => {
      const index = Number(totalField.value);
      if (index >= 15) { alert('Maksimum 15 pasangan transaksi per jurnal.'); return; }
      rows.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__prefix__', String(index)));
      totalField.value = String(index + 1);
      recalc();
    });
    recalc();
  }
})();
