/* MVR Enhancer — frontend application logic.
 *
 * Vanilla ES2020, no framework, no build step. Wires the static layout
 * (index.html / css/app.css, Task 12) to the pywebview bridge exposed as
 * ``window.pywebview.api`` (mvr_enhancer/api.py, Task 10).
 *
 * Local UI state is limited to `aktiv` (which accordion step is open) and
 * `nurProbleme` (table filter) — everything else is derived from the
 * server's `get_state()` payload, kept in `serverState` and refreshed
 * whenever a `{type:"state", data}` event arrives from Python (or a direct
 * API call resolves with a full state dict).
 *
 * This file must survive being loaded in a plain browser (no pywebview at
 * all): every bridge call is guarded, and the initial render always uses
 * EMPTY_STATE so the page shows the empty/unloaded UI silently.
 */

(function () {
  "use strict";

  // ──── Empty/default state (browser-mode fallback + first paint) ────

  var EMPTY_STATE = {
    mvr_loaded: false,
    file_meta: {},
    stats: null,
    types: [],
    grouping: true,
    share: { logged_in: false, user: "" },
    library: { dir: "", count: 0 },
    recent: [],
    warnings: { fallbacks: [], collisions: [], cleanup_preview: null },
    export: { done: false, path: "", size_mb: 0, time: "", default_path: "" },
    assigned_count: 0,
    open_count: 0,
  };

  // ──── Module state ────

  var serverState = null; // last known get_state() payload, or null until first load
  var localState = { aktiv: 1, nurProbleme: false };
  var lastExportReport = null; // EnrichReport from the last run_export "result" event
  var exporting = false;
  var pendingLoginModal = false;
  var autoAdvanceTimer = null;
  var searchDebounceTimer = null;
  var toasts = [];
  var toastSeq = 0;
  var searchModal = {
    typeKey: null,
    typeName: "",
    results: [],
    loading: false,
    downloadingRid: null,
  };

  // ──── Small helpers ────

  function esc(value) {
    return String(value === undefined || value === null ? "" : value).replace(
      /[&<>"']/g,
      function (ch) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
      }
    );
  }

  function formatNumber(n, decimals) {
    if (typeof n !== "number" || Number.isNaN(n)) return "0";
    var d = decimals === undefined ? 2 : decimals;
    return n.toFixed(d).replace(".", ",");
  }

  function formatDateTime(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    function pad(x) {
      return String(x).padStart(2, "0");
    }
    return (
      pad(d.getDate()) + "." + pad(d.getMonth() + 1) + "." + d.getFullYear() +
      " " + pad(d.getHours()) + ":" + pad(d.getMinutes())
    );
  }

  function formatFileMeta(fileMeta) {
    var size = formatNumber(fileMeta.size_mb, 1);
    var modified = formatDateTime(fileMeta.modified);
    return size + " MB" + (modified ? " · geändert " + modified : "");
  }

  function $(id) {
    return document.getElementById(id);
  }

  function bootstrapIcons() {
    document.querySelectorAll("[data-icon]").forEach(function (el) {
      el.innerHTML = (window.ICONS && window.ICONS[el.getAttribute("data-icon")]) || "";
    });
  }

  // ──── Bridge ────

  /**
   * Calls window.pywebview.api.<method>(...args), guarded so it never
   * throws — safe to call even with no pywebview present (browser mode).
   *
   * If the resolved {ok:true, data} payload looks like a full get_state()
   * dict (has "mvr_loaded"), applies it immediately: several API methods
   * (remove_mvr, set_gdtf, set_mode, set_removed, set_grouping,
   * prepare_export, reset_export, ...) run synchronously and return the
   * fresh state directly rather than via an onEvent "state" push. Methods
   * that run as background threads in production return {started:true}
   * instead — those updates arrive later through onEvent, handled by
   * applyState()/handleResult() independently of this function.
   */
  function callApi(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api[method] !== "function") {
      return Promise.resolve({ ok: false, error: "Keine Verbindung zur Anwendung." });
    }
    var promise;
    try {
      promise = window.pywebview.api[method].apply(window.pywebview.api, args);
    } catch (err) {
      return Promise.resolve({ ok: false, error: String(err) });
    }
    return Promise.resolve(promise)
      .then(function (result) {
        if (result && result.ok) {
          if (result.data && typeof result.data === "object" && !Array.isArray(result.data) && "mvr_loaded" in result.data) {
            applyState(result.data);
          }
        } else if (result && !result.ok) {
          pushToast("error", result.error || "Unbekannter Fehler.");
        }
        return result || { ok: false, error: "Keine Antwort erhalten." };
      })
      .catch(function (err) {
        pushToast("error", "Verbindung zur Anwendung fehlgeschlagen.");
        return { ok: false, error: String(err) };
      });
  }

  function applyState(newState) {
    var wasLoaded = serverState ? serverState.mvr_loaded : false;
    var wasLoggedIn = serverState ? serverState.share.logged_in : false;
    serverState = newState;

    if (!wasLoaded && newState.mvr_loaded) {
      scheduleAutoAdvance();
    } else if (wasLoaded && !newState.mvr_loaded) {
      cancelAutoAdvance();
    }

    if (exporting && newState.export.done) {
      exporting = false;
    }

    if (pendingLoginModal && !wasLoggedIn && newState.share.logged_in) {
      closeModal("modal-share-login");
      pendingLoginModal = false;
    }

    render();
  }

  /**
   * Switches the local accordion step and re-renders. Also mirrors the step
   * to the backend via set_active_step() — per the implementation plan this
   * exists purely for window-title bookkeeping (the accordion state itself
   * always stays client-side), so the call is fire-and-forget.
   */
  function goToStep(n) {
    localState.aktiv = n;
    callApi("set_active_step", n);
    render();
  }

  function scheduleAutoAdvance() {
    cancelAutoAdvance();
    autoAdvanceTimer = setTimeout(function () {
      autoAdvanceTimer = null;
      goToStep(2);
    }, 750);
  }

  function cancelAutoAdvance() {
    if (autoAdvanceTimer) {
      clearTimeout(autoAdvanceTimer);
      autoAdvanceTimer = null;
    }
  }

  // ──── window.app.onEvent — Python → JS event channel ────

  function onEvent(evt) {
    if (!evt || !evt.type) return;
    switch (evt.type) {
      case "state":
        applyState(evt.data);
        break;
      case "result":
        handleResult(evt.method, evt.data);
        break;
      case "toast":
        handleToastEvent(evt);
        break;
      case "progress":
        // No dedicated progress UI in this iteration — intentionally a no-op.
        break;
      default:
        break;
    }
  }

  function handleToastEvent(evt) {
    var message = evt.message || evt.text || "Unbekannter Fehler.";
    if (pendingLoginModal && evt.level === "error") {
      showLoginError(message);
      pendingLoginModal = false;
    }
    pushToast(evt.level || "error", message);
  }

  function handleResult(method, data) {
    if (method === "share_search") {
      if (Array.isArray(data)) {
        searchModal.results = data;
        searchModal.loading = false;
        renderSearchModal();
      }
    } else if (method === "share_download") {
      finishDownload(data);
    } else if (method === "run_export") {
      handleRunExportResult(data);
    }
    // load_mvr / rescan_library / share_login / share_logout / startup:
    // no extra handling needed — the paired "state" event already re-rendered.
  }

  function handleRunExportResult(data) {
    exporting = false;
    if (data && data.report) {
      lastExportReport = data.report;
    }
    render();
  }

  function finishDownload(stateData) {
    var typeKey = searchModal.typeKey;
    var type = null;
    if (typeKey && stateData && Array.isArray(stateData.types)) {
      type = stateData.types.find(function (t) {
        return t.key === typeKey;
      });
    }
    closeModal("modal-share-search");
    if (type && type.assignment && type.assignment.gdtf_name) {
      pushToast("info", esc(type.assignment.gdtf_name) + " heruntergeladen und zugeordnet.");
    } else {
      pushToast("info", "GDTF heruntergeladen.");
    }
  }

  // ──── Toasts ────

  function pushToast(level, text) {
    if (!text) return;
    var id = ++toastSeq;
    toasts.push({ id: id, level: level, text: text });
    renderToasts();
    var timeout = level === "error" ? 8000 : 4000;
    setTimeout(function () {
      dismissToast(id);
    }, timeout);
  }

  function dismissToast(id) {
    toasts = toasts.filter(function (t) {
      return t.id !== id;
    });
    renderToasts();
  }

  function renderToasts() {
    var el = $("toast-stack");
    if (!el) return;
    el.innerHTML = toasts
      .map(function (t) {
        return '<div class="toast toast-' + esc(t.level) + '">' + esc(t.text) + "</div>";
      })
      .join("");
  }

  // ──── Modals ────

  function openModal(id) {
    var el = $(id);
    if (el) el.classList.remove("hidden");
  }

  function closeModal(id) {
    var el = $(id);
    if (el) el.classList.add("hidden");
    if (id === "modal-share-login") {
      hideLoginError();
      $("share-login-pass").value = "";
      pendingLoginModal = false;
    }
    if (id === "modal-share-search") {
      searchModal = { typeKey: null, typeName: "", results: [], loading: false, downloadingRid: null };
    }
  }

  function showLoginError(message) {
    var el = $("share-login-error");
    el.textContent = message;
    el.classList.remove("hidden");
  }

  function hideLoginError() {
    var el = $("share-login-error");
    el.textContent = "";
    el.classList.add("hidden");
  }

  function openSearchModal(typeKey, typeName) {
    searchModal = {
      typeKey: typeKey,
      typeName: typeName || "",
      results: [],
      loading: false,
      downloadingRid: null,
    };
    $("share-search-input").value = searchModal.typeName;
    openModal("modal-share-search");
    renderSearchModal();
    doSearch(searchModal.typeName);
  }

  function doSearch(query) {
    var s = serverState || EMPTY_STATE;
    if (!s.share.logged_in) {
      searchModal.results = [];
      searchModal.loading = false;
      renderSearchModal();
      return;
    }
    searchModal.loading = true;
    renderSearchModal();
    callApi("share_search", query).then(function (result) {
      if (result.ok && Array.isArray(result.data)) {
        searchModal.results = result.data;
        searchModal.loading = false;
        renderSearchModal();
      } else if (!result.ok) {
        searchModal.loading = false;
        renderSearchModal();
      }
      // else: production stub {started:true} — real results arrive via
      // the "result" event handled in handleResult().
    });
  }

  function downloadShareResult(rid) {
    if (!searchModal.typeKey) return;
    searchModal.downloadingRid = rid;
    renderSearchModal();
    callApi("share_download", rid, searchModal.typeKey).then(function (result) {
      if (!result.ok) {
        searchModal.downloadingRid = null;
        renderSearchModal();
        return;
      }
      if (result.data && typeof result.data === "object" && "mvr_loaded" in result.data) {
        // Sync-mode/test path: the full state came back directly.
        finishDownload(result.data);
      }
      // else: production path — the "result" event (method share_download)
      // calls finishDownload() once Python pushes it.
    });
  }

  function renderSearchModal() {
    var hint = $("share-search-hint");
    var results = $("share-results");
    var s = serverState || EMPTY_STATE;
    if (!s.share.logged_in) {
      hint.textContent = "Bitte melde dich zuerst beim GDTF Share an.";
      results.innerHTML = "";
      return;
    }
    if (searchModal.loading) {
      hint.textContent = "Suche läuft…";
      results.innerHTML = "";
      return;
    }
    if (!searchModal.results.length) {
      hint.textContent = "Keine Treffer.";
      results.innerHTML = "";
      return;
    }
    hint.textContent = "Verbindung zum GDTF Share erforderlich.";
    results.innerHTML = searchModal.results.map(renderSearchResultRow).join("");
  }

  function renderSearchResultRow(item) {
    var name = ((item.manufacturer || "") + " " + (item.fixture || "")).trim();
    var metaParts = [];
    if (item.revision) metaParts.push(String(item.revision));
    if (item.rating !== undefined && item.rating !== null) metaParts.push("Bewertung " + item.rating);
    var meta = metaParts.join(" · ");
    var downloading = searchModal.downloadingRid === item.rid;
    return (
      '<div class="share-result-row">' +
      "<div>" +
      '<div class="share-result-name">' + esc(name) + "</div>" +
      (meta ? '<div class="share-result-meta">' + esc(meta) + "</div>" : "") +
      "</div>" +
      '<button type="button" class="btn btn-outline btn-sm btn-share-download" data-rid="' +
      esc(item.rid) +
      '" ' + (downloading ? "disabled" : "") + ">" +
      (downloading ? "Lädt…" : "Übernehmen") +
      "</button>" +
      "</div>"
    );
  }

  // ──── Master render ────

  function render() {
    var s = serverState || EMPTY_STATE;
    renderAccordion(s);
    renderSection1(s);
    renderSection2(s);
    renderSection3(s);
    renderSearchModal();
    renderToasts();
    bootstrapIcons();
  }

  // ──── Accordion (rail + headers) ────

  function iconSpanHtml(name, classes) {
    return '<span class="icon ' + classes + '" data-icon="' + name + '"></span>';
  }

  function setNode(n, isActive, isDone) {
    var node = $("node-" + n);
    node.classList.toggle("active", isActive);
    node.classList.toggle("done", isDone && !isActive);
    if (n === 3) {
      node.innerHTML = isDone
        ? iconSpanHtml("check", "ic-20 ic-blue300")
        : iconSpanHtml("arrow-down-to-line", "ic-20 ic-white");
    } else if (isDone && !isActive) {
      node.innerHTML = iconSpanHtml("check", "ic-20 ic-blue300");
    } else {
      node.textContent = "0" + n;
    }
  }

  function renderAccordion(s) {
    var f1 = s.mvr_loaded;
    var f2 = s.mvr_loaded && (localState.aktiv === 3 || s.export.done);
    var f3 = s.export.done;

    $("sect-1").classList.toggle("active", localState.aktiv === 1);
    $("sect-2").classList.toggle("active", localState.aktiv === 2);
    $("sect-3").classList.toggle("active", localState.aktiv === 3);

    setNode(1, localState.aktiv === 1, f1);
    setNode(2, localState.aktiv === 2, f2);
    setNode(3, localState.aktiv === 3, f3);

    $("sum-1").textContent = f1
      ? (s.file_meta.name || "") + " · " + (s.stats ? s.stats.fixtures : 0) + " Fixtures · " +
        (s.stats ? s.stats.meshes : 0) + " Meshes"
      : "noch keine Datei geladen";

    $("match-badge").textContent = s.assigned_count + " von " + s.types.length + " zugeordnet";
    $("sum-2").textContent = f1
      ? s.assigned_count + " von " + s.types.length + " Typen zugeordnet · " + s.open_count + " offene Punkte"
      : "wartet auf Quell-MVR";

    var warnCount = s.warnings.fallbacks.length + s.warnings.collisions.length;
    var sum3;
    if (s.export.done) {
      sum3 = "exportiert · " + s.export.time;
    } else if (f1 && s.warnings.cleanup_preview) {
      sum3 = "bereit · " + warnCount + " Warnungen";
    } else {
      sum3 = "wartet auf Matching";
    }
    $("sum-3").textContent = sum3;
  }

  // ──── Section 1 · Quelle ────

  function renderSection1(s) {
    $("dropzone").classList.toggle("hidden", s.mvr_loaded);
    $("filecard-block").classList.toggle("hidden", !s.mvr_loaded);

    if (s.mvr_loaded) {
      $("filecard-name").textContent = s.file_meta.name || "";
      $("filecard-sub").textContent = formatFileMeta(s.file_meta);
      var stats = s.stats || { fixtures: 0, fixture_types: 0, meshes: 0, positions: 0 };
      $("stat-fixtures").textContent = stats.fixtures;
      $("stat-types").textContent = stats.fixture_types;
      $("stat-meshes").textContent = stats.meshes;
      $("stat-positions").textContent = stats.positions;
    }

    renderRecentList(s.recent);
  }

  function renderRecentList(recent) {
    var el = $("recent-list");
    if (!recent.length) {
      el.innerHTML = '<div class="muted-text">noch keine Historie</div>';
      return;
    }
    el.innerHTML = recent
      .map(function (entry) {
        return (
          '<div class="recent-row" data-path="' + esc(entry.path) + '">' +
          iconSpanHtml("file-box", "ic-16 ic-blue300") +
          '<span class="recent-name">' + esc(entry.name) + "</span>" +
          '<span class="recent-time">' + esc(formatDateTime(entry.ts)) + "</span>" +
          "</div>"
        );
      })
      .join("");
  }

  // ──── Section 2 · Matching ────

  function renderSection2(s) {
    var pathEl = $("library-path");
    pathEl.innerHTML = s.library.dir
      ? esc(s.library.dir) + ' <span class="muted">· ' + s.library.count + " Dateien</span>"
      : 'Kein Bibliotheksordner gewählt <span class="muted">· 0 Dateien</span>';

    $("share-status-in").classList.toggle("hidden", !s.share.logged_in);
    $("share-status-out").classList.toggle("hidden", s.share.logged_in);
    if (s.share.logged_in) {
      $("share-user-name").textContent = s.share.user || "";
    }

    $("chk-gruppieren").checked = !!s.grouping;

    renderMatchTable(s);
  }

  function isFilterProblem(assignment) {
    return !!(assignment.removed || !assignment.gdtf_name || assignment.mode_is_fallback);
  }

  function isStylingProblem(assignment) {
    return !assignment.removed && (!assignment.gdtf_name || assignment.mode_is_fallback);
  }

  function findCandidate(type, gdtfName) {
    if (!gdtfName) return null;
    return type.candidates.find(function (c) {
      return c.gdtf_name === gdtfName;
    }) || null;
  }

  function scoreCellHtml(candidate) {
    if (!candidate) {
      return '<span class="badge tone-ondark">–</span>';
    }
    var score = candidate.score;
    var tone = score >= 0.9 ? "success" : score >= 0.3 ? "warning" : "danger";
    return '<span class="badge tone-' + tone + '">' + score.toFixed(2) + "</span>";
  }

  function gdtfCellHtml(type) {
    var assignment = type.assignment;
    if (assignment.removed) {
      return (
        '<div class="gdtf-cell-empty">' +
        '<span class="muted-text strike">wird entfernt</span>' +
        '<button type="button" class="btn btn-outline btn-sm btn-reassign" data-type-key="' +
        esc(type.key) + '">Doch zuordnen</button>' +
        "</div>"
      );
    }
    if (!type.candidates.length) {
      return (
        '<div class="gdtf-cell-empty">' +
        '<span class="muted-text">kein Treffer in der Bibliothek</span>' +
        '<button type="button" class="btn btn-outline btn-sm btn-share-search" data-type-key="' +
        esc(type.key) + '" data-type-name="' + esc(type.name) + '">Im Share suchen</button>' +
        "</div>"
      );
    }
    var options = ['<option value="">— kein Treffer —</option>'];
    type.candidates.forEach(function (c) {
      options.push(
        '<option value="' + esc(c.gdtf_name) + '"' +
        (c.gdtf_name === assignment.gdtf_name ? " selected" : "") +
        ">" + esc(c.gdtf_name) + "</option>"
      );
    });
    return (
      '<select class="sel-dark sel-gdtf" data-type-key="' + esc(type.key) + '">' +
      options.join("") + "</select>"
    );
  }

  function modeCellHtml(type, candidate) {
    var assignment = type.assignment;
    if (assignment.removed || !assignment.gdtf_name) {
      return '<span class="em-dash">—</span>';
    }
    var modes = candidate ? candidate.modes : assignment.mode_name ? [{ name: assignment.mode_name, channel_count: 0 }] : [];
    var options = modes
      .map(function (m) {
        return (
          '<option value="' + esc(m.name) + '"' +
          (m.name === assignment.mode_name ? " selected" : "") +
          ">" + esc(m.name) + " (" + m.channel_count + "ch)</option>"
        );
      })
      .join("");
    var selectHtml =
      '<select class="sel-dark sel-mode" data-type-key="' + esc(type.key) + '">' + options + "</select>";
    if (assignment.mode_is_fallback) {
      return (
        '<div class="modus-cell">' + selectHtml +
        '<span class="fallback-label" title="Fallback: erster Modus der GDTF">Fallback</span></div>'
      );
    }
    return selectHtml;
  }

  function sourceBadgeHtml(assignment) {
    if (assignment.removed) return '<span class="badge tone-ondark">entfernt</span>';
    if (!assignment.gdtf_name) return '<span class="badge tone-danger">offen</span>';
    if (assignment.source === "share") return '<span class="badge tone-brand">Share</span>';
    return '<span class="badge tone-ondark">Bibliothek</span>';
  }

  function renderMatchRow(type) {
    var assignment = type.assignment;
    var candidate = findCandidate(type, assignment.gdtf_name);
    var rowClass = isStylingProblem(assignment) ? "row-problem" : "";
    return (
      '<tr class="' + rowClass + '" data-type-key="' + esc(type.key) + '">' +
      "<td>" +
      '<div class="type-name">' + esc(type.name) + "</div>" +
      '<div class="type-meta">' + esc(type.meta_line) + "</div>" +
      "</td>" +
      "<td>" + gdtfCellHtml(type) + "</td>" +
      "<td>" + scoreCellHtml(assignment.removed ? null : candidate) + "</td>" +
      "<td>" + modeCellHtml(type, candidate) + "</td>" +
      "<td>" + sourceBadgeHtml(assignment) + "</td>" +
      "</tr>"
    );
  }

  function renderMatchTable(s) {
    var tbody = $("match-tbody");
    var rows = s.types
      .filter(function (type) {
        return !localState.nurProbleme || isFilterProblem(type.assignment);
      })
      .map(renderMatchRow);
    tbody.innerHTML = rows.join("");
  }

  // ──── Section 3 · Export ────

  function computeStatsFallback(s) {
    var total = s.stats ? s.stats.fixtures : 0;
    var matched = 0;
    var embeddedSet = {};
    s.types.forEach(function (t) {
      if (!t.assignment.removed && t.assignment.gdtf_name) {
        matched += t.count;
        embeddedSet[t.assignment.gdtf_name] = true;
      }
    });
    return {
      matched: matched,
      total: total,
      embedded: Object.keys(embeddedSet).length,
      meshes: s.stats ? s.stats.meshes : 0,
      positions: s.stats ? s.stats.positions : 0,
    };
  }

  function renderWarnStack(w) {
    var rows = [];
    w.fallbacks.forEach(function (fb) {
      rows.push(
        '<div class="warn-row amber">' + iconSpanHtml("triangle-alert", "ic-16 ic-amber") +
        "<span><b>" + fb.count + "× Modus-Fallback:</b> " + esc(fb.type_name) +
        " nutzt den ersten Modus der GDTF — bitte in Schritt 2 prüfen.</span></div>"
      );
    });
    w.collisions.forEach(function (col) {
      rows.push(
        '<div class="warn-row red">' + iconSpanHtml("zap", "ic-16 ic-red") +
        "<span><b>Adress-Kollision:</b> Universum " + col.universe + ", Kanal " + col.start +
        "–" + col.end + " doppelt belegt (" +
        col.fixture_names.map(esc).join(" / ") + ").</span></div>"
      );
    });
    if (w.cleanup_preview) {
      var cp = w.cleanup_preview;
      var parts = [cp.removed_fixture_count + " Fixtures entfernt"];
      if (cp.open_type_names.length) parts.push(cp.open_type_names.length + " offene Typen");
      parts.push(cp.orphan_gdtf_names.length + " verwaiste GDTFs verworfen");
      rows.push(
        '<div class="warn-row neutral">' + iconSpanHtml("list-checks", "ic-16 ic-blue300") +
        "<span>" + parts.join(" · ") + "</span></div>"
      );
    }
    $("warn-stack").innerHTML = rows.join("");
  }

  function renderSection3(s) {
    var warnCount = s.warnings.fallbacks.length + s.warnings.collisions.length;

    $("report-banner").classList.toggle("hidden", !s.export.done);
    if (s.export.done) {
      $("report-banner-sub").textContent =
        s.export.path + " · " + formatNumber(s.export.size_mb, 1) + " MB · " + s.export.time;
    }

    var stats;
    if (lastExportReport) {
      stats = {
        matched: lastExportReport.matched_fixtures,
        total: lastExportReport.total_fixtures,
        embedded: lastExportReport.embedded_gdtf_count,
        meshes: lastExportReport.mesh_count,
        positions: lastExportReport.position_group_count,
      };
    } else {
      stats = computeStatsFallback(s);
    }
    $("es-matched").textContent = stats.matched + "/" + stats.total;
    $("es-embedded").textContent = stats.embedded;
    $("es-meshes").textContent = stats.meshes;
    $("es-positions").textContent = stats.positions;

    renderWarnStack(s.warnings);

    $("export-panel-pre").classList.toggle("hidden", s.export.done);
    $("export-panel-post").classList.toggle("hidden", !s.export.done);

    $("export-target-path-pre").textContent = s.export.default_path || "(kein Zielpfad)";
    $("export-target-path-post").textContent = s.export.path || "";

    var btn = $("btn-export");
    btn.classList.remove("btn-primary", "btn-amber");
    if (exporting) {
      btn.classList.add("btn-primary");
      btn.textContent = "Exportiere…";
      btn.disabled = true;
    } else {
      btn.disabled = false;
      if (warnCount > 0) {
        btn.classList.add("btn-amber");
        btn.textContent = "Mit " + warnCount + " Warnungen exportieren";
      } else {
        btn.classList.add("btn-primary");
        btn.textContent = "Exportieren";
      }
    }
  }

  // ──── Event wiring (attached once; DOM containers persist across renders) ────

  function wireStaticListeners() {
    // Accordion header clicks — always allowed, delegated on document.
    document.addEventListener("click", function (e) {
      var head = e.target.closest(".sect-head");
      if (head && head.dataset.goto) {
        goToStep(Number(head.dataset.goto));
      }
    });

    // Section 1 — dropzone
    var dropzone = $("dropzone");
    dropzone.addEventListener("click", function () {
      callApi("choose_mvr");
    });
    dropzone.addEventListener("dragover", function (e) {
      e.preventDefault();
      dropzone.classList.add("drag-over");
    });
    dropzone.addEventListener("dragleave", function () {
      dropzone.classList.remove("drag-over");
    });
    dropzone.addEventListener("drop", function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag-over");
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      var path = file && file.pywebviewFullPath;
      if (path) {
        callApi("load_mvr", path);
      } else {
        pushToast("info", "Bitte über den Dialog wählen");
      }
    });

    $("btn-remove").addEventListener("click", function (e) {
      e.stopPropagation();
      cancelAutoAdvance();
      callApi("remove_mvr");
    });

    $("recent-list").addEventListener("click", function (e) {
      var row = e.target.closest(".recent-row");
      if (row && row.dataset.path) callApi("load_mvr", row.dataset.path);
    });

    // Section 2 — sources bar
    $("library-path").addEventListener("click", function () {
      callApi("choose_library_dir");
    });
    $("btn-share-login").addEventListener("click", function () {
      $("share-login-user").value = "";
      $("share-login-pass").value = "";
      hideLoginError();
      openModal("modal-share-login");
    });
    $("btn-share-logout").addEventListener("click", function (e) {
      e.preventDefault();
      callApi("share_logout");
    });
    $("chk-gruppieren").addEventListener("change", function (e) {
      callApi("set_grouping", e.target.checked);
    });
    $("filter-problems").addEventListener("change", function (e) {
      localState.nurProbleme = e.target.checked;
      render();
    });

    // Section 2 — match table (delegated: rows are re-created on every render)
    var tbody = $("match-tbody");
    tbody.addEventListener("change", function (e) {
      var key = e.target.dataset.typeKey;
      if (!key) return;
      if (e.target.classList.contains("sel-gdtf")) {
        callApi("set_gdtf", key, e.target.value);
      } else if (e.target.classList.contains("sel-mode")) {
        callApi("set_mode", key, e.target.value);
      }
    });
    tbody.addEventListener("click", function (e) {
      var searchBtn = e.target.closest(".btn-share-search");
      if (searchBtn) {
        openSearchModal(searchBtn.dataset.typeKey, searchBtn.dataset.typeName);
        return;
      }
      var reassignBtn = e.target.closest(".btn-reassign");
      if (reassignBtn) {
        callApi("set_removed", reassignBtn.dataset.typeKey, false);
      }
    });

    $("btn-continue").addEventListener("click", function () {
      callApi("prepare_export").then(function (result) {
        if (result.ok) {
          goToStep(3);
        }
      });
    });

    // Section 3 — export
    $("btn-export").addEventListener("click", function () {
      if (exporting) return;
      exporting = true;
      render();
      callApi("run_export", "").then(function (result) {
        if (!result.ok) {
          exporting = false;
          render();
        }
      });
    });
    $("btn-open-folder").addEventListener("click", function () {
      if (serverState && serverState.export.path) callApi("open_folder", serverState.export.path);
    });
    $("btn-new-export").addEventListener("click", function (e) {
      e.preventDefault();
      lastExportReport = null;
      callApi("reset_export");
    });

    // Modals — login
    $("btn-share-login-submit").addEventListener("click", function () {
      var user = $("share-login-user").value.trim();
      var pass = $("share-login-pass").value;
      var remember = $("share-login-remember").checked;
      if (!user || !pass) {
        showLoginError("Bitte Benutzername und Passwort eingeben.");
        return;
      }
      pendingLoginModal = true;
      hideLoginError();
      callApi("share_login", user, pass, remember);
    });

    // Modals — share search
    $("share-search-input").addEventListener("input", function (e) {
      clearTimeout(searchDebounceTimer);
      var value = e.target.value;
      searchDebounceTimer = setTimeout(function () {
        doSearch(value);
      }, 300);
    });
    $("share-results").addEventListener("click", function (e) {
      var btn = e.target.closest(".btn-share-download");
      if (!btn || btn.disabled) return;
      downloadShareResult(Number(btn.dataset.rid));
    });

    // Modals — generic close (X button, overlay click, ESC)
    document.querySelectorAll("[data-modal-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeModal(btn.dataset.modalClose);
      });
    });
    document.querySelectorAll(".modal-overlay").forEach(function (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) closeModal(overlay.id);
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        document.querySelectorAll(".modal-overlay:not(.hidden)").forEach(function (overlay) {
          closeModal(overlay.id);
        });
      }
    });
  }

  // ──── Bridge connection bootstrap ────

  var bridgeConnected = false;

  function connectBridge() {
    function tryConnect() {
      if (bridgeConnected) return;
      if (window.pywebview && window.pywebview.api) {
        bridgeConnected = true;
        callApi("get_state");
      }
    }
    window.addEventListener("pywebviewready", tryConnect, { once: true });
    tryConnect();
    var attempts = 0;
    var poll = setInterval(function () {
      if (bridgeConnected) {
        clearInterval(poll);
        return;
      }
      attempts += 1;
      tryConnect();
      if (bridgeConnected || attempts >= 40) {
        clearInterval(poll);
      }
    }, 100);
  }

  function boot() {
    render(); // paints the empty/unloaded state immediately, incl. in plain-browser mode
    wireStaticListeners();
    connectBridge();
  }

  // Exposed as early as possible: Python calls window.app.onEvent(...) from
  // a background thread and must find it defined regardless of timing.
  window.app = { onEvent: onEvent };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
