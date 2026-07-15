/* LCC Y2KM — Lucent Command Center frontend (Phase 1).
   Vanilla JS. Activated by app.js switchLogTab('lcc'). Backend: :8104. */
(function () {
    // Same-origin proxy (ui/server.py forwards /lcc/* → 127.0.0.1:8104).
    // Relative so it inherits the page's http/https scheme — no mixed content.
    const BASE = '/lcc';
    const SPARK_MAX = 60;
    let invTimer = null, sysTimer = null, tick = 0, tickTimer = null, built = false;
    const spark = { cpu: [], mem: [] };

    // ── helpers ──────────────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    function fmtBytes(n) {
        if (n == null) return '—';
        const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0;
        while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
        return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)}${u[i]}`;
    }
    function fmtUptime(s) {
        if (s == null) return '—';
        if (s < 60) return `${s}s`;
        if (s < 3600) return `${Math.floor(s / 60)}m`;
        if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
        return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
    }
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    // ── favorites (persisted client-side, keyed by port) ──────────────────────
    const FAV_KEY = 'lcc_fav_ports';
    let _lastServices = null;   // cache so a star toggle can re-render in place
    function getFavs() {
        try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
        catch (e) { return new Set(); }
    }
    window.lccToggleFav = (port) => {
        const s = getFavs();
        s.has(port) ? s.delete(port) : s.add(port);
        localStorage.setItem(FAV_KEY, JSON.stringify([...s]));
        if (_lastServices) renderServices(_lastServices);   // instant re-sort
    };

    function toast(msg, isErr) {
        let wrap = $('lccToasts');
        if (!wrap) { wrap = document.createElement('div'); wrap.id = 'lccToasts'; wrap.className = 'lcc-toasts'; document.body.appendChild(wrap); }
        const t = document.createElement('div');
        t.className = 'lcc-toast' + (isErr ? ' err' : '');
        t.textContent = msg;
        wrap.appendChild(t);
        setTimeout(() => t.remove(), 4200);
    }

    function sparkSVG(buf, color) {
        if (buf.length < 2) return '';
        const w = 186, h = 26, max = 100;
        const pts = buf.map((v, i) => {
            const x = (i / (SPARK_MAX - 1)) * w;
            const y = h - (Math.min(v, max) / max) * h;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(' ');
        return `<svg class="lcc-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
            <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" opacity="0.85"/></svg>`;
    }
    const zoneCls = (p) => p >= 90 ? 'crit' : p >= 75 ? 'warn' : '';

    // ── shell ─────────────────────────────────────────────────────────────────
    function build() {
        const v = $('lccView');
        if (!v) return;
        v.innerHTML = `
        <div class="lcc-sidebar">
            <div class="lcc-brand">LCC&nbsp;Y2KM<small>LUCENT COMMAND CENTER</small></div>
            <button class="lcc-btn lcc-back" id="lccBack" title="Return to the Lucent dashboard">‹ Back to Lucent</button>
            <div class="lcc-nav">
                <button data-jump="lccServices" class="active">◈ Services & Ports</button>
                <button data-jump="lccDocker">▣ Docker</button>
                <button data-jump="lccOllama">◉ Ollama</button>
                <button data-jump="lccProjects">▤ Projects</button>
            </div>
            <div class="lcc-resmon" id="lccResmon"><div class="lcc-empty">Reading resources…</div></div>
        </div>
        <div class="lcc-main">
            <div class="lcc-topbar">
                <div class="lcc-title">LCC Y2KM</div>
                <div class="lcc-summary" id="lccSummary"></div>
                <div class="lcc-refresh">
                    <span class="tick" id="lccTick">—</span>
                    <button class="lcc-btn" onclick="lccOpenPalette()" title="Command palette (Ctrl/Cmd+K)">⌘K</button>
                    <button class="lcc-btn" id="lccRefreshBtn">↻ Refresh</button>
                </div>
            </div>
            <div class="lcc-section" id="lccServices"><h2>◈ Services &amp; Ports <span class="count" id="lccSvcCount"></span></h2><div id="lccSvcBody"><div class="lcc-empty">Loading…</div></div></div>
            <div class="lcc-section" id="lccDocker"><h2>▣ Docker Containers <span class="count" id="lccDkCount"></span></h2><div id="lccDkBody"><div class="lcc-empty">Loading…</div></div></div>
            <div class="lcc-section" id="lccOllama"><h2>◉ Ollama Models <span class="count" id="lccOlCount"></span></h2><div id="lccOlBody"><div class="lcc-empty">Loading…</div></div></div>
            <div class="lcc-section" id="lccProjects"><h2>▤ My Projects <span class="count" id="lccPrCount"></span></h2><div id="lccPrBody"><div class="lcc-empty">Loading…</div></div></div>
        </div>
        <div class="lcc-modal-back hidden" id="lccModalBack">
            <div class="lcc-modal">
                <h3>Confirm action</h3>
                <p id="lccModalMsg"></p>
                <div class="actions">
                    <button class="lcc-btn" id="lccModalCancel">Cancel</button>
                    <button class="lcc-btn danger" id="lccModalOk">Confirm</button>
                </div>
            </div>
        </div>`;

        v.querySelectorAll('[data-jump]').forEach(b => b.addEventListener('click', () => {
            v.querySelectorAll('.lcc-nav button').forEach(x => x.classList.remove('active'));
            b.classList.add('active');
            $(b.dataset.jump).scrollIntoView({ behavior: 'smooth', block: 'start' });
        }));
        $('lccBack').addEventListener('click', () => {
            // switchLogTab restores .main-grid and calls lccDeactivate()
            if (window.switchLogTab) window.switchLogTab('daily');
        });
        $('lccRefreshBtn').addEventListener('click', () => { loadInventory(); loadSystem(); });
        $('lccModalCancel').addEventListener('click', closeModal);
        $('lccModalBack').addEventListener('click', (e) => { if (e.target.id === 'lccModalBack') closeModal(); });

        // per-section focus buttons (⛶ toggles focus on that section)
        SECTIONS.forEach(id => {
            const h = $(id) && $(id).querySelector('h2');
            if (!h) return;
            const b = document.createElement('button');
            b.className = 'lcc-focus-btn'; b.textContent = '⛶'; b.title = 'Focus this section (Esc to exit)';
            b.onclick = () => setFocus(_focusSection === id ? null : id);
            h.appendChild(b);
        });

        // command palette overlay (appended once to body)
        if (!$('lccPalBack')) {
            const pal = document.createElement('div');
            pal.id = 'lccPalBack'; pal.className = 'lcc-pal-back hidden';
            pal.innerHTML = `<div class="lcc-pal">
                <input id="lccPalInput" class="lcc-pal-input" placeholder="Type a command…  (Esc to close)">
                <div id="lccPalList" class="lcc-pal-list"></div></div>`;
            document.body.appendChild(pal);
            pal.addEventListener('click', e => { if (e.target.id === 'lccPalBack') closePalette(); });
            const inp = $('lccPalInput');
            inp.addEventListener('input', () => { _palSel = 0; renderPalette(inp.value); });
            inp.addEventListener('keydown', e => {
                if (e.key === 'ArrowDown') { e.preventDefault(); _palSel = Math.min(_palSel + 1, _palCmds.length - 1); renderPalette(inp.value); }
                else if (e.key === 'ArrowUp') { e.preventDefault(); _palSel = Math.max(_palSel - 1, 0); renderPalette(inp.value); }
                else if (e.key === 'Enter') { e.preventDefault(); runSelected(); }
                else if (e.key === 'Escape') { closePalette(); }
            });
        }
        built = true;
    }

    // ── modal / actions ─────────────────────────────────────────────────────
    function closeModal() { $('lccModalBack').classList.add('hidden'); }

    async function post(url, params) {
        const u = new URL(BASE + url, location.href);   // preserves any ?name= in url
        Object.entries(params || {}).forEach(([k, v]) => u.searchParams.set(k, v));
        const r = await fetch(u, { method: 'POST' });
        return r.json();
    }

    // Two-step: request → if needs_confirm show modal → resend with token.
    async function action(url, label) {
        let res;
        try { res = await post(url); } catch (e) { toast('Request failed: ' + e, true); return; }
        if (res && res.needs_confirm) {
            $('lccModalMsg').textContent = res.impact || label;
            $('lccModalBack').classList.remove('hidden');
            const ok = $('lccModalOk'), fresh = ok.cloneNode(true);
            ok.parentNode.replaceChild(fresh, ok);
            fresh.addEventListener('click', async () => {
                closeModal();
                let r2;
                try { r2 = await post(url, { token: res.token }); } catch (e) { toast('Failed: ' + e, true); return; }
                if (r2.ok) { toast(`${label} ✓`); loadInventory(); }
                else toast(r2.error || 'Action failed' + (r2.hint ? ` — ${r2.hint}` : ''), true);
            });
        } else if (res.ok) { toast(`${label} ✓`); loadInventory(); }
        else toast((res.error || 'Action failed') + (res.hint ? ` — ${res.hint}` : ''), true);
    }
    window.lccAction = action;

    // Ollama pull with live progress (backend runs it in a thread; we poll status)
    window.lccPull = async function () {
        const inp = $('lccPullInput');
        const name = inp && inp.value.trim();
        if (!name) { toast('Enter a model:tag to pull', true); return; }
        const st = $('lccPullStatus');
        try { await post('/api/ollama/pull', { name }); } catch (e) { toast('Pull failed: ' + e, true); return; }
        toast(`Pulling ${name}…`);
        const poll = setInterval(async () => {
            let s;
            try { s = await (await fetch(`${BASE}/api/ollama/pull/status?name=${encodeURIComponent(name)}`)).json(); }
            catch (e) { return; }
            if (st) st.textContent = s.done ? '' : `${name}: ${s.status || ''} ${(s.percent || 0)}%`;
            if (s.done) {
                clearInterval(poll);
                if (s.error) toast('Pull failed: ' + s.error, true);
                else { toast(`${name} pulled ✓`); if (inp) inp.value = ''; loadInventory(); }
            }
        }, 1500);
    };

    // ── renderers ─────────────────────────────────────────────────────────────
    function renderSystem(s) {
        if (!s || s.error) { $('lccResmon').innerHTML = `<div class="lcc-empty">system: ${esc(s && s.error)}</div>`; return; }
        spark.cpu.push(s.cpu.total); if (spark.cpu.length > SPARK_MAX) spark.cpu.shift();
        spark.mem.push(s.mem.percent); if (spark.mem.length > SPARK_MAX) spark.mem.shift();
        const g = (label, pct, sub, sk, col) => `
            <div class="lcc-gauge">
                <div class="lcc-gauge-head"><span>${label}</span><span class="val">${pct.toFixed(0)}%</span></div>
                <div class="lcc-bar ${zoneCls(pct)}"><span style="width:${Math.min(pct, 100)}%"></span></div>
                ${sub ? `<div class="lcc-gauge-head" style="margin-top:3px"><span>${sub}</span></div>` : ''}
                ${sk ? sparkSVG(sk, col) : ''}
            </div>`;
        $('lccResmon').innerHTML =
            g('CPU', s.cpu.total, `${s.cpu.count} cores`, spark.cpu, 'var(--status-running)') +
            g('MEMORY', s.mem.percent, `${fmtBytes(s.mem.used)} / ${fmtBytes(s.mem.total)}`, spark.mem, 'var(--neon-cyan)') +
            g('SWAP', s.swap.percent, `${fmtBytes(s.swap.used)} / ${fmtBytes(s.swap.total)}`, null) +
            g('DISK /', s.disk.percent, `${fmtBytes(s.disk.used)} / ${fmtBytes(s.disk.total)}`, null);
        checkThreshold('CPU', s.cpu.total);
        checkThreshold('RAM', s.mem.percent);
        checkThreshold('Disk', s.disk.percent);
    }

    function renderServices(d) {
        const body = $('lccSvcBody');
        if (!d || d.error) { body.innerHTML = `<div class="lcc-empty">${esc(d && d.error)}</div>`; return; }
        _lastServices = d;
        const favs = getFavs();
        const rows = (d.services || []).slice();
        // sort: favorites first → project name A–Z → port ascending
        rows.sort((a, b) => {
            const fa = favs.has(a.port) ? 0 : 1, fb = favs.has(b.port) ? 0 : 1;
            if (fa !== fb) return fa - fb;
            const pa = (a.project || '').toLowerCase(), pb = (b.project || '').toLowerCase();
            if (pa !== pb) return pa < pb ? -1 : 1;
            return a.port - b.port;
        });
        const run = rows.filter(r => r.status === 'running').length;
        const favN = rows.filter(r => favs.has(r.port)).length;
        $('lccSvcCount').textContent = `${run}/${rows.length} up${favN ? ` · ${favN}★` : ''}`;

        const rowHTML = (r) => {
            const isFav = favs.has(r.port);
            return `<tr>
                <td><span class="lcc-pill ${r.status}"><span class="lcc-dot ${r.status}"></span>${r.status}</span></td>
                <td class="lcc-fav ${isFav ? 'on' : ''}" onclick="lccToggleFav(${r.port})"
                    title="${isFav ? 'Unfavorite' : 'Mark favorite'}">${isFav ? '★' : '☆'}</td>
                <td>${r.status === 'running' ? `<a href="${esc(r.url)}" target="_blank">${r.port}</a>` : r.port}</td>
                <td>${esc(r.project)}</td><td class="lcc-muted">${esc(r.service)}</td>
                <td class="lcc-muted">${esc(r.process) || '—'}</td><td class="lcc-muted">${fmtUptime(r.uptime)}</td>
                <td class="lcc-row">${r.protected ? '<span class="lcc-muted">protected</span>'
                    : r.status === 'running'
                    ? `<button class="lcc-btn" onclick="lccAction('/api/services/${r.port}/restart','Restart ${esc(r.project)}')">Restart</button>
                       <button class="lcc-btn danger" onclick="lccAction('/api/services/${r.port}/stop','Stop ${esc(r.project)}')">Stop</button>`
                    : `<button class="lcc-btn" onclick="lccAction('/api/services/${r.port}/start','Start ${esc(r.project)}')">Start</button>`}</td>
            </tr>`;
        };

        let tbody = '', dividerDone = false;
        rows.forEach(r => {
            if (favN && !dividerDone && !favs.has(r.port)) {   // subtle break after favorites
                tbody += `<tr class="lcc-divider-row"><td colspan="8">ALL SERVICES</td></tr>`;
                dividerDone = true;
            }
            tbody += rowHTML(r);
        });

        body.innerHTML = `<table class="lcc-table"><thead><tr>
            <th>Status</th><th></th><th>Port</th><th>Project</th><th>Service</th><th>Process</th><th>Uptime</th><th></th>
            </tr></thead><tbody>${tbody}</tbody></table>`;
    }

    function renderDocker(d) {
        const body = $('lccDkBody');
        if (!d || d.error) { body.innerHTML = `<div class="lcc-empty">${esc(d && d.error)}</div>`; return; }
        if (!d.available) { body.innerHTML = '<div class="lcc-empty">Docker daemon not available.</div>'; return; }
        const rows = d.containers || [];
        const run = rows.filter(r => r.status === 'running').length;
        $('lccDkCount').textContent = `${run}/${rows.length} up`;
        if (!rows.length) { body.innerHTML = '<div class="lcc-empty">No containers.</div>'; return; }
        body.innerHTML = `<table class="lcc-table"><thead><tr>
            <th>Status</th><th>Name</th><th>Image</th><th>Ports</th><th>Controls</th></tr></thead><tbody>${
            rows.map(c => {
                const running = c.status === 'running';
                const st = running ? 'running' : 'stopped';
                return `<tr>
                    <td><span class="lcc-pill ${st}"><span class="lcc-dot ${st}"></span>${esc(c.status)}</span></td>
                    <td>${esc(c.name)}</td><td class="lcc-muted">${esc(c.image)}</td>
                    <td class="lcc-muted">${(c.ports && c.ports.length)
                        ? c.ports.map(p => running
                            ? `<a href="http://localhost:${esc(p)}" target="_blank">${esc(p)}</a>`
                            : esc(p)).join(', ')
                        : '—'}</td>
                    <td class="lcc-row">${running
                        ? `<button class="lcc-btn" onclick="lccAction('/api/docker/${c.id}/restart','Restart ${esc(c.name)}')">Restart</button>
                           <button class="lcc-btn danger" onclick="lccAction('/api/docker/${c.id}/stop','Stop ${esc(c.name)}')">Stop</button>`
                        : `<button class="lcc-btn" onclick="lccAction('/api/docker/${c.id}/start','Start ${esc(c.name)}')">Start</button>`}
                    </td></tr>`;
            }).join('')}</tbody></table>`;
    }

    function renderOllama(d) {
        const body = $('lccOlBody');
        if (!d || d.error) { body.innerHTML = `<div class="lcc-empty">${esc(d && d.error)}</div>`; return; }
        if (!d.available) { body.innerHTML = '<div class="lcc-empty">Ollama not reachable.</div>'; return; }
        const loaded = new Set((d.loaded || []).map(m => m.name));
        const models = d.models || [];
        $('lccOlCount').textContent = `${models.length} models · ${loaded.size} loaded`;
        body.innerHTML = `
            <div class="lcc-pull-bar">
                <input type="text" id="lccPullInput" class="lcc-input" placeholder="model:tag to pull (e.g. llama3.2:latest)">
                <button class="lcc-btn" onclick="lccPull()">⤓ Pull</button>
                <span class="lcc-muted" id="lccPullStatus"></span>
            </div>
            <table class="lcc-table"><thead><tr>
            <th>Model</th><th>Family</th><th>Size</th><th>State</th><th>Controls</th></tr></thead><tbody>${
            models.map(m => {
                const nm = encodeURIComponent(m.name), lbl = esc(m.name);
                const isLoaded = loaded.has(m.name);
                return `<tr>
                    <td>${esc(m.name)}</td><td class="lcc-muted">${esc(m.family) || '—'}</td>
                    <td class="lcc-muted">${fmtBytes(m.size)}</td>
                    <td>${isLoaded ? '<span class="lcc-badge-vram">IN VRAM</span>' : '<span class="lcc-muted">on disk</span>'}</td>
                    <td class="lcc-row">${isLoaded
                        ? `<button class="lcc-btn" onclick="lccAction('/api/ollama/unload?name=${nm}','Unload ${lbl}')">Unload</button>`
                        : `<button class="lcc-btn" onclick="lccAction('/api/ollama/load?name=${nm}','Load ${lbl}')">Load</button>`}
                        <button class="lcc-btn danger" onclick="lccAction('/api/ollama/delete?name=${nm}','Delete ${lbl}')">Delete</button>
                    </td></tr>`;
            }).join('')}</tbody></table>`;
    }

    // Projects: user-owned draggable list with separator bars (order persists).
    let _projItems = [];
    let _dragIdx = null;

    function renderProjectsLayout() {
        const body = $('lccPrBody');
        const items = _projItems;
        $('lccPrCount').textContent = `${items.filter(i => i.type === 'project').length}`;
        let html = `<div class="lcc-proj-toolbar">
            <button class="lcc-btn" onclick="lccAddSeparator()">+ Separator</button>
            <span class="lcc-muted">drag to reorder · changes auto-save</span></div>
            <div class="lcc-proj-list" id="lccProjList">`;
        items.forEach((it, idx) => {
            if (it.type === 'separator') {
                html += `<div class="lcc-sep" draggable="true" data-idx="${idx}">
                    <span class="lcc-grip">⋮⋮</span>
                    <span class="lcc-sep-label" onclick="lccRenameSep(${idx})" title="Click to rename">${esc(it.label) || 'Section'}</span>
                    <button class="lcc-sep-del" onclick="lccDelSeparator(${idx})" title="Remove separator">×</button></div>`;
            } else {
                html += `<div class="lcc-proj-item" draggable="true" data-idx="${idx}">
                    <span class="lcc-grip">⋮⋮</span>
                    <div class="lcc-proj-main">
                        <div class="lcc-proj-title">${esc(it.title)}</div>
                        <div class="lcc-proj-desc">${esc(it.description) || '<span class="lcc-muted">No README summary.</span>'}</div>
                    </div>
                    ${it.has_readme ? `<button class="lcc-btn" onclick="lccOpenReadme('${esc(it.path)}')">README</button>` : ''}
                </div>`;
            }
        });
        body.innerHTML = html + `</div>`;
        wireProjDnD();
    }

    function wireProjDnD() {
        const list = $('lccProjList');
        if (!list) return;
        list.querySelectorAll('[draggable="true"]').forEach(el => {
            el.addEventListener('dragstart', () => { _dragIdx = +el.dataset.idx; el.classList.add('dragging'); });
            el.addEventListener('dragend', () => el.classList.remove('dragging'));
            el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('drag-over'); });
            el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
            el.addEventListener('drop', e => {
                e.preventDefault(); el.classList.remove('drag-over');
                const to = +el.dataset.idx;
                if (_dragIdx === null || _dragIdx === to) return;
                const moved = _projItems.splice(_dragIdx, 1)[0];
                _projItems.splice(to, 0, moved);
                _dragIdx = null;
                saveLayout(); renderProjectsLayout();
            });
        });
    }

    async function saveLayout() {
        try {
            await fetch(`${BASE}/api/projects/layout`, {
                method: 'PUT',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({
                    items: _projItems.map(i => i.type === 'separator'
                        ? { type: 'separator', id: i.id, label: i.label }
                        : { type: 'project', name: i.name })
                })
            });
        } catch (e) { toast('Layout save failed', true); }
    }

    window.lccAddSeparator = () => { _projItems.unshift({ type: 'separator', id: 'sep' + Date.now(), label: 'New Section' }); saveLayout(); renderProjectsLayout(); };
    window.lccDelSeparator = (idx) => { _projItems.splice(idx, 1); saveLayout(); renderProjectsLayout(); };
    window.lccRenameSep = (idx) => {
        const v = prompt('Section label:', _projItems[idx].label || '');
        if (v !== null) { _projItems[idx].label = v.trim(); saveLayout(); renderProjectsLayout(); }
    };

    async function loadProjects() {
        try {
            const d = await (await fetch(`${BASE}/api/projects/layout`)).json();
            _projItems = d.items || [];
            renderProjectsLayout();
        } catch (e) { $('lccPrBody').innerHTML = `<div class="lcc-empty">projects unavailable</div>`; }
    }

    // README in a new tab (served by existing Lucent /view-file endpoint,
    // which resolves absolute paths — /api/projects returns absolute paths)
    window.lccOpenReadme = (projPath) => {
        window.open(`/view-file?path=${encodeURIComponent(projPath + '/README.md')}`, '_blank');
    };

    // ── Phase 3: real-time-feel alerts (change detection between polls) ────────
    let _prevSvc = null, _prevLoaded = null;
    const _alertLvl = {};
    function detectChanges(inv) {
        const svc = (inv.services && inv.services.services) || [];
        if (_prevSvc) {
            const prev = Object.fromEntries(_prevSvc.map(s => [s.port, s.status]));
            svc.forEach(s => {
                const p = prev[s.port];
                if (p && p !== s.status) {
                    if (s.status === 'stopped') toast(`▼ ${s.project} :${s.port} went DOWN`, true);
                    else if (s.status === 'running') toast(`▲ ${s.project} :${s.port} is UP`);
                }
            });
        }
        _prevSvc = svc;
        const loaded = ((inv.ollama && inv.ollama.loaded) || []).map(m => m.name);
        if (_prevLoaded) {
            loaded.filter(n => !_prevLoaded.includes(n)).forEach(n => toast(`◉ ${n} loaded into VRAM`));
            _prevLoaded.filter(n => !loaded.includes(n)).forEach(n => toast(`○ ${n} unloaded`));
        }
        _prevLoaded = loaded;
    }
    function checkThreshold(name, pct) {
        const lvl = pct >= 90 ? 2 : pct >= 75 ? 1 : 0;
        if (lvl > (_alertLvl[name] || 0)) {
            toast(`⚠ ${name} ${lvl === 2 ? 'critical' : 'high'}: ${pct.toFixed(0)}%`, lvl === 2);
        }
        _alertLvl[name] = lvl;
    }

    // ── Phase 3: focus mode ───────────────────────────────────────────────────
    let _focusSection = null;
    const SECTIONS = ['lccServices', 'lccDocker', 'lccOllama', 'lccProjects'];
    function setFocus(id) {
        _focusSection = id;
        SECTIONS.forEach(sid => { const el = $(sid); if (el) el.style.display = (!id || sid === id) ? '' : 'none'; });
    }
    function jump(id) {
        if (_focusSection) setFocus(null);
        const el = $(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        document.querySelectorAll('.lcc-nav button').forEach(b => b.classList.toggle('active', b.dataset.jump === id));
    }

    // ── Phase 3: Cmd-K command palette ────────────────────────────────────────
    let _palCmds = [], _palSel = 0;
    function paletteCommands() {
        const cmds = [
            { label: 'Go: Services & Ports', act: () => jump('lccServices') },
            { label: 'Go: Docker', act: () => jump('lccDocker') },
            { label: 'Go: Ollama', act: () => jump('lccOllama') },
            { label: 'Go: Projects', act: () => jump('lccProjects') },
            { label: 'Refresh all', act: () => { loadInventory(); loadSystem(); loadProjects(); } },
            { label: 'Focus: Services only', act: () => setFocus('lccServices') },
            { label: 'Focus: Docker only', act: () => setFocus('lccDocker') },
            { label: 'Focus: Ollama only', act: () => setFocus('lccOllama') },
            { label: 'Focus: Projects only', act: () => setFocus('lccProjects') },
            { label: 'Show all sections', act: () => setFocus(null) },
            { label: 'Back to Lucent', act: () => window.switchLogTab && window.switchLogTab('daily') },
        ];
        ((_lastServices && _lastServices.services) || [])
            .filter(s => s.status === 'running')
            .forEach(s => cmds.push({ label: `Open: ${s.project} :${s.port}`, act: () => window.open(s.url, '_blank') }));
        return cmds;
    }
    function renderPalette(filter) {
        const f = (filter || '').toLowerCase();
        _palCmds = paletteCommands().filter(c => c.label.toLowerCase().includes(f));
        if (_palSel >= _palCmds.length) _palSel = Math.max(0, _palCmds.length - 1);
        const list = $('lccPalList');
        list.innerHTML = _palCmds.length
            ? _palCmds.map((c, i) => `<div class="lcc-pal-item ${i === _palSel ? 'sel' : ''}" data-i="${i}">${esc(c.label)}</div>`).join('')
            : '<div class="lcc-empty">no matches</div>';
        list.querySelectorAll('.lcc-pal-item').forEach(el => el.onclick = () => { _palSel = +el.dataset.i; runSelected(); });
    }
    function runSelected() { const c = _palCmds[_palSel]; closePalette(); if (c) c.act(); }
    function openPalette() {
        const back = $('lccPalBack'); if (!back) return;
        back.classList.remove('hidden');
        _palSel = 0; const inp = $('lccPalInput'); inp.value = ''; inp.focus(); renderPalette('');
    }
    function closePalette() { const b = $('lccPalBack'); if (b) b.classList.add('hidden'); }
    window.lccOpenPalette = openPalette;
    function keyHandler(e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
        else if (e.key === 'Escape') {
            if (!$('lccPalBack').classList.contains('hidden')) closePalette();
            else if (_focusSection) setFocus(null);
        }
    }

    function renderSummary(inv) {
        const s = inv.services && inv.services.services || [];
        const dk = inv.docker && inv.docker.containers || [];
        const ol = inv.ollama && inv.ollama.models || [];
        $('lccSummary').innerHTML =
            `<span><b>${s.filter(x => x.status === 'running').length}</b>/${s.length} services</span>
             <span><b>${dk.filter(x => x.status === 'running').length}</b>/${dk.length} containers</span>
             <span><b>${ol.length}</b> models</span>`;
    }

    // ── loaders ─────────────────────────────────────────────────────────────
    async function loadInventory() {
        try {
            const inv = await (await fetch(`${BASE}/api/inventory`)).json();
            renderServices(inv.services);
            renderDocker(inv.docker);
            renderOllama(inv.ollama);
            renderSummary(inv);   // projects load separately (loadProjects) so drag isn't interrupted
            if (inv.system) renderSystem(inv.system);
            detectChanges(inv);   // real-time-feel toasts on up/down + model load/unload
            tick = 0;
        } catch (e) {
            $('lccSummary').innerHTML = `<span style="color:var(--status-stopped)">command-center backend unreachable — start idea/PewPew/backend/start.sh</span>`;
        }
    }
    async function loadSystem() {
        try { renderSystem(await (await fetch(`${BASE}/api/system`)).json()); } catch (e) { /* ignore */ }
    }

    // ── lifecycle (called by app.js) ─────────────────────────────────────────
    window.lccActivate = function () {
        if (!built) build();
        loadInventory(); loadSystem(); loadProjects();
        invTimer = setInterval(loadInventory, 4000);
        sysTimer = setInterval(loadSystem, 2000);
        tickTimer = setInterval(() => { tick++; const t = $('lccTick'); if (t) t.textContent = `updated ${tick}s ago`; }, 1000);
        document.addEventListener('keydown', keyHandler);
    };
    window.lccDeactivate = function () {
        clearInterval(invTimer); clearInterval(sysTimer); clearInterval(tickTimer);
        invTimer = sysTimer = tickTimer = null;
        document.removeEventListener('keydown', keyHandler);
        closePalette(); if (_focusSection) setFocus(null);
    };
})();
