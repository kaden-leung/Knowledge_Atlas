/* ────────────────────────────────────────────────────────────────
   ka_canonical_navbar.js — the single source of truth for K-ATLAS navigation

   Adopts Option 3: the nav items match KA_STYLE_GUIDE.md §1a and §1b
   verbatim (Articles · Topics · Theories · Mechanisms · Neural Underpinnings
   for the global regime; Syllabus · A0 · A1 · Track 1-4 · Profile for 160sp).
   Pages that do not yet exist (Theories, Mechanisms, Neural Underpinnings)
   are marked {stub:true} so the nav can render with a small "stub" badge
   until the pages ship.

   Right-slot state machine (the unified component we agreed):
     anonymous                    → [user-type picker] [Log in] [Register]
     signed in, public user type  → [user-type picker] [Account menu]
     signed in, 160 Student       → [Student profile pill] [Account menu]
     signed in, Admin             → [Admin badge] [user-type picker] [Account menu]
   Impersonation banner is handled by ka_user_type.js (separate file).

   Include on every page:
     <script src="ka_canonical_navbar.js" defer></script>
   Declare the regime on <body> (otherwise inferred from URL):
     <body data-ka-regime="global"   data-ka-active="topics">
     <body data-ka-regime="160sp"    data-ka-active="track2"
           data-ka-crumbs='[["Home","ka_home.html"],["Track 2",""]]'>
   Slots (created automatically if missing):
     <div id="ka-navbar-slot"></div>
     <div id="ka-breadcrumb-slot"></div>

   Coexists with ka_user_type.js via the window.KA namespace.
   ──────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  /* ─── Regime item inventories ────────────────────────────── */

  const REGIME_ITEMS = {
    global: [
      { id:'search',     label:'⌕ Search',             href:'ka_search.html' },
      { id:'articles',   label:'Articles',             href:'ka_articles.html' },
      { id:'topics',     label:'Topics',               href:'ka_topics.html' },
      { id:'theories',   label:'Theories',             href:'ka_theories.html' },
      { id:'mechanisms', label:'Mechanisms',           href:'ka_mechanisms.html' },
      { id:'neural',     label:'Neural Underpinnings', href:'ka_neural.html' },
      { id:'contribute', label:'Contribute',           href:'ka_contribute.html' },
      { id:'about',      label:'About',                href:'ka_about.html' },
    ],
    '160sp': [
      { id:'search',   label:'⌕ Search', href:'ka_search.html', global:true },
      { id:'syllabus', label:'Syllabus', href:'ka_schedule.html' },
      { id:'a0',       label:'A0',       href:'week2_exercises.html' },
      { id:'a1',       label:'A1',       href:'week3_agenda.html' },
      { id:'track1',   label:'Track 1',  href:'t1_intro.html' },
      { id:'track2',   label:'Track 2',  href:'t2_intro.html' },
      { id:'track3',   label:'Track 3',  href:'t3_intro.html' },
      { id:'track4',   label:'Track 4',  href:'t4_intro.html' },
    ],
  };

  const USER_TYPES_PUBLIC = [
    { id:'visitor',      label:'Visitor' },
    { id:'researcher',   label:'Researcher' },
    { id:'practitioner', label:'Practitioner' },
    { id:'contributor',  label:'Contributor' },
  ];
  const USER_TYPES_GATED = [
    { id:'160-student',  label:'160 Student' },
    { id:'instructor',   label:'Instructor' },
  ];

  /* ─── Shared namespace ───────────────────────────────────── */

  const KA = (window.KA = window.KA || {});
  const SS = window.sessionStorage;
  const LS = window.localStorage;
  const GATED_USER_TYPES = new Set(USER_TYPES_GATED.map(type => type.id));
  function g(k) { try { return SS.getItem(k); } catch (e) { return null; } }
  function s(k, v) { try { SS.setItem(k, v); } catch (e) {} }
  function lg(k) { try { return LS.getItem(k); } catch (e) { return null; } }
  function lrm(k) { try { LS.removeItem(k); } catch (e) {} }
  function srm(k) { try { SS.removeItem(k); } catch (e) {} }
  function esc(x) {
    return String(x == null ? '' : x).replace(/[&<>"']/g, c =>
      ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c]);
  }

  function readCurrentUser() {
    try {
      const raw = lg('ka_current_user');
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function hasAccessToken() {
    return !!lg('ka_access_token');
  }

  function clearCompatSessionAuth() {
    ['ka.admin', 'ka.adminEmail', 'ka.adminRole', 'ka.impersonating',
     'ka.160.authed', 'ka.studentEmail'].forEach(srm);
  }

  function normalizeStoredUserType(isPrivileged) {
    const current = g('ka.userType') || 'visitor';
    if (!isPrivileged && GATED_USER_TYPES.has(current)) {
      s('ka.userType', 'visitor');
      return 'visitor';
    }
    return current;
  }

  function syncCompatSessionFromLocalAuth() {
    const user = readCurrentUser();
    const hasToken = hasAccessToken();
    if (!hasToken || !user || !user.email) {
      clearCompatSessionAuth();
      normalizeStoredUserType(false);
      return null;
    }

    const role = String(user.role || '').toLowerCase();
    if (role === 'instructor' || role === 'admin') {
      s('ka.admin', 'yes');
      s('ka.adminEmail', user.email);
      s('ka.adminRole', role);
      if (!g('ka.userType')) s('ka.userType', 'instructor');
      try { SS.removeItem('ka.160.authed'); SS.removeItem('ka.studentEmail'); } catch (e) {}
      return user;
    }

    s('ka.160.authed', 'yes');
    s('ka.studentEmail', user.email);
    if (!g('ka.userType') || g('ka.userType') === 'visitor') s('ka.userType', '160-student');
    try { SS.removeItem('ka.admin'); SS.removeItem('ka.adminEmail'); SS.removeItem('ka.adminRole'); } catch (e) {}
    return user;
  }

  function primeFromUser(user) {
    if (!user || !user.email) return null;
    try { LS.setItem('ka_current_user', JSON.stringify(user)); } catch (e) {}
    return syncCompatSessionFromLocalAuth() || user;
  }

  function clearAuthState() {
    clearCompatSessionAuth();
    srm('ka_logged_in');
    ['ka_access_token', 'ka_current_user', 'ka_logged_in', 'ka_refresh_token'].forEach(lrm);
    normalizeStoredUserType(false);
  }

  function dispatchAuthStateChanged(source) {
    if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return;
    let event = null;
    if (typeof window.CustomEvent === 'function') {
      event = new window.CustomEvent('ka-auth-state-changed', { detail: { source: source || 'unknown' } });
    } else if (typeof Event === 'function') {
      event = new Event('ka-auth-state-changed');
      event.detail = { source: source || 'unknown' };
    } else {
      event = { type: 'ka-auth-state-changed', detail: { source: source || 'unknown' } };
    }
    window.dispatchEvent(event);
  }

  /* ─── State detection ────────────────────────────────────── */

  function detectRegime() {
    const declared = document.body && document.body.getAttribute('data-ka-regime');
    if (declared === 'global' || declared === '160sp') return declared;
    return location.pathname.indexOf('/160sp/') !== -1 ? '160sp' : 'global';
  }

  function detectSession() {
    const localUser = syncCompatSessionFromLocalAuth() || readCurrentUser();
    const hasToken = hasAccessToken();
    const isAdmin = g('ka.admin') === 'yes';
    const studentAuthed = g('ka.160.authed') === 'yes';
    const impersonating = g('ka.impersonating') === 'true';
    const userType = normalizeStoredUserType(isAdmin || studentAuthed);
    const email = g('ka.adminEmail') || g('ka.studentEmail') || (localUser && localUser.email) || null;

    // Authority rules, in order:
    //  1. An admin is always "admin", regardless of impersonation
    //     (the banner elsewhere communicates the impersonation)
    //  2. A signed-in 160 Student is "student"
    //  3. Any other signed-in account is "authenticated"
    //  4. Anyone else is "anonymous" — browsing in a presentation mode
    let authState;
    if (isAdmin) authState = 'admin';
    else if (studentAuthed) authState = 'student';
    else if (hasToken && localUser) authState = 'authenticated';
    else authState = 'anonymous';

    return { isAdmin, studentAuthed, impersonating, userType, email, authState };
  }

  /* ─── Path helpers (base prefix between regimes) ─────────── */

  // The nav always shows items for the CURRENT regime. This helper
  // prefixes hrefs when the current page is in 160sp/ but we want
  // to link to items whose hrefs were declared relative to /ka/.
  function prefixFor(regime, currentInClass) {
    if (regime === 'global' && currentInClass) return '../';
    if (regime === '160sp'  && !currentInClass) return '160sp/';
    return '';
  }
  function currentlyIn160sp() {
    return location.pathname.indexOf('/160sp/') !== -1;
  }

  /* ─── Style injection ────────────────────────────────────── */

  function injectStyles() {
    if (document.getElementById('ka-nav-styles')) return;
    const css = `
      :root {
        --ka-navy:#1C3D3A; --ka-teal:#2A7868; --ka-amber:#E8872A;
        --ka-gold:#F5A623; --ka-cream:#F7F4EF; --ka-panel:#F9F5EE;
        --ka-border:#E0D8CC; --ka-ink:#2C2C2C; --ka-muted:#6B6B6B;
      }
      .ka-skip { position:absolute; left:-9999px; top:auto; }
      .ka-skip:focus { left:8px; top:8px; padding:6px 10px; background:#fff;
        z-index:10000; border-radius:4px; color:var(--ka-navy); }

      .ka-nav { background:var(--ka-navy); color:#fff;
        display:flex; align-items:center; gap:18px; padding:0 24px;
        min-height:56px; position:sticky; top:0; z-index:500;
        box-shadow:0 2px 8px rgba(0,0,0,.15);
        font:500 .88rem -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
      }
      .ka-nav .ka-brand { display:flex; align-items:center; gap:10px;
        text-decoration:none; color:#fff; }
      .ka-nav .ka-brand .ka-mark { flex-shrink:0;
        filter: drop-shadow(0 1px 1.5px rgba(0,0,0,.25)); }
      .ka-nav .ka-brand .ka-mark,
      .ka-nav .ka-brand img.ka-mark,
      .ka-nav .ka-brand svg.ka-mark {
        width:30px; height:30px; min-width:30px; min-height:30px;
        max-width:30px; max-height:30px; display:block;
      }
      .ka-nav .ka-brand-mark { font-family:Georgia,serif; font-weight:800;
        letter-spacing:.02em; line-height:1.1; }
      .ka-nav .ka-brand-mark .k { color:#A8C8BF; font-size:.62rem;
        text-transform:uppercase; letter-spacing:.16em; display:block; }
      .ka-nav .ka-brand-mark .a { color:#fff; font-size:1.0rem; }
      .ka-nav .ka-brand-mark .las { color:var(--ka-gold); }
      /* .ka-regime-tag removed 2026-04-20 — rule retained as display:none
         so any cached-HTML variant that still renders the span keeps it
         hidden rather than showing inconsistently across pages. */
      .ka-nav .ka-regime-tag { display:none; }

      .ka-nav .ka-center { display:flex; align-items:center; gap:2px; flex:1;
        margin-left:14px; overflow-x:auto; }
      .ka-nav a.ka-link { color:#B8D4CE; text-decoration:none;
        padding:8px 12px; border-radius:6px; white-space:nowrap;
        transition:background .12s,color .12s; display:inline-flex;
        align-items:center; gap:6px; }
      .ka-nav a.ka-link:hover { background:rgba(255,255,255,.08); color:#fff; }
      .ka-nav a.ka-link.active { color:var(--ka-gold);
        background:rgba(232,135,42,.10);
        border-bottom:2px solid var(--ka-gold); }
      .ka-nav a.ka-link .stub { font-size:.58rem; text-transform:uppercase;
        letter-spacing:.08em; color:var(--ka-amber);
        border:1px solid var(--ka-amber); padding:1px 5px; border-radius:8px;
        background:rgba(232,135,42,.08); }

      .ka-nav .ka-right { display:flex; align-items:center; gap:10px;
        margin-left:auto; }
      .ka-nav .ka-pill { display:inline-flex; align-items:center; gap:6px;
        padding:4px 10px; border-radius:14px; font-size:.72rem;
        font-weight:600; letter-spacing:.04em; background:rgba(255,255,255,.08);
        color:#B8D4CE; border:1px solid rgba(255,255,255,.15); cursor:pointer;
        user-select:none; transition:background .12s, color .12s; }
      .ka-nav .ka-pill:hover { background:rgba(255,255,255,.14); color:#fff; }
      .ka-nav .ka-pill .caret { font-size:.6rem; opacity:.7; }
      .ka-nav .ka-pill-admin { background:var(--ka-amber); color:#fff;
        border-color:var(--ka-amber); }
      .ka-nav .ka-btn { padding:6px 12px; border-radius:6px; font-size:.8rem;
        font-weight:600; text-decoration:none; border:1px solid transparent;
        display:inline-flex; align-items:center; gap:4px;
        transition:background .12s, color .12s, border-color .12s; cursor:pointer; }
      .ka-nav .ka-btn-ghost { color:#fff; background:transparent;
        border-color:rgba(255,255,255,.22); }
      .ka-nav .ka-btn-ghost:hover { background:rgba(255,255,255,.12); }
      .ka-nav .ka-btn-cta { background:var(--ka-amber); color:#fff; }
      .ka-nav .ka-btn-cta:hover { background:#D27320; }

      /* Dropdown menu (user-type picker & account menu) */
      .ka-menu { position:fixed; background:#fff; color:var(--ka-ink);
        border:1px solid var(--ka-border); border-radius:10px;
        box-shadow:0 12px 36px rgba(0,0,0,.18); min-width:220px;
        z-index:600; padding:6px; display:none; font-size:.85rem; }
      .ka-menu.open { display:block; }
      .ka-menu .ka-menu-head { font-size:.66rem; text-transform:uppercase;
        letter-spacing:.12em; color:var(--ka-muted); font-weight:700;
        padding:8px 10px 4px; }
      .ka-menu .ka-menu-item { display:flex; align-items:center; gap:8px;
        padding:7px 10px; border-radius:6px; cursor:pointer; color:var(--ka-ink);
        text-decoration:none; }
      .ka-menu .ka-menu-item:hover { background:var(--ka-panel); }
      .ka-menu .ka-menu-item.active { background:#E6F5F0; color:var(--ka-teal);
        font-weight:600; }
      .ka-menu .ka-menu-sep { height:1px; background:var(--ka-border); margin:6px 0; }
      .ka-menu .ka-menu-gated { font-size:.66rem; color:var(--ka-amber);
        margin-left:auto; font-weight:700; letter-spacing:.04em; }
      .ka-menu .ka-menu-email { font-size:.78rem; color:var(--ka-muted);
        padding:2px 10px 8px; }

      /* Breadcrumbs */
      .ka-breadcrumb { background:#E8E0D4; padding:7px 24px; font-size:.78rem;
        color:#6A5A4A; display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
      .ka-breadcrumb a { color:var(--ka-navy); text-decoration:none; font-weight:600; }
      .ka-breadcrumb a:hover { text-decoration:underline; }
      .ka-breadcrumb .sep { color:#B0A898; }

      @media (max-width:720px) {
        .ka-nav { gap:8px; padding-left:8px; padding-right:8px; }
        .ka-nav .ka-center { margin-left:4px; }
        .ka-nav .ka-right { gap:6px; }
        .ka-nav .ka-regime-tag { display:none; }
        .ka-nav a.ka-link { padding:6px 8px; }
        .ka-nav .ka-btn { padding:5px 10px; font-size:.76rem; }
      }
    `;
    const tag = document.createElement('style');
    tag.id = 'ka-nav-styles';
    tag.textContent = css;
    document.head.appendChild(tag);
  }

  function ensureFavicon() {
    if (!document.head) return;
    if (document.querySelector('link[rel="icon"], link[rel="shortcut icon"]')) return;

    const base = currentlyIn160sp() ? '../' : '';

    const svg = document.createElement('link');
    svg.rel = 'icon';
    svg.type = 'image/svg+xml';
    svg.href = base + 'favicon.svg';
    svg.setAttribute('data-ka-managed', 'true');
    document.head.appendChild(svg);

    const ico = document.createElement('link');
    ico.rel = 'shortcut icon';
    ico.href = base + 'favicon.ico';
    ico.setAttribute('data-ka-managed', 'true');
    document.head.appendChild(ico);
  }

  /* ─── HTML builders ──────────────────────────────────────── */

  function buildBrand(regime) {
    // Wordmark/logo rule (Prof. Kirsh, 2026-04-27):
    //   * On a portal page (any 160sp page using THIS canonical navbar)
    //     → return to GLOBAL home.
    //   * On a global page → stay at global home.
    // Journey pages (t*_intro.html, t*_task*.html) use the inline top-nav
    // from _track_pages_shared.css and set their own wordmark target —
    // task pages → journey home, intros → portal — so they bypass this
    // builder entirely.
    const home = (regime === '160sp' && !currentlyIn160sp()) ? '../ka_home.html'
              : (regime === 'global' && currentlyIn160sp())  ? '../ka_home.html'
              : (regime === '160sp')                         ? '../ka_home.html'
              :                                                'ka_home.html';
    // Canonical Atlas logo: the linked-node mark already used on the login,
    // register, and user pages. This is the repo's recurring brand object,
    // unlike the brief triangle experiment that proved visually misleading.
    const mark = `
      <svg class="ka-mark" viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
        <circle cx="16" cy="16" r="3.5" fill="#F5A623"/>
        <circle cx="16" cy="5"  r="2.5" fill="#A8C8BF"/>
        <circle cx="27" cy="22" r="2.5" fill="#A8C8BF"/>
        <circle cx="5"  cy="22" r="2.5" fill="#A8C8BF"/>
        <line x1="16"   y1="7.5"  x2="16"   y2="12.5" stroke="#F5A623" stroke-width="1.5" stroke-opacity="0.9"/>
        <line x1="24.8" y1="20.2" x2="19.0" y2="17.3" stroke="#F5A623" stroke-width="1.5" stroke-opacity="0.9"/>
        <line x1="7.2"  y1="20.2" x2="13.0" y2="17.3" stroke="#F5A623" stroke-width="1.5" stroke-opacity="0.9"/>
        <line x1="16"   y1="7.5"  x2="25.5" y2="20" stroke="#FFFFFF" stroke-width="0.8" stroke-opacity="0.18"/>
        <line x1="25.5" y1="20" x2="6.5"   y2="20" stroke="#FFFFFF" stroke-width="0.8" stroke-opacity="0.18"/>
        <line x1="6.5"  y1="20" x2="16"    y2="7.5" stroke="#FFFFFF" stroke-width="0.8" stroke-opacity="0.18"/>
      </svg>`;
    return `
      <a class="ka-brand" href="${esc(home)}" aria-label="Knowledge Atlas home">
        ${mark}
        <span class="ka-brand-mark">
          <span class="k">Knowledge</span>
          <span class="a">At<span class="las">las</span></span>
        </span>
      </a>`;
  }

  function buildLinks(regime, activeId) {
    const items = REGIME_ITEMS[regime] || [];
    const inClass = currentlyIn160sp();
    const prefix = prefixFor(regime, inClass);
    return items.map(it => {
      // Items flagged global:true live at the root of the repo, not inside
      // the regime's directory. From a 160sp page they need '../'; from a
      // root-level page they are already adjacent.
      let href;
      if (it.global) {
        href = (inClass ? '../' : '') + it.href;
      } else {
        href = prefix + it.href;
      }
      const cls = 'ka-link' + (it.id === activeId ? ' active' : '');
      const stubBadge = it.stub ? ' <span class="stub">stub</span>' : '';
      return `<a class="${cls}" href="${esc(href)}" data-ka-id="${esc(it.id)}">${esc(it.label)}${stubBadge}</a>`;
    }).join('');
  }

  function buildRight(regime, session) {
    const { authState, userType, email, isAdmin } = session;
    const parts = [];

    // Admin badge first, if applicable
    if (isAdmin) {
      const adminHref = currentlyIn160sp() ? 'ka_admin.html' : '160sp/ka_admin.html';
      parts.push(`
        <a class="ka-pill ka-pill-admin" href="${esc(adminHref)}" title="Admin console">
          <span>★ Admin</span>
        </a>`);
      // Grader's Page (AG's autograder UI). Local stdlib server at :5050;
      // instructor must run `python3 160sp/grader_page/server.py` first.
      // Click handler probes the server before navigating; if unreachable,
      // tells the instructor exactly how to start it instead of dropping
      // them on a browser "could not connect" page.
      parts.push(`
        <a class="ka-pill ka-pill-admin" href="http://localhost:5050/" target="_blank" rel="noopener" title="AG autograder dashboard (probes server before opening)" data-ka-grader-pill="true">
          <span>🎓 Grader</span>
        </a>`);
    }

    // User-type / presentation-mode picker (always useful for non-students)
    if (authState !== 'student') {
      const current = (USER_TYPES_PUBLIC.concat(USER_TYPES_GATED))
        .find(u => u.id === userType) || USER_TYPES_PUBLIC[0];
      parts.push(`
        <button class="ka-pill" type="button" data-ka-menu="user-type"
                aria-haspopup="true" aria-expanded="false">
          <span>Viewing as: ${esc(current.label)}</span>
          <span class="caret">▾</span>
        </button>`);
    } else {
      parts.push(`
        <span class="ka-pill" title="You are a 160 Student">
          <span>160 Student</span>
        </span>`);
    }

    // Auth-state-specific controls
    if (authState === 'anonymous') {
      const loginHref = currentlyIn160sp() ? '../ka_login.html' : 'ka_login.html';
      const regHref   = currentlyIn160sp() ? '../ka_register.html' : 'ka_register.html';
      parts.push(`
        <a class="ka-btn ka-btn-ghost" href="${esc(loginHref)}">Log in</a>
        <a class="ka-btn ka-btn-cta"   href="${esc(regHref)}">Register →</a>`);
    } else {
      const initials = (email || '??').split('@')[0]
        .split(/[._-]/).map(s => s[0] || '').join('').slice(0,2).toUpperCase() || '??';
      parts.push(`
        <button class="ka-pill" type="button" data-ka-menu="account"
                aria-haspopup="true" aria-expanded="false" title="Account">
          <span>${esc(initials)}</span>
          <span class="caret">▾</span>
        </button>`);
    }

    return `<div class="ka-right">${parts.join('')}</div>`;
  }

  function buildNavbar(regime, session, activeId) {
    return `
      <a class="ka-skip" href="#ka-main">Skip to main content</a>
      <nav class="ka-nav" role="navigation" aria-label="Primary">
        ${buildBrand(regime)}
        <div class="ka-center">${buildLinks(regime, activeId)}</div>
        ${buildRight(regime, session)}
      </nav>`;
  }

  function buildBreadcrumb() {
    const raw = document.body && document.body.getAttribute('data-ka-crumbs');
    if (!raw) return '';
    let crumbs; try { crumbs = JSON.parse(raw); } catch (e) { return ''; }
    if (!Array.isArray(crumbs) || crumbs.length === 0) return '';
    return `<div class="ka-breadcrumb" aria-label="Breadcrumb">` +
      crumbs.map(([label, href], i) => {
        const sep = i === 0 ? '' : '<span class="sep">›</span>';
        return sep + (href ? `<a href="${esc(href)}">${esc(label)}</a>` : `<span>${esc(label)}</span>`);
      }).join('') +
    `</div>`;
  }

  /* ─── Menus (user-type picker & account menu) ────────────── */

  function openMenu(trigger, kind, session) {
    closeAllMenus();
    const rect = trigger.getBoundingClientRect();
    const menu = document.createElement('div');
    menu.className = 'ka-menu open';
    menu.setAttribute('role', 'menu');
    menu.style.top  = (rect.bottom + 6) + 'px';
    menu.style.right = (window.innerWidth - rect.right) + 'px';
    menu.innerHTML = kind === 'user-type' ? userTypeMenuHtml(session)
                                          : accountMenuHtml(session);
    document.body.appendChild(menu);
    trigger.setAttribute('aria-expanded', 'true');
    trigger._menu = menu;
    menu.addEventListener('click', ev => {
      const t = ev.target.closest('[data-action]');
      if (!t) return;
      ev.preventDefault();
      handleMenuAction(t.dataset.action, t.dataset.value || t.getAttribute('href') || '');
    });
  }
  function closeAllMenus() {
    document.querySelectorAll('.ka-menu').forEach(m => m.remove());
    document.querySelectorAll('[data-ka-menu]').forEach(t =>
      t.setAttribute('aria-expanded', 'false'));
  }
  function userTypeMenuHtml(session) {
    const cur = session.userType;
    const can = (t) => t.id !== '160-student' || session.isAdmin || session.studentAuthed;
    const row = (t, gated) => `
      <a class="ka-menu-item ${cur===t.id?'active':''}" href="#"
         data-action="set-user-type" data-value="${esc(t.id)}">
        <span>${esc(t.label)}</span>
        ${gated && !can(t) ? '<span class="ka-menu-gated">gated</span>' : ''}
      </a>`;
    return `
      <div class="ka-menu-head">Presentation mode</div>
      ${USER_TYPES_PUBLIC.map(t => row(t, false)).join('')}
      <div class="ka-menu-sep"></div>
      <div class="ka-menu-head">Requires sign-in</div>
      ${USER_TYPES_GATED.map(t => row(t, true)).join('')}`;
  }
  function accountMenuHtml(session) {
    const items = [];
    items.push(`<div class="ka-menu-head">Signed in</div>`);
    items.push(`<div class="ka-menu-email">${esc(session.email || '(no email)')}</div>`);
    if (session.isAdmin) {
      items.push(`<a class="ka-menu-item" href="${currentlyIn160sp()?'':'160sp/'}ka_admin.html"
        data-action="navigate">Admin console</a>`);
    }
    if (session.studentAuthed) {
      items.push(`<a class="ka-menu-item" href="${currentlyIn160sp()?'':'160sp/'}ka_student_profile.html"
        data-action="navigate">My profile</a>`);
    }
    items.push(`<div class="ka-menu-sep"></div>`);
    items.push(`<a class="ka-menu-item" href="#" data-action="sign-out">Sign out</a>`);
    return items.join('');
  }

  function handleMenuAction(action, value) {
    if (action === 'set-user-type') {
      s('ka.userType', value);
      if (g('ka.admin') === 'yes') s('ka.impersonating', 'true');
      closeAllMenus();
      KA.nav.refresh();
    } else if (action === 'sign-out') {
      clearAuthState();
      dispatchAuthStateChanged('sign-out');
      location.reload();
    } else if (action === 'navigate') {
      closeAllMenus();
      if (value && value !== '#') {
        if (typeof window !== 'undefined' && window.location && typeof window.location.assign === 'function') {
          window.location.assign(value);
        } else if (typeof location !== 'undefined') {
          location.href = value;
        }
      }
    }
  }

  /* ─── Event wiring ───────────────────────────────────────── */

  function wireTriggers() {
    const session = detectSession();
    document.querySelectorAll('[data-ka-menu]').forEach(trigger => {
      trigger.addEventListener('click', ev => {
        ev.stopPropagation();
        const kind = trigger.getAttribute('data-ka-menu');
        const already = trigger.getAttribute('aria-expanded') === 'true';
        closeAllMenus();
        if (!already) openMenu(trigger, kind, session);
      });
    });
    document.addEventListener('click', ev => {
      if (!ev.target.closest('.ka-menu') && !ev.target.closest('[data-ka-menu]')) {
        closeAllMenus();
      }
    });
    document.addEventListener('keydown', ev => {
      if (ev.key === 'Escape') closeAllMenus();
    });
  }

  function bindStateRefresh() {
    if (KA.nav && KA.nav._stateRefreshBound) return;
    const refresh = () => {
      if (KA.nav && typeof KA.nav.refresh === 'function') KA.nav.refresh();
    };
    const watch = key => (
      !key ||
      key === 'ka_access_token' ||
      key === 'ka_refresh_token' ||
      key === 'ka_current_user' ||
      key === 'ka_logged_in' ||
      key === 'ka.userType' ||
      key === 'ka.admin' ||
      key === 'ka.160.authed'
    );
    if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
      window.addEventListener('pageshow', refresh);
      window.addEventListener('focus', refresh);
      window.addEventListener('ka-auth-state-changed', refresh);
      window.addEventListener('storage', ev => {
        if (watch(ev && ev.key)) refresh();
      });
    }
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') refresh();
      });
    }
    if (!KA.nav) KA.nav = {};
    KA.nav._stateRefreshBound = true;
  }

  function retireLegacyTopNavs(regime) {
    const markers = regime === '160sp'
      ? ['160 Syllabus', 'COGS 160', '160 Student Profile', 'Track 1', 'Track 2', 'Track 3', 'Track 4']
      : ['Articles', 'Topics', 'Theories', 'Mechanisms', 'Neural Underpinnings', 'Contribute', 'About'];

    document.querySelectorAll('body > nav').forEach(nav => {
      if (nav.querySelector('.ka-nav')) return;
      if (nav.dataset.kaNavReplaced === 'true') return;
      if (nav.dataset.kaKeepLegacyNav === 'true') return;

      const text = (nav.textContent || '').replace(/\s+/g, ' ').trim();
      const looksLikeLegacy =
        markers.some(marker => text.includes(marker)) ||
        nav.classList.contains('topnav') ||
        nav.querySelector('.nav-brand, .nav-link, .wordmark, .ka-wordmark');

      if (!looksLikeLegacy) return;

      nav.style.display = 'none';
      nav.setAttribute('aria-hidden', 'true');
      nav.dataset.kaNavReplaced = 'true';
    });
  }

  /* ─── Mount ──────────────────────────────────────────────── */

  function ensureSlot(id, where) {
    let el = document.getElementById(id);
    if (el) return el;
    el = document.createElement('div');
    el.id = id;
    if (where === 'top') document.body.insertBefore(el, document.body.firstChild);
    else document.body.appendChild(el);
    return el;
  }

  function mount() {
    injectStyles();
    ensureFavicon();
    const regime = detectRegime();
    const session = detectSession();
    const activeId = (document.body && document.body.getAttribute('data-ka-active')) || '';

    const navSlot   = ensureSlot('ka-navbar-slot', 'top');
    const crumbSlot = ensureSlot('ka-breadcrumb-slot', 'top');
    // ensure breadcrumb sits right after navbar
    if (crumbSlot.previousElementSibling !== navSlot) {
      navSlot.parentNode.insertBefore(crumbSlot, navSlot.nextSibling);
    }

    navSlot.innerHTML   = buildNavbar(regime, session, activeId);
    crumbSlot.innerHTML = buildBreadcrumb();

    retireLegacyTopNavs(regime);
    wireTriggers();
  }

  /* ─── Public API ─────────────────────────────────────────── */

  KA.nav = Object.assign(KA.nav || {}, {
    mount,
    refresh: mount,              // re-render from current state
    detectRegime,
    detectSession,
    setActive(id) { if (document.body) document.body.setAttribute('data-ka-active', id); mount(); },
    REGIME_ITEMS,                // exposed for inspection / tests
  });
  KA.authState = {
    clear: clearAuthState,
    notify: dispatchAuthStateChanged,
    primeFromUser,
    syncCompatSessionFromLocalAuth,
  };

  /* ─── Grader pill probe ───────────────────────────────────────
   * The 🎓 Grader pill points at http://localhost:5050/ but that
   * server is optional — instructors run it ad-hoc. Without a probe,
   * a click when the server is not running drops the user on the
   * browser's "could not connect" page with no in-app explanation.
   * The handler below intercepts the click, attempts a 1-second
   * fetch with no-cors mode (so reachability is what we test, not
   * CORS), and either lets the navigation proceed or shows a small
   * inline tooltip telling the instructor exactly how to start the
   * server. The pill is identified by data-ka-grader-pill="true".
   * ───────────────────────────────────────────────────────────── */
  function wireGraderPillProbe() {
    document.addEventListener('click', function(ev) {
      const pill = ev.target.closest('[data-ka-grader-pill="true"]');
      if (!pill) return;
      ev.preventDefault();
      const url = pill.getAttribute('href');
      const ctrl = new AbortController();
      const timeout = setTimeout(() => ctrl.abort(), 1000);
      fetch(url, { mode: 'no-cors', signal: ctrl.signal })
        .then(() => {
          clearTimeout(timeout);
          window.open(url, '_blank', 'noopener');
        })
        .catch(() => {
          clearTimeout(timeout);
          // Build a small toast inline (no dependencies on existing toast lib).
          const existing = document.querySelector('.ka-grader-pill-toast');
          if (existing) existing.remove();
          const toast = document.createElement('div');
          toast.className = 'ka-grader-pill-toast';
          toast.style.cssText = [
            'position:fixed', 'top:64px', 'right:16px', 'z-index:99999',
            'max-width:360px', 'background:#fff8eb', 'color:#2C2C2C',
            'border:1px solid #E8872A', 'border-radius:6px',
            'padding:12px 14px', 'box-shadow:0 2px 12px rgba(0,0,0,0.15)',
            'font-family:Arial,sans-serif', 'font-size:13px', 'line-height:1.45'
          ].join(';');
          toast.innerHTML =
            '<strong>Grader server is not running.</strong><br>' +
            'Start it from a terminal:<br>' +
            '<code style="display:block;margin:6px 0;padding:6px 8px;background:#f4ead4;border-radius:3px;font-size:12px;">' +
            'cd 160sp/grader_page &amp;&amp; python3 server.py' +
            '</code>' +
            'Then click 🎓 Grader again. ' +
            '<a href="#" onclick="this.closest(\'.ka-grader-pill-toast\').remove();return false;" ' +
            'style="float:right;color:#9a5010;font-weight:600;text-decoration:none;">×</a>';
          document.body.appendChild(toast);
          setTimeout(() => { if (toast.parentNode) toast.remove(); }, 12000);
        });
    });
  }

  /* ─── Boot ───────────────────────────────────────────────── */

  bindStateRefresh();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      mount();
      wireGraderPillProbe();
    });
  } else {
    mount();
    wireGraderPillProbe();
  }
})();
