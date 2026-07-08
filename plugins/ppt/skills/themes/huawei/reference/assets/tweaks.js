/* ========================================================================
   Tweaks 面板 · 主色 / 字体切换
   ======================================================================== */
(function() {
  const extra = document.createElement('link');
  extra.rel = 'stylesheet';
  extra.href = 'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Noto+Serif+SC:wght@400;500;600&display=swap';
  document.head.appendChild(extra);

  const script = document.getElementById('__tweaks');
  if (!script) return;
  const match = script.textContent.match(/\/\*EDITMODE-BEGIN\*\/([\s\S]*?)\/\*EDITMODE-END\*\//);
  if (!match) return;
  const state = JSON.parse(match[1]);

  function apply(s) {
    const r = document.documentElement.style;
    r.setProperty('--c-primary', s.primary);
    r.setProperty('--c-ink-dark', s.inkDark);
    r.setProperty('--c-paper', s.paper);
    r.setProperty('--f-sans', s.fontSans);
    r.setProperty('--f-mono', s.fontMono);
  }
  apply(state);

  function persist() {
    try { window.parent.postMessage({ type: '__edit_mode_set_keys', edits: state }, '*'); } catch(e) {}
  }

  const panel = document.createElement('div');
  panel.id = 'tweaks-panel';
  panel.innerHTML = `
    <h6>Tweaks · 主题</h6>
    <label>主色 Primary</label>
    <div class="sw-row" data-key="primary">
      <div class="sw" data-c="#C7000B" style="background:#C7000B"></div>
      <div class="sw" data-c="#8A0008" style="background:#8A0008"></div>
      <div class="sw" data-c="#0B2545" style="background:#0B2545"></div>
      <div class="sw" data-c="#1A1A1A" style="background:#1A1A1A"></div>
      <div class="sw" data-c="#D97706" style="background:#D97706"></div>
      <div class="sw" data-c="#1E7B3A" style="background:#1E7B3A"></div>
    </div>
    <label>深底 Ink Dark（章节页）</label>
    <div class="sw-row" data-key="inkDark">
      <div class="sw" data-c="#2A2A2A" style="background:#2A2A2A"></div>
      <div class="sw" data-c="#1A1A1A" style="background:#1A1A1A"></div>
      <div class="sw" data-c="#8A0008" style="background:#8A0008"></div>
      <div class="sw" data-c="#0B2545" style="background:#0B2545"></div>
      <div class="sw" data-c="#3E2C1E" style="background:#3E2C1E"></div>
      <div class="sw" data-c="#1C3B2E" style="background:#1C3B2E"></div>
    </div>
    <label>页底 Paper</label>
    <div class="sw-row" data-key="paper">
      <div class="sw" data-c="#FFFFFF" style="background:#FFFFFF; border:1px solid #555;"></div>
      <div class="sw" data-c="#FAFAFA" style="background:#FAFAFA; border:1px solid #555;"></div>
      <div class="sw" data-c="#F7F5EF" style="background:#F7F5EF; border:1px solid #555;"></div>
      <div class="sw" data-c="#F4F4F4" style="background:#F4F4F4; border:1px solid #555;"></div>
      <div class="sw" data-c="#EAEAEA" style="background:#EAEAEA; border:1px solid #555;"></div>
      <div class="sw" data-c="#F5F2EC" style="background:#F5F2EC; border:1px solid #555;"></div>
    </div>
    <label>无衬线字体</label>
    <select id="tw-sans">
      <option value="Inter, 'Noto Sans SC', 'Microsoft YaHei', system-ui, sans-serif">Inter + 思源黑体</option>
      <option value="'IBM Plex Sans', 'Noto Sans SC', sans-serif">IBM Plex Sans</option>
      <option value="'Helvetica Neue', 'Microsoft YaHei', sans-serif">Helvetica + 雅黑</option>
      <option value="'PingFang SC', 'Microsoft YaHei', sans-serif">苹方 / 雅黑</option>
      <option value="Georgia, 'Noto Serif SC', serif">Georgia + 思源宋体</option>
    </select>
    <label>等宽字体</label>
    <select id="tw-mono">
      <option value="'JetBrains Mono', ui-monospace, monospace">JetBrains Mono</option>
      <option value="'IBM Plex Mono', ui-monospace, monospace">IBM Plex Mono</option>
      <option value="Menlo, monospace">Menlo</option>
      <option value="'Courier New', monospace">Courier New</option>
    </select>
  `;
  document.body.appendChild(panel);

  const style = document.createElement('style');
  style.textContent = `
    #tweaks-panel {
      position: fixed; right: 20px; bottom: 20px; z-index: 9999;
      background: #111; color: #eee; font-family: var(--f-mono); font-size: 13px;
      padding: 16px 18px; border: 1px solid #333; min-width: 260px;
      box-shadow: 0 8px 30px rgba(0,0,0,0.4); display: none;
    }
    #tweaks-panel h6 { margin: 0 0 12px; font-size: 12px; letter-spacing: 0.16em; color: #999; text-transform: uppercase; font-weight: 500; }
    #tweaks-panel label { display: block; margin: 10px 0 4px; font-size: 11px; color: #bbb; letter-spacing: 0.08em; text-transform: uppercase; }
    #tweaks-panel .sw-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 5px; }
    #tweaks-panel .sw { height: 26px; cursor: pointer; border: 2px solid transparent; }
    #tweaks-panel .sw.on { border-color: #fff; }
    #tweaks-panel select { width: 100%; background: #222; color: #fff; border: 1px solid #444; padding: 5px; font-family: inherit; font-size: 12px; }
  `;
  document.head.appendChild(style);

  function bindSw(rowKey) {
    const row = panel.querySelector(`.sw-row[data-key="${rowKey}"]`);
    const refresh = () => row.querySelectorAll('.sw').forEach(s => {
      s.classList.toggle('on', s.dataset.c.toLowerCase() === state[rowKey].toLowerCase());
    });
    row.addEventListener('click', e => {
      const sw = e.target.closest('.sw');
      if (!sw) return;
      state[rowKey] = sw.dataset.c;
      apply(state); refresh(); persist();
    });
    refresh();
  }
  bindSw('primary'); bindSw('inkDark'); bindSw('paper');

  const sansSel = panel.querySelector('#tw-sans');
  sansSel.value = state.fontSans;
  sansSel.addEventListener('change', () => { state.fontSans = sansSel.value; apply(state); persist(); });
  const monoSel = panel.querySelector('#tw-mono');
  monoSel.value = state.fontMono;
  monoSel.addEventListener('change', () => { state.fontMono = monoSel.value; apply(state); persist(); });

  window.addEventListener('message', e => {
    const d = e.data;
    if (!d || !d.type) return;
    if (d.type === '__activate_edit_mode') panel.style.display = 'block';
    if (d.type === '__deactivate_edit_mode') panel.style.display = 'none';
  });
  try { window.parent.postMessage({ type: '__edit_mode_available' }, '*'); } catch(e) {}
})();
