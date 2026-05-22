/* ka_fall_journey_nav.js
 * Persistent left-rail step navigation for the COGS 160 Fall Week-1 journey.
 *
 * Each of the ten journey surfaces loads this script with a single tag:
 *     <script src="ka_fall_journey_nav.js" defer></script>
 *
 * The script identifies the current page from its filename, then:
 *   - wraps the page's existing <div class="wrap"> in a two-column shell
 *   - injects a sticky left sidebar listing all ten steps, grouped, with
 *     the current step marked .current and earlier steps marked .done
 *   - appends a previous / continue control to the end of the content,
 *     before the instructor annotations block
 *
 * To reorder or relabel the journey, edit only the JOURNEY manifest below;
 * the HTML across all ten surfaces does not change.
 *
 * Author: Cowork session for Prof. David Kirsh, COGS 160 Fall, 2026-05-21.
 */
(function () {
  'use strict';

  /* ─────────────────────────────────────────────────────────────
   * Journey manifest. Order = sidebar order = previous/continue order.
   * id matches the page filename (without the .html extension).
   * ───────────────────────────────────────────────────────────── */
  var JOURNEY = [
    { id: 'ka_fall_week1',              label: 'Week-1 landing',            group: 'Start' },
    { id: 'ka_fall_dyk_browser',        label: 'Browse all topics',         group: 'Find your topic' },
    { id: 'ka_fall_topic',              label: 'Explore a topic',           group: 'Find your topic' },
    { id: 'ka_evaluate_paper_for_vr',   label: 'Evaluate a paper for VR',   group: 'Test it for VR' },
    { id: 'ka_choose_measure_for_vr',   label: 'Choose a measure',          group: 'Test it for VR' },
    { id: 'ka_vr_measurability',        label: 'What VR can measure',       group: 'Reference reading' },
    { id: 'ka_methodological_pitfalls', label: 'Methodological pitfalls',   group: 'Reference reading' },
    { id: 'ka_validities_showcase',     label: 'The four validities',       group: 'Reference reading' },
    { id: 'ka_vr_exemplars',            label: 'Exemplary VR experiments',  group: 'Reference reading' },
    { id: 'ka_fall_week1_deliverable',  label: 'Week-1 deliverable',        group: 'Finish' }
  ];
  var MAP_HREF = 'ka_journey_map.html';

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function currentId() {
    return (location.pathname.split('/').pop() || '').replace(/\.html?$/i, '');
  }

  function indexOfId(id) {
    for (var i = 0; i < JOURNEY.length; i++) {
      if (JOURNEY[i].id === id) return i;
    }
    return -1;
  }

  /* ─────────────────────────────────────────────────────────────
   * Sidebar — the persistent left rail.
   * ───────────────────────────────────────────────────────────── */
  function buildSidebar(curIdx) {
    var parts = ['<div class="journey-nav-head">Week-1 journey</div>'];
    if (curIdx >= 0) {
      parts.push('<div class="journey-nav-progress">Step ' + (curIdx + 1) +
                 ' of ' + JOURNEY.length + '</div>');
    }
    var lastGroup = null;
    JOURNEY.forEach(function (step, i) {
      if (step.group !== lastGroup) {
        parts.push('<div class="journey-nav-group">' + esc(step.group) + '</div>');
        lastGroup = step.group;
      }
      var cls = 'journey-nav-item';
      var isCurrent = (i === curIdx);
      if (isCurrent) cls += ' current';
      else if (curIdx >= 0 && i < curIdx) cls += ' done';
      parts.push(
        '<a class="' + cls + '" href="' + esc(step.id) + '.html"' +
          (isCurrent ? ' aria-current="page"' : '') + '>' +
          '<span class="journey-nav-num" aria-hidden="true">' + (i + 1) + '</span>' +
          '<span class="journey-nav-label">' + esc(step.label) + '</span>' +
        '</a>'
      );
    });
    parts.push('<a class="journey-nav-map" href="' + esc(MAP_HREF) +
               '">Full journey map &rarr;</a>');
    return parts.join('');
  }

  /* ─────────────────────────────────────────────────────────────
   * Previous / Continue control at the foot of the content column.
   * ───────────────────────────────────────────────────────────── */
  function buildPrevNext(curIdx) {
    if (curIdx < 0) return null;
    var prev = curIdx > 0 ? JOURNEY[curIdx - 1] : null;
    var next = curIdx < JOURNEY.length - 1 ? JOURNEY[curIdx + 1] : null;
    var html = '<nav class="journey-prevnext" aria-label="Journey step navigation">';
    if (prev) {
      html += '<a class="journey-pn journey-pn-prev" href="' + esc(prev.id) + '.html">' +
                '<span class="journey-pn-dir">&larr; Previous step</span>' +
                '<span class="journey-pn-label">' + esc(prev.label) + '</span>' +
              '</a>';
    } else {
      html += '<span class="journey-pn journey-pn-empty" aria-hidden="true"></span>';
    }
    if (next) {
      html += '<a class="journey-pn journey-pn-next" href="' + esc(next.id) + '.html">' +
                '<span class="journey-pn-dir">Continue to the next step &rarr;</span>' +
                '<span class="journey-pn-label">' + esc(next.label) + '</span>' +
              '</a>';
    } else {
      html += '<a class="journey-pn journey-pn-next journey-pn-done" href="' + esc(MAP_HREF) + '">' +
                '<span class="journey-pn-dir">Journey complete &rarr;</span>' +
                '<span class="journey-pn-label">Back to the journey map</span>' +
              '</a>';
    }
    html += '</nav>';
    return html;
  }

  /* ─────────────────────────────────────────────────────────────
   * Boot — restructure the page into [ sidebar | content ].
   * ───────────────────────────────────────────────────────────── */
  function boot() {
    var wrap = document.querySelector('div.wrap');
    if (!wrap || wrap.getAttribute('data-journey-wired') === '1') return;
    var curIdx = indexOfId(currentId());

    var shell = document.createElement('div');
    shell.className = 'journey-shell';

    var aside = document.createElement('aside');
    aside.className = 'journey-nav';
    aside.setAttribute('aria-label', 'Week-1 journey steps');
    aside.innerHTML = buildSidebar(curIdx);

    wrap.parentNode.insertBefore(shell, wrap);
    shell.appendChild(aside);
    shell.appendChild(wrap);
    wrap.setAttribute('data-journey-wired', '1');

    var pnHtml = buildPrevNext(curIdx);
    if (pnHtml) {
      var holder = document.createElement('div');
      holder.innerHTML = pnHtml;
      var pn = holder.firstChild;
      var annotations = wrap.querySelector('.annotations');
      if (annotations) {
        wrap.insertBefore(pn, annotations);
      } else {
        wrap.appendChild(pn);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
