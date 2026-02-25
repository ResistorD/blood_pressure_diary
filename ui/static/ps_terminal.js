(() => {
  const body = document.body;
  if (!body) return;

  const state = {
    paused: body.dataset.paused === "1",
    pausedAt: "",
    lastUpdate: body.dataset.lastUpdate || "",
    staleLevel: "ok",
  };
  window.PS_TERMINAL_STATE = state;

  const titlebar = document.querySelector(".titlebar");
  const killWrap = document.querySelector(".kill-switch");
  const killBtn = document.querySelector("[data-kill-action]");
  const killLabel = document.querySelector("[data-kill-label]");
  const killStatus = document.querySelector("[data-kill-status]");
  const killTime = document.querySelector("[data-kill-time]");
  const latencyEl = document.querySelector("[data-metric='latency']");
  const execEl = document.querySelector("[data-metric='exec']");
  const freshEl = document.querySelector("[data-metric='freshness']");
  const exposureEl = document.querySelector("[data-exposure-summary]");
  const edgeReportEl = document.querySelector("[data-edge-report]");
  const edgeTradesPanel = document.getElementById("edge-trades-panel");
  const edgeTradesTitle = document.getElementById("edge-trades-title");
  const edgeTradesClose = document.getElementById("edge-trades-close");
  const edgeTradesTableWrap = document.getElementById("edge-trades-table-wrap");
  const bookPill = document.querySelector("#book-pill");
  const progressEl = document.querySelector(".kill-switch-progress");
  const agentCard = document.getElementById("agent-card");
  const agentPill = document.getElementById("agent-pill");
  const agentStatusPill = document.getElementById("agent-status-pill");
  const agentModePill = document.getElementById("agent-mode-pill");
  const agentCadencePill = document.getElementById("agent-cadence-pill");
  const agentGuardPill = document.getElementById("agent-guard-pill");
  const agentCurrentLine = document.getElementById("agent-current-line");
  const agentLastLine = document.getElementById("agent-last-line");
  const agentLog = document.getElementById("agent-log");
  const agentStartBtn = document.getElementById("agent-start-btn");
  const agentStopBtn = document.getElementById("agent-stop-btn");

  const HOLD_MS = 800;
  const REFRESH_MS = 5000;
  const PING_MS = 2000;
  const EXEC_MS = 5000;
  const BOOK_MS = 5000;
  const STALE_WARN_SEC = 20;
  const STALE_HARD_SEC = 60;
  const GUARD_SPREAD_MAX = 8;
  const GUARD_DEPTH_MIN_USD = 500;
  const GUARD_BOOK_AGE_MAX = 20;
  const GUARD_MAX_SLIP_BPS = 150;
  const GUARD_HOLD_MS = 800;
  const AGENT_POLL_MS = 5000;
  const MICRO_EDGE_TTL = 10000;
  const MICRO_EDGE_MAX = 4;
  const EXPLAIN_TTL = 15000;
  const EXPLAIN_MAX = 4;
  const EDGE_LABEL_SPREAD_TIGHT = 0.5;
  const EDGE_LABEL_SPREAD_WIDE = 2.0;
  const EDGE_LABEL_DEPTH_DEEP = 2000;
  const EDGE_LABEL_DEPTH_THIN = 300;
  const EDGE_LABEL_SAFE_ROOMY = 10;
  const EDGE_LABEL_SAFE_TINY = 1;
  const EDGE_LABEL_BOOK_STALE = 60;
  const EDGE_LABEL_FRESH_TICK = 10;

  let holdTimer = null;
  let holdRaf = null;
  let holdStart = 0;

  function parseTs(ts) {
    if (!ts) return null;
    if (typeof ts === "number") return ts;
    const s = String(ts).trim();
    if (!s) return null;
    if (/^\d+$/.test(s)) {
      const n = Number(s);
      return n > 1e12 ? n : n * 1000;
    }
    const parsed = Date.parse(s);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function formatDuration(sec) {
    if (sec == null) return "—";
    if (sec < 60) return `${Math.round(sec)}с`;
    if (sec < 3600) return `${Math.round(sec / 60)}м`;
    return `${Math.round(sec / 3600)}ч`;
  }

  function formatAgeCompact(sec) {
    if (sec == null) return "—";
    const s = Math.max(0, Number(sec));
    if (s < 60) return `${Math.round(s)}s`;
    return `${Math.round(s / 60)}m`;
  }

  function formatUsdCompact(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    const v = Number(value);
    const abs = Math.abs(v);
    if (abs >= 1_000_000) {
      const digits = abs >= 10_000_000 ? 0 : 1;
      return `$${(v / 1_000_000).toFixed(digits)}M`;
    }
    if (abs >= 1_000) {
      const digits = abs >= 10_000 ? 0 : 1;
      return `$${(v / 1_000).toFixed(digits)}k`;
    }
    return `$${Math.round(v)}`;
  }

  function formatSpreadPct(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    const v = Number(value);
    const digits = Math.abs(v) < 1 ? 2 : 1;
    return `${v.toFixed(digits)}%`;
  }

  function pickEdgeLabel(metrics) {
    const warnings = Array.isArray(metrics.warnings) ? metrics.warnings : [];
    if (warnings.includes("NO_ORDERBOOK")) return { code: "NO_BOOK", text: "No book" };
    if (warnings.includes("STALE_BOOK") || (metrics.book_age_s != null && metrics.book_age_s > EDGE_LABEL_BOOK_STALE)) {
      return { code: "STALE_BOOK", text: "Stale book" };
    }

    if (metrics.spread_pct != null && Number.isFinite(Number(metrics.spread_pct))) {
      const spread = Number(metrics.spread_pct);
      if (spread <= EDGE_LABEL_SPREAD_TIGHT) return { code: "TIGHT_SPREAD", text: "Tight spread" };
      if (spread >= EDGE_LABEL_SPREAD_WIDE) return { code: "WIDE_SPREAD", text: "Wide spread" };
    }

    if (metrics.depth_ask_1pct != null && metrics.depth_bid_1pct != null) {
      const minDepth = Math.min(Number(metrics.depth_ask_1pct), Number(metrics.depth_bid_1pct));
      if (Number.isFinite(minDepth)) {
        if (minDepth >= EDGE_LABEL_DEPTH_DEEP) return { code: "DEEP_BOOK", text: "Deep book" };
        if (minDepth <= EDGE_LABEL_DEPTH_THIN) return { code: "THIN_BOOK", text: "Thin book" };
      }
    }

    if (metrics.safe_buy != null && metrics.safe_sell != null) {
      const minSafe = Math.min(Number(metrics.safe_buy), Number(metrics.safe_sell));
      if (Number.isFinite(minSafe)) {
        if (minSafe >= EDGE_LABEL_SAFE_ROOMY) return { code: "ROOMY", text: "Roomy size" };
        if (minSafe <= EDGE_LABEL_SAFE_TINY) return { code: "TINY", text: "Tiny size" };
      }
    }

    if (metrics.age_s != null && Number.isFinite(Number(metrics.age_s)) && Number(metrics.age_s) <= EDGE_LABEL_FRESH_TICK) {
      return { code: "FRESH_TICK", text: "Fresh tick" };
    }

    return { code: "EDGE", text: "Edge" };
  }

  function buildEdgeLine({ age_s, spread_pct, liq_usd, depth_ask_1pct, depth_bid_1pct, book_age_s, safe_buy, safe_sell, warnings }) {
    const label = pickEdgeLabel({ age_s, spread_pct, liq_usd, depth_ask_1pct, depth_bid_1pct, book_age_s, safe_buy, safe_sell, warnings }).text;
    const parts = [
      `Edge: <span class="edge-label">${escapeHtml(label)}</span>`,
      `spr ${formatSpreadPct(spread_pct)}`,
      `liq ${formatUsdCompact(liq_usd)}`,
      `age ${formatAgeCompact(age_s)}`,
    ];
    if (book_age_s != null) {
      parts.push(`book ${formatAgeCompact(book_age_s)}`);
    }
    if (depth_ask_1pct != null || depth_bid_1pct != null) {
      const ask = formatUsdCompact(depth_ask_1pct);
      const bid = formatUsdCompact(depth_bid_1pct);
      parts.push(`depth A/B ${ask}/${bid}`);
    }
    if (safe_buy != null || safe_sell != null) {
      const buy = safe_buy != null ? Math.floor(Number(safe_buy)) : "—";
      const sell = safe_sell != null ? Math.floor(Number(safe_sell)) : "—";
      parts.push(`safe ${buy}/${sell}`);
    }
    if (Array.isArray(warnings)) {
      if (warnings.includes("NO_ORDERBOOK")) parts.push("NO_BOOK");
      if (warnings.includes("STALE_BOOK")) parts.push("STALE_BOOK");
    }
    return parts.join(" · ");
  }

  function formatEdgePct(value) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return `${Number(value).toFixed(1)}%`;
  }

  function buildWhyLine(explain) {
    if (!explain || !explain.type || explain.type === "NONE") return "Why: —";
    const pct = formatEdgePct(explain.edge_pct);
    if (explain.type === "MX") return `Why: MX gap ${pct}`;
    if (explain.type === "IMPL") return `Why: A>B ${pct}`;
    if (explain.type === "OVERROUND") return `Why: Overround ${pct}`;
    if (explain.type === "DIVERGENCE") return `Why: Divergence ${pct}`;
    return "Why: —";
  }

  function buildGuidedWhy(explain, micro) {
    if (!explain || !explain.type || explain.type === "NONE") return "Why: —";
    const pct = formatEdgePct(explain.edge_pct);
    const warnings = (micro && micro.warnings) ? micro.warnings : [];
    const suffix = warnings.includes("NO_ORDERBOOK") ? " · NO_BOOK" : warnings.includes("STALE_BOOK") ? " · STALE_BOOK" : "";
    if (explain.type === "MX") return `Why: MX gap ${pct}${suffix}`;
    if (explain.type === "IMPL") return `Why: A>B ${pct}${suffix}`;
    if (explain.type === "OVERROUND") return `Why: Overround ${pct}${suffix}`;
    if (explain.type === "DIVERGENCE") return `Why: Divergence ${pct}${suffix}`;
    return `Why: ${explain.type}${suffix}`;
  }

  function formatDepthPair(a, b) {
    if (a == null || b == null) return "—";
    return `${formatUsdCompact(a)}/${formatUsdCompact(b)}`;
  }

  function formatClock(sec) {
    if (sec == null) return "—";
    const s = Math.max(0, Math.round(sec));
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }

  function formatTs(ts) {
    if (!ts) return "—";
    const ms = parseTs(ts);
    if (!ms) return String(ts);
    const d = new Date(ms);
    return d.toISOString().replace("T", " ").replace("Z", "Z");
  }

  function setPaused(paused, pausedAt) {
    state.paused = !!paused;
    if (pausedAt) state.pausedAt = pausedAt;
    body.dataset.paused = state.paused ? "1" : "0";
    body.classList.toggle("is-paused", state.paused);
    if (titlebar) titlebar.classList.toggle("is-paused", state.paused);
    if (killWrap) killWrap.classList.toggle("is-paused", state.paused);
    if (killBtn) killBtn.classList.toggle("is-resume", state.paused);
    if (killLabel) killLabel.textContent = state.paused ? "ВОЗОБНОВИТЬ" : "⛔ ПАУЗА";
    if (killStatus) killStatus.textContent = "ПАУЗА";
    if (killTime) killTime.textContent = state.pausedAt ? `Пауза с ${formatTs(state.pausedAt)}` : "Пауза с —";
    syncTradeButtons();
  }

  function setLatency(ms) {
    if (!latencyEl) return;
    latencyEl.textContent = `API ${Math.round(ms)}мс`;
    latencyEl.classList.remove("ok", "warn", "bad", "blink");
    if (ms < 150) latencyEl.classList.add("ok");
    else if (ms < 500) latencyEl.classList.add("warn");
    else {
      latencyEl.classList.add("bad", "blink");
    }
  }

  function setExecHealth(p50, p95, errors) {
    if (!execEl) return;
    const p50v = p50 == null ? "—" : Math.round(p50);
    const p95v = p95 == null ? "—" : Math.round(p95);
    execEl.textContent = `ИСП ${p50v}/${p95v}мс`;
    execEl.classList.remove("ok", "warn", "bad", "blink");
    if ((errors || 0) >= 3 || (p95 != null && p95 > 1500)) {
      execEl.classList.add("bad");
    } else if (p95 != null && p95 >= 500) {
      execEl.classList.add("warn");
    } else {
      execEl.classList.add("ok");
    }
  }

  function setFreshness(lastUpdateTs) {
    if (lastUpdateTs) state.lastUpdate = lastUpdateTs;
    const lastMs = parseTs(state.lastUpdate);
    const now = Date.now();
    let freshnessSec = null;
    if (lastMs) freshnessSec = Math.max(0, (now - lastMs) / 1000);
    const label = freshnessSec == null ? "УСТАРЕЛО" : `Свежие ${formatDuration(freshnessSec)}`;
    if (freshEl) {
      if (freshnessSec == null || freshnessSec > STALE_HARD_SEC) {
        freshEl.innerHTML = `<span class="dot"></span> УСТАРЕЛО ${formatDuration(freshnessSec)} · Торговля отключена`;
      } else {
        freshEl.innerHTML = `<span class="dot"></span> ${label}`;
      }
      freshEl.classList.remove("ok", "warn", "bad");
      if (freshnessSec == null) {
        freshEl.classList.add("bad");
      } else if (freshnessSec <= STALE_WARN_SEC) {
        freshEl.classList.add("ok");
      } else if (freshnessSec <= STALE_HARD_SEC) {
        freshEl.classList.add("warn");
      } else {
        freshEl.classList.add("bad");
      }
    }

    body.classList.remove("is-stale", "is-stale-hard");
    state.staleLevel = "ok";
    if (freshnessSec == null) {
      body.classList.add("is-stale");
      state.staleLevel = "warn";
    } else if (freshnessSec > STALE_HARD_SEC) {
      body.classList.add("is-stale-hard");
      body.classList.add("is-stale");
      state.staleLevel = "hard";
    } else if (freshnessSec > STALE_WARN_SEC) {
      body.classList.add("is-stale");
      state.staleLevel = "warn";
    }
    syncTradeButtons();
  }

  function syncTradeButtons() {
    const disable = state.paused || state.staleLevel === "hard";
    const pausedReason = state.paused ? "Пауза" : null;
    const staleReason = state.staleLevel === "hard" ? "Данные устарели — торговля заблокирована" : null;

    function setReason(btn, reason, hardDisable) {
      if (!btn) return;
      if (reason) {
        btn.setAttribute("title", reason);
        btn.dataset.disabledReason = reason;
      } else {
        btn.removeAttribute("title");
        delete btn.dataset.disabledReason;
      }
      if (hardDisable) {
        btn.setAttribute("disabled", "disabled");
        btn.setAttribute("aria-disabled", "true");
      } else {
        btn.removeAttribute("disabled");
        btn.removeAttribute("aria-disabled");
      }
    }

    function applyReason(btn) {
      const row = btn.closest("tr");
      const rowStale = row && row.classList.contains("row-age-bad");
      const marketId = btn.getAttribute("data-case-id") || (row ? row.getAttribute("data-case-id") : "");
      const isTrade = btn.matches("[data-trade-button], [data-action='trade'], .trade-action, button[data-paper-action]");
      const isGuarded = btn.getAttribute("data-guarded") === "1";
      const sizeMissing = isTrade ? (getPaperSize(btn) == null) : false;

      let reason = null;
      let hardDisable = false;
      if (pausedReason) {
        reason = pausedReason;
        hardDisable = true;
      } else if (staleReason) {
        reason = staleReason;
        hardDisable = true;
      } else if (rowStale && isTrade) {
        reason = "Строка устарела";
        hardDisable = true;
      } else if (isGuarded && isTrade) {
        reason = btn.dataset.guardDetail || "Защита — удерживайте для обхода";
      } else if (!marketId) {
        reason = "Нет ID рынка";
      } else if (sizeMissing && isTrade) {
        reason = "Выберите размер (1/5/10)";
      }

      setReason(btn, reason, hardDisable);
      if (isGuarded && isTrade && !hardDisable) {
        btn.classList.add("is-guarded");
        btn.setAttribute("aria-disabled", "true");
      } else {
        btn.classList.remove("is-guarded");
      }
    }

    document.querySelectorAll("[data-trade-button], [data-action='trade'], .trade-action, button[data-paper-action]").forEach(applyReason);
    document.querySelectorAll("[data-preview-trigger], [data-micro-trigger]").forEach(applyReason);
  }

  function ensurePausedBanner() {
    const main = document.querySelector(".main");
    if (!main) return;
    if (main.querySelector(".paused-banner")) return;
    const banner = document.createElement("div");
    banner.className = "paused-banner";
    banner.textContent = "⛔ ПАУЗА — исполнение заблокировано";
    main.prepend(banner);
  }

  function showToast(text, kind) {
    const toast = document.createElement("div");
    toast.className = `terminal-toast${kind ? " " + kind : ""}`;
    toast.textContent = text;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 300);
    }, 1600);
  }

  window.PS_TERMINAL_TOAST = showToast;

  function flashCell(el) {
    if (!el) return;
    el.classList.remove("tick-flash");
    void el.offsetWidth;
    el.classList.add("tick-flash");
  }

  function setButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) btn.classList.add("paper-action-loading");
    else btn.classList.remove("paper-action-loading");
  }

  function ensureGuardBadge(btn) {
    if (!btn) return null;
    const action = btn.getAttribute("data-paper-action") || "buy";
    const wrap = btn.parentElement || btn.closest(".btn-group") || btn.closest("td");
    if (!wrap) return null;
    let badge = wrap.querySelector(`[data-guard-badge='${action}']`);
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "guard-badge";
      badge.setAttribute("data-guard-badge", action);
      btn.insertAdjacentElement("afterend", badge);
    }
    return badge;
  }

  function setGuardState(btn, reason) {
    if (!btn) return;
    const badge = ensureGuardBadge(btn);
    if (!reason) {
      btn.removeAttribute("data-guarded");
      btn.removeAttribute("aria-disabled");
      delete btn.dataset.guardDetail;
      if (badge) {
        badge.textContent = "";
        badge.style.display = "none";
      }
      return;
    }
    btn.setAttribute("data-guarded", "1");
    btn.setAttribute("aria-disabled", "true");
    if (badge) {
      badge.textContent = reason;
      badge.style.display = "inline-flex";
    }
  }

  function getSpreadPctFromRow(row) {
    if (!row) return null;
    const ds = row.dataset.spreadPct;
    if (ds) {
      const v = Number(ds);
      return Number.isFinite(v) ? v : null;
    }
    const el = row.querySelector("[data-case-spread]");
    if (!el) return null;
    const txt = (el.textContent || "").replace("%", "").trim();
    const v = Number(txt);
    return Number.isFinite(v) ? v : null;
  }

  function getPreviewWarnings(marketId, action) {
    const key = `${marketId}:${action}`;
    const cached = previewCache.get(key);
    if (!cached || !cached.data) return [];
    return cached.data.warnings || [];
  }

  function evaluateGuard(row, micro) {
    const spreadPct = getSpreadPctFromRow(row);
    const bookAge = micro ? micro.book_age_s : null;
    return { spreadPct, bookAge };
  }

  function getPreviewData(marketId, action) {
    const key = `${marketId}:${action}`;
    const cached = previewCache.get(key);
    if (!cached || !cached.data) return null;
    return cached.data;
  }

  function buildDecisionExplain(row, action, micro, preview) {
    const lines = [];
    const spreadPct = getSpreadPctFromRow(row);
    if (spreadPct == null) {
      lines.push({ ok: true, text: "Спред —" });
    } else if (spreadPct <= GUARD_SPREAD_MAX) {
      lines.push({ ok: true, text: `Спред в норме (${spreadPct.toFixed(2)}%)` });
    } else {
      lines.push({ ok: false, text: `Широкий спред (${spreadPct.toFixed(2)}% > ${GUARD_SPREAD_MAX}%)` });
    }

    const depthVal = action === "close" ? (micro ? micro.depth_bid_1pct_usd : null) : (micro ? micro.depth_ask_1pct_usd : null);
    if (depthVal == null) {
      lines.push({ ok: true, text: "Глубина —" });
    } else if (Number(depthVal) >= GUARD_DEPTH_MIN_USD) {
      lines.push({ ok: true, text: `Глубина в норме ($${Number(depthVal).toFixed(0)})` });
    } else {
      lines.push({ ok: false, text: `Слабая глубина ($${Number(depthVal).toFixed(0)} < ${GUARD_DEPTH_MIN_USD}$)` });
    }

    const bookAge = micro ? micro.book_age_s : null;
    if (bookAge == null) {
      lines.push({ ok: true, text: "Возраст книги —" });
    } else if (Number(bookAge) <= GUARD_BOOK_AGE_MAX) {
      lines.push({ ok: true, text: `Книга свежая (${Math.round(bookAge)}с)` });
    } else {
      lines.push({ ok: false, text: `Книга устарела (${Math.round(bookAge)}с > ${GUARD_BOOK_AGE_MAX}с)` });
    }

    if (preview && preview.slip_bps != null) {
      const slip = Number(preview.slip_bps);
      if (Number.isFinite(slip) && Math.abs(slip) <= GUARD_MAX_SLIP_BPS) {
        lines.push({ ok: true, text: `Импакт в норме (${Math.round(slip)}бпс)` });
      } else if (Number.isFinite(slip)) {
        lines.push({ ok: false, text: `Высокий импакт (${Math.round(slip)}бпс)` });
      } else {
        lines.push({ ok: true, text: "Импакт —" });
      }
    } else {
      lines.push({ ok: true, text: "Импакт не рассчитан" });
    }

    if (preview) {
      const safe = action === "close" ? preview.safe_max_size_sell : preview.safe_max_size_buy;
      if (safe != null) {
        if (Number(safe) <= 0) {
          lines.push({ ok: false, text: `Нет безопасного размера при пороге ${GUARD_MAX_SLIP_BPS} бпс` });
        } else {
          lines.push({ ok: true, text: `Макс. безопасный размер: ${Math.floor(Number(safe))}` });
        }
      }
    }

    const hasFail = lines.some((l) => l.ok === false);
    lines.push({ ok: !hasFail, text: hasFail ? "Защита (можно обойти удержанием)" : "Торговля разрешена", summary: true });
    return lines;
  }

  function getPaperSize(btn) {
    if (!btn) return null;
    const direct = btn.getAttribute("data-paper-size");
    if (direct) {
      const v = Number(direct);
      return Number.isFinite(v) ? v : null;
    }
    const wrap = btn.closest(".paper-cell") || btn.closest("td") || btn.closest("tr");
    if (wrap) {
      const sizeBox = wrap.querySelector("[data-paper-size]");
      if (sizeBox && sizeBox.getAttribute("data-paper-size")) {
        const v = Number(sizeBox.getAttribute("data-paper-size"));
        return Number.isFinite(v) ? v : null;
      }
      const input = wrap.querySelector("[data-paper-size-input]");
      if (input && input.value) {
        const v = Number(input.value);
        return Number.isFinite(v) ? v : null;
      }
    }
    return null;
  }

  function updateSafeSizeDisplay(row, safeBuy, safeSell) {
    if (!row) return;
    const wrap = row.querySelector("[data-safe-size]");
    if (!wrap) return;
    const buyEl = wrap.querySelector("[data-safe-buy]");
    const sellEl = wrap.querySelector("[data-safe-sell]");
    if (buyEl) buyEl.textContent = safeBuy != null ? String(Math.floor(Number(safeBuy))) : "—";
    if (sellEl) sellEl.textContent = safeSell != null ? String(Math.floor(Number(safeSell))) : "—";
  }

  function applySafeSizeFromPreview(row, preview) {
    if (!row || !preview) return;
    if (preview.safe_max_size_buy == null && preview.safe_max_size_sell == null) return;
    updateSafeSizeDisplay(row, preview.safe_max_size_buy, preview.safe_max_size_sell);
  }

  function applySafeSizeFromMicro(row, micro, preferPreview = false) {
    if (!row || !micro) return;
    if (preferPreview) return;
    if (micro.safe_max_size_buy == null && micro.safe_max_size_sell == null) return;
    updateSafeSizeDisplay(row, micro.safe_max_size_buy, micro.safe_max_size_sell);
  }

  function updateNavBadges(updated) {
    if (!updated) return;
    Object.entries(updated).forEach(([name, val]) => {
      const el = document.querySelector(`[data-nav-count='${name}']`);
      if (!el) return;
      el.textContent = String(val);
      flashCell(el);
    });
  }

  function applyPaperResponse(data, caseId) {
    const row = document.querySelector(`tr[data-case-id='${caseId}']`);
    if (!row) return;
    const mapStatus = (status) => {
      if (!status) return "—";
      if (status === "OPEN") return "ОТКРЫТО";
      if (status === "CLOSED") return "ЗАКРЫТО";
      if (status === "NONE") return "—";
      return status;
    };
    const statusEl = row.querySelector("[data-paper-status]");
    if (statusEl && data.new_status) {
      statusEl.textContent = mapStatus(data.new_status);
      statusEl.classList.remove("badge-green", "badge-blue", "badge-gray", "badge-red", "badge-yellow");
      statusEl.classList.add("badge");
      if (data.new_status === "OPEN") statusEl.classList.add("badge-green");
      else if (data.new_status === "CLOSED") statusEl.classList.add("badge-gray");
      else statusEl.classList.add("badge-yellow");
      flashCell(statusEl);
    }
    if (data.new_status) {
      const cell = row.querySelector(".paper-cell");
      if (cell) cell.setAttribute("data-paper-state", data.new_status);
    }
    const posStatus = row.querySelector("[data-position-status]");
    if (posStatus && data.new_status) {
      posStatus.textContent = mapStatus(data.new_status);
      flashCell(posStatus);
    }
  }

  async function paperActionRequest(caseId, action, btn) {
    if (window.PS_TERMINAL_STATE && (window.PS_TERMINAL_STATE.paused || window.PS_TERMINAL_STATE.staleLevel === "hard")) {
      showToast(window.PS_TERMINAL_STATE.paused ? "⛔ Исполнение на паузе" : "⚠ Данные устарели — торговля заблокирована", "warn");
      return;
    }
    const row = document.querySelector(`tr[data-case-id='${caseId}']`);
    if (row && row.classList.contains("row-age-bad")) {
      showToast("Строка устарела", "warn");
      return;
    }
    if (!caseId || !action) return;
    if (btn && btn.getAttribute("data-guarded") === "1" && btn.getAttribute("data-guard-override") !== "1") {
      showToast("Активна защита — удерживайте для обхода", "warn");
      return;
    }
    if (row) {
      row.classList.add("paper-pending");
      row.dataset.pending = "1";
    }
    setButtonLoading(btn, true);
    try {
      const size = getPaperSize(btn);
      const resp = await fetch("/paper/action", {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        credentials: "same-origin",
        body: JSON.stringify({ case_id: caseId, action, size, mode: "paper" }),
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok) {
        if (resp.status === 423) showToast("⛔ Исполнение на паузе", "paused");
        else if (resp.status === 409) showToast("⚠ Данные устарели — торговля заблокирована", "warn");
        else showToast("Ошибка исполнения", "warn");
        return;
      }
      if (data && data.ok) {
        applyPaperResponse(data, caseId);
        if (data.updated_badges) updateNavBadges(data.updated_badges);
        showToast(action === "buy" ? "✅ Пейпер‑покупка" : "✅ Пейпер‑закрытие", "resumed");
      } else {
        const err = (data && data.error) ? String(data.error) : "BLOCKED";
        showToast(err, "warn");
      }
    } catch (e) {
      showToast("Ошибка сети", "warn");
    } finally {
      if (row) {
        row.classList.remove("paper-pending");
        delete row.dataset.pending;
      }
      setButtonLoading(btn, false);
    }
  }

  function handlePaperClick(e) {
    const btn = e.target.closest("button[data-paper-action][data-case-id]");
    if (!btn) return;
    e.preventDefault();
    const caseId = btn.getAttribute("data-case-id");
    const action = btn.getAttribute("data-paper-action");
    paperActionRequest(caseId, action, btn);
  }

  window.PS_PAPER_ACTION = paperActionRequest;

  let inflightState = false;
  let inflightPing = false;
  let inflightHealth = false;
  let inflightExposure = false;
  let inflightEdgeReport = false;
  let inflightExec = false;
  let inflightBook = false;
  let inflightAgent = false;
  let pingErrors = 0;
  let stateErrors = 0;
  let healthErrors = 0;
  let exposureErrors = 0;
  let edgeReportErrors = 0;
  let execErrors = 0;
  let bookErrors = 0;
  let agentErrors = 0;
  let pollingStarted = false;
  const forceRefreshBtn = document.getElementById("force-refresh-btn");

  let lastAgentState = null;
  let lastAgentEvents = [];
  let lastEdgeReportTs = 0;
  let lastEdgeReportData = null;
  const edgeTradesCache = new Map();
  const edgeTradesInflight = new Set();

  async function fetchState() {
    if (inflightState) return;
    inflightState = true;
    try {
      const resp = await fetch("/control/state", { headers: { "Accept": "application/json" } });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && typeof data === "object") {
        if (typeof data.paused === "boolean") {
          setPaused(data.paused, data.paused_at || data.pausedAt || "");
        }
      }
      stateErrors = 0;
    } catch (e) {
      stateErrors += 1;
    } finally {
      inflightState = false;
    }
  }

  async function fetchPing() {
    if (inflightPing) return;
    inflightPing = true;
    const start = performance.now();
    try {
      const resp = await fetch("/health/ping", { cache: "no-store" });
      const latency = performance.now() - start;
      setLatency(latency);
      if (!resp.ok) {
        pingErrors += 1;
        return;
      }
      pingErrors = 0;
    } catch (e) {
      setLatency(999);
      pingErrors += 1;
    } finally {
      inflightPing = false;
    }
  }

  async function fetchHealth() {
    if (inflightHealth) return;
    inflightHealth = true;
    try {
      const resp = await fetch("/health/state", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && typeof data === "object") {
        setFreshness(data.last_snapshot_ts || data.last_ingest_ts || data.last_data_ts || "");
      }
      healthErrors = 0;
    } catch (e) {
      healthErrors += 1;
    } finally {
      inflightHealth = false;
    }
  }

  async function fetchExposure() {
    if (inflightExposure) return;
    inflightExposure = true;
    try {
      const resp = await fetch("/risk/summary", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data || typeof data !== "object") return;
      const usedPct = Number(data.used_pct || 0);
      const gross = Number(data.gross_usd || 0);
      const net = Number(data.net_usd || 0);
      const budget = Number(data.budget_usd || 0);
      if (exposureEl) {
        exposureEl.textContent = `ЭКСПО ${Math.round(usedPct)}% | Нетто ${net.toFixed(0)} | Брутто ${gross.toFixed(0)}`;
        exposureEl.classList.remove("warn", "bad");
        if (usedPct >= 95) exposureEl.classList.add("bad");
        else if (usedPct >= 80) exposureEl.classList.add("warn");
      }

      document.querySelectorAll("[data-exposure-used]").forEach((el) => {
        el.textContent = `${usedPct.toFixed(1)}%`;
      });
      document.querySelectorAll("[data-exposure-net]").forEach((el) => {
        el.textContent = net.toFixed(2);
      });
      document.querySelectorAll("[data-exposure-gross]").forEach((el) => {
        el.textContent = gross.toFixed(2);
      });
      document.querySelectorAll("[data-exposure-budget]").forEach((el) => {
        el.textContent = budget.toFixed(2);
      });
      const asOf = data.as_of || data.asOf || "";
      document.querySelectorAll("[data-exposure-asof]").forEach((el) => {
        el.textContent = asOf ? formatTs(asOf) : "—";
      });
      document.querySelectorAll("[data-exposure-badge]").forEach((el) => {
        el.classList.remove("badge", "warn", "bad");
        if (usedPct >= 95) {
          el.textContent = "ЛИМИТ РИСКА";
          el.classList.add("badge", "bad");
        } else if (usedPct >= 80) {
          el.textContent = "ПОЧТИ ЛИМИТ";
          el.classList.add("badge", "warn");
        } else {
          el.textContent = "ОК";
        }
      });
      const list = document.querySelector("[data-exposure-groups]");
      if (list) {
        list.innerHTML = "";
        (data.by_group || []).slice(0, 3).forEach((g) => {
          const row = document.createElement("div");
          row.className = "risk-group-row";
          row.textContent = `${g.group || "—"} · ${Number(g.gross || 0).toFixed(0)} (${Number(g.used_pct || 0).toFixed(0)}%)`;
          list.appendChild(row);
        });
      }
      exposureErrors = 0;
    } catch (e) {
      exposureErrors += 1;
    } finally {
      inflightExposure = false;
    }
  }

  function formatHoldShort(sec) {
    if (sec == null || !Number.isFinite(Number(sec))) return "—";
    const s = Math.max(0, Math.round(Number(sec)));
    if (s < 60) return `${s}s`;
    if (s < 3600) {
      const m = Math.floor(s / 60);
      const ss = String(s % 60).padStart(2, "0");
      return `${m}m${ss}s`;
    }
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h${String(m).padStart(2, "0")}m`;
  }

  function formatPct(value, digits = 2) {
    if (value == null || !Number.isFinite(Number(value))) return "—";
    return `${Number(value).toFixed(digits)}%`;
  }

  function renderEdgePnlReport(data) {
    if (!edgeReportEl) return;
    const rows = (data && data.rows) ? data.rows : [];
    if (!rows.length) {
      edgeReportEl.textContent = "Нет данных";
      return;
    }
    const head = `
      <tr>
        <th>TYPE</th>
        <th class="tr">N</th>
        <th class="tr">Win%</th>
        <th class="tr">Avg PnL</th>
        <th class="tr">Best</th>
        <th class="tr">Worst</th>
        <th class="tr">Hold</th>
        <th class="tr">Avg Edge</th>
      </tr>
    `;
    const body = rows.map((r) => {
      const pnl = Number(r.avg_pnl_pct || 0);
      const pnlCls = pnl > 0 ? "pnl-pos" : pnl < 0 ? "pnl-neg" : "pnl-flat";
      const typ = String(r.explain_type || "NONE");
      return `
        <tr>
          <td><button type="button" class="linklike mono" data-edge-type="${escapeHtml(typ)}">${escapeHtml(typ)}</button></td>
          <td class="tr mono">${Number(r.n || 0)}</td>
          <td class="tr mono">${formatPct(Number(r.winrate || 0) * 100, 0)}</td>
          <td class="tr mono"><span class="${pnlCls}">${formatPct(r.avg_pnl_pct, 2)}</span></td>
          <td class="tr mono">${formatPct(r.avg_best_pct, 2)}</td>
          <td class="tr mono">${formatPct(r.avg_worst_pct, 2)}</td>
          <td class="tr mono">${formatHoldShort(r.avg_hold_sec)}</td>
          <td class="tr mono">${formatPct(r.avg_edge_pct, 2)}</td>
        </tr>
      `;
    }).join("");
    edgeReportEl.innerHTML = `
      <div class="table-wrap">
        <table class="data-table edge-report-table">
          <thead>${head}</thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    `;
  }

  function renderEdgeTradesPanel(type, data, err = false) {
    if (!edgeTradesPanel || !edgeTradesTableWrap || !edgeTradesTitle) return;
    edgeTradesPanel.classList.remove("hidden");
    edgeTradesTitle.textContent = `${type} — last 7d`;
    if (err) {
      edgeTradesTableWrap.textContent = "Failed to load trades";
      return;
    }
    const rows = (data && data.rows) ? data.rows : [];
    if (!rows.length) {
      edgeTradesTableWrap.textContent = "Нет данных";
      return;
    }
    const head = `
      <tr>
        <th>Time</th>
        <th>Case</th>
        <th>Side</th>
        <th class="tr">Hold</th>
        <th class="tr">PnL</th>
        <th class="tr">Best</th>
        <th class="tr">Worst</th>
        <th class="tr">Edge</th>
      </tr>
    `;
    const body = rows.map((r) => {
      const pnl = Number(r.pnl_pct || 0);
      const pnlCls = pnl > 0 ? "pnl-pos" : pnl < 0 ? "pnl-neg" : "pnl-flat";
      const caseId = String(r.case_id || r.market_id || "");
      const closedTs = r.closed_ts != null ? new Date(Number(r.closed_ts) * 1000).toISOString().replace("T", " ").slice(0, 19) : "—";
      return `
        <tr>
          <td class="mono">${escapeHtml(closedTs)}</td>
          <td class="mono">${caseId ? `<a href="/cases/${encodeURIComponent(caseId)}">${escapeHtml(caseId)}</a>` : "—"}</td>
          <td class="mono">${escapeHtml(String(r.side || "—"))}</td>
          <td class="tr mono">${formatHoldShort(r.hold_sec)}</td>
          <td class="tr mono"><span class="${pnlCls}">${formatPct(r.pnl_pct, 2)}</span></td>
          <td class="tr mono">${formatPct(r.best_pct, 2)}</td>
          <td class="tr mono">${formatPct(r.worst_pct, 2)}</td>
          <td class="tr mono">${formatPct(r.edge_pct, 2)}</td>
        </tr>
      `;
    }).join("");
    edgeTradesTableWrap.innerHTML = `
      <div class="table-wrap">
        <table class="data-table edge-trades-table">
          <thead>${head}</thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    `;
  }

  async function fetchEdgeTrades(type, days = 7, limit = 20) {
    if (!edgeTradesTableWrap || !type) return;
    const key = `${type}:${days}:${limit}`;
    const cached = edgeTradesCache.get(key);
    const now = Date.now();
    if (cached && (now - cached.ts) < 30000) {
      renderEdgeTradesPanel(type, cached.data);
      return;
    }
    if (edgeTradesInflight.has(key)) return;
    edgeTradesInflight.add(key);
    edgeTradesTableWrap.textContent = "Loading…";
    renderEdgeTradesPanel(type, { rows: [] });
    try {
      const resp = await fetch(`/reports/edge_trades?days=${days}&type=${encodeURIComponent(type)}&limit=${limit}`, { cache: "no-store" });
      if (!resp.ok) {
        renderEdgeTradesPanel(type, null, true);
        return;
      }
      const data = await resp.json();
      edgeTradesCache.set(key, { ts: Date.now(), data });
      renderEdgeTradesPanel(type, data);
    } catch (e) {
      renderEdgeTradesPanel(type, null, true);
    } finally {
      edgeTradesInflight.delete(key);
    }
  }

  async function fetchEdgePnlReport() {
    if (!edgeReportEl || inflightEdgeReport) return;
    const now = Date.now();
    if (lastEdgeReportData && (now - lastEdgeReportTs) < 30000) {
      renderEdgePnlReport(lastEdgeReportData);
      return;
    }
    inflightEdgeReport = true;
    try {
      const resp = await fetch("/reports/edge_pnl?days=7", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      lastEdgeReportTs = Date.now();
      lastEdgeReportData = data;
      renderEdgePnlReport(data);
      edgeReportErrors = 0;
    } catch (e) {
      edgeReportErrors += 1;
    } finally {
      inflightEdgeReport = false;
    }
  }

  async function fetchExecHealth() {
    if (inflightExec) return;
    inflightExec = true;
    try {
      const resp = await fetch("/health/exec", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && typeof data === "object") {
        setExecHealth(data.exec_rtt_ms_p50, data.exec_rtt_ms_p95, data.errors_1m || 0);
      }
      execErrors = 0;
    } catch (e) {
      execErrors += 1;
    } finally {
      inflightExec = false;
    }
  }

  async function fetchBookHealth() {
    if (inflightBook) return;
    inflightBook = true;
    try {
      const resp = await fetch("/health/orderbook", { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!bookPill) return;
      const lastMap = data.last_book_ts || {};
      let maxTs = null;
      Object.values(lastMap).forEach((v) => {
        const ms = parseTs(v);
        if (!ms) return;
        if (!maxTs || ms > maxTs) maxTs = ms;
      });
      const ageSec = maxTs ? Math.max(0, (Date.now() - maxTs) / 1000) : null;
      const errors = Number(data.errors_1m || 0);
      const snaps = Number(data.snapshots_per_min || 0);
      const text = ageSec == null ? "КНИГА —" : `КНИГА ${Math.round(ageSec)}с`;
      bookPill.textContent = text;
      bookPill.classList.remove("pill-ok", "pill-warn", "pill-bad", "pill-muted");
      if (ageSec == null) {
        bookPill.classList.add("pill-muted");
      } else if (ageSec <= 10 && errors === 0) {
        bookPill.classList.add("pill-ok");
      } else if ((ageSec > 30) || snaps === 0) {
        bookPill.classList.add("pill-bad");
      } else {
        bookPill.classList.add("pill-warn");
      }
      bookErrors = 0;
    } catch (e) {
      bookErrors += 1;
    } finally {
      inflightBook = false;
    }
  }

  async function fetchAgent() {
    if ((!agentCard && !agentPill) || inflightAgent) return;
    inflightAgent = true;
    try {
      let stateData = null;
      let eventsData = null;
      if (agentCard) {
        const [stateResp, eventsResp] = await Promise.all([
          fetch("/agent/state", { cache: "no-store", headers: { "Accept": "application/json" } }),
          fetch("/agent/events?limit=10", { cache: "no-store", headers: { "Accept": "application/json" } }),
        ]);
        if (!stateResp.ok || !eventsResp.ok) {
          agentErrors += 1;
          return;
        }
        stateData = await stateResp.json();
        eventsData = await eventsResp.json();
      } else {
        const stateResp = await fetch("/agent/state", { cache: "no-store", headers: { "Accept": "application/json" } });
        if (!stateResp.ok) {
          agentErrors += 1;
          return;
        }
        stateData = await stateResp.json();
      }
      lastAgentState = stateData && stateData.state ? stateData.state : null;
      lastAgentEvents = (eventsData && eventsData.events) ? eventsData.events : [];
      renderAgentPanel(lastAgentState, lastAgentEvents);
      renderAgentPill(lastAgentState);
      agentErrors = 0;
    } catch (e) {
      agentErrors += 1;
    } finally {
      inflightAgent = false;
    }
  }

  function renderAgentPill(stateData) {
    if (!agentPill) return;
    const st = stateData || {};
    const enabled = !!st.enabled;
    const cadence = st.cadence_sec ? `${st.cadence_sec}s` : "—";
    const openCount = st.current ? 1 : 0;
    const maxPos = st.max_positions != null ? st.max_positions : "—";
    agentPill.textContent = `AGENT ${enabled ? "ON" : "OFF"} · ${cadence} · ${openCount}/${maxPos}`;
    agentPill.classList.remove("pill-ok", "pill-muted", "pill-warn");
    agentPill.classList.add(enabled ? "pill-ok" : "pill-muted");
  }

  function renderAgentPanel(stateData, events) {
    if (!agentCard) return;
    const st = stateData || {};
    const enabled = !!st.enabled;
    if (agentStatusPill) {
      agentStatusPill.textContent = enabled ? "● ON" : "● OFF";
      agentStatusPill.classList.remove("pill-ok", "pill-muted", "pill-warn");
      agentStatusPill.classList.add(enabled ? "pill-ok" : "pill-muted");
    }
    if (agentModePill) agentModePill.textContent = st.mode ? String(st.mode) : "paper";
    if (agentCadencePill) agentCadencePill.textContent = st.cadence_sec ? `каждые ${st.cadence_sec}s` : "—";

    if (agentGuardPill) {
      const flags = [];
      if (body.classList.contains("is-paused")) flags.push("PAUSED");
      if (body.classList.contains("is-stale-hard")) flags.push("STALE");
      if (flags.length) {
        agentGuardPill.style.display = "inline-flex";
        agentGuardPill.textContent = flags.join(" ");
      } else {
        agentGuardPill.style.display = "none";
      }
    }

    if (agentCurrentLine) {
      agentCurrentLine.textContent = "—";
      agentCurrentLine.innerHTML = "";
      if (st.current) {
        const cur = st.current;
        const caseId = cur.case_id || cur.market_id || "";
        const side = cur.side || "YES";
        const rem = cur.size != null ? Number(cur.size).toFixed(0) : "—";
        const total = cur.size_total != null ? Number(cur.size_total).toFixed(0) : rem;
        const openedMs = parseTs(cur.opened_ts);
        const ageSec = openedMs ? (Date.now() - openedMs) / 1000 : null;
        const line = document.createElement("span");
        if (caseId) {
          const link = document.createElement("a");
          link.href = `/cases/${caseId}`;
          link.textContent = `case ${caseId}`;
          link.className = "agent-link";
          line.appendChild(link);
        } else {
          line.textContent = "case —";
        }
        line.appendChild(document.createTextNode(` · ${side} · rem ${rem}/${total} · age ${formatClock(ageSec)}`));
        agentCurrentLine.appendChild(line);

        const pnlLine = renderPnlLine(cur);
        if (pnlLine) {
          agentCurrentLine.appendChild(pnlLine);
        }
      } else {
        agentCurrentLine.textContent = "—";
      }
    }

    const latest = (events || [])[0] || null;
    if (agentLastLine) {
      agentLastLine.innerHTML = latest ? formatAgentEventLine(latest, true) : "—";
    }

    if (agentLog) {
      agentLog.innerHTML = "";
      (events || []).slice(0, 5).forEach((ev) => {
        const row = document.createElement("div");
        row.className = "agent-log-line";
        const badge = document.createElement("span");
        const type = String(ev.type || "").toUpperCase();
        badge.className = `agent-evt agent-evt-${type}`;
        badge.textContent = type || "—";
        const marker = document.createElement("span");
        marker.className = `agent-evt-marker agent-evt-${type}`;
        marker.textContent = eventMarker(type);
        const text = document.createElement("span");
        text.className = "agent-log-text";
        text.innerHTML = formatAgentEventLine(ev, false);
        row.appendChild(marker);
        row.appendChild(badge);
        row.appendChild(text);
        agentLog.appendChild(row);
      });
      if (!events || events.length === 0) {
        const empty = document.createElement("div");
        empty.className = "agent-log-empty";
        empty.textContent = "Нет событий";
        agentLog.appendChild(empty);
      }
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderAgentReason(reasonCode, type) {
    if (!reasonCode) return "";
    const extraClass = type === "ERROR" ? " agent-reason-error" : type === "SKIP" ? " agent-reason-skip" : "";
    return `<span class="agent-reason${extraClass}">${escapeHtml(reasonCode)}</span>`;
  }

  function formatPnlSpan(value) {
    if (value == null || !Number.isFinite(Number(value))) return `<span class="pnl-flat">—</span>`;
    const v = Number(value);
    const sign = v > 0 ? "+" : v < 0 ? "" : "";
    const cls = v > 0 ? "pnl-pos" : v < 0 ? "pnl-neg" : "pnl-flat";
    return `<span class="${cls}">${sign}${v.toFixed(2)}%</span>`;
  }

  function renderPnlLine(cur) {
    const pnl = cur.pnl_pct;
    const best = cur.best_runup_pct;
    const worst = cur.worst_drawdown_pct;
    if (pnl == null && best == null && worst == null) return null;
    const wrap = document.createElement("span");
    wrap.className = "agent-pnl-line";
    wrap.innerHTML = `PnL: ${formatPnlSpan(pnl)} · best ${formatPnlSpan(best)} · worst ${formatPnlSpan(worst)}`;
    return wrap;
  }

  function formatAgentEventLine(ev, compact) {
    const type = String(ev.type || "");
    const detail = ev.detail || {};
    const ts = ev.ts ? formatTs(ev.ts) : "";
    const prefix = compact ? type : `${ts} ${type}`.trim();
    const reasonCode = getAgentReason(detail);
    const ctx = formatAgentContext(type, detail, reasonCode);
    const prefixHtml = escapeHtml(prefix);
    const ctxHtml = ctx ? ` (${escapeHtml(ctx)})` : "";

    if (type === "CLOSE_CHUNK") {
      const qty = detail.qty != null ? `qty=${detail.qty}` : "";
      const rem = detail.remaining != null ? `rem=${detail.remaining}` : "";
      const mode = detail.mode ? `(${detail.mode})` : "";
      return `${prefixHtml} ${escapeHtml(qty)} ${escapeHtml(rem)} ${escapeHtml(mode)}`.trim();
    }
    if (type === "CLOSE_DONE") {
      if (detail.realized_pnl_pct != null || detail.best_runup_pct != null || detail.worst_drawdown_pct != null) {
        const pnl = formatPnlSpan(detail.realized_pnl_pct);
        const best = formatPnlSpan(detail.best_runup_pct);
        const worst = formatPnlSpan(detail.worst_drawdown_pct);
        return `${prefixHtml} — ${pnl} (best ${best} · worst ${worst})`.trim();
      }
      const mode = detail.mode ? `(${detail.mode})` : "";
      const slip = detail.slip_bps != null ? `slip=${Math.round(detail.slip_bps)}bps` : "";
      return `${prefixHtml} ${escapeHtml(mode)} ${escapeHtml(slip)}`.trim();
    }
    if (type === "OPEN") {
      const size = detail.size != null ? `size=${detail.size}` : "";
      const slip = detail.slip_bps != null ? `slip=${Math.round(detail.slip_bps)}bps` : "";
      return `${prefixHtml} ${escapeHtml(size)} ${escapeHtml(slip)}`.trim();
    }
    if (type === "SKIP" || type === "ERROR") {
      const label = reasonCode ? renderAgentReason(reasonCode, type) : escapeHtml(type);
      return `${prefixHtml} — ${label}${ctxHtml}`.trim();
    }
    const reasonHtml = renderAgentReason(reasonCode, type);
    const tail = reasonHtml ? `— ${reasonHtml}` : "";
    return `${prefixHtml} ${tail}${ctxHtml}`.trim();
  }

  function getAgentReason(detail) {
    return detail.reason || detail.error || detail.code || detail.message || "";
  }

  function formatAgentContext(type, detail, reason) {
    const ctx = [];
    const reasonCode = String(reason || "");
    if (reasonCode === "STALE_DATA") {
      if (detail.stale_age_s != null) ctx.push(`${Math.round(detail.stale_age_s)}s`);
      else if (detail.freshness_age_s != null) ctx.push(`${Math.round(detail.freshness_age_s)}s`);
    } else if (reasonCode === "HIGH_IMPACT") {
      if (detail.slip_bps != null) ctx.push(`${Math.round(detail.slip_bps)}bps`);
      if (detail.safe_max_sell != null) ctx.push(`safe=${detail.safe_max_sell}`);
    } else if (type === "CLOSE_CHUNK") {
      if (detail.qty != null) ctx.push(`qty=${detail.qty}`);
      if (detail.remaining != null) ctx.push(`rem=${detail.remaining}`);
    }
    if (!ctx.length) {
      if (detail.book_age_s != null && (reasonCode === "STALE_BOOK" || type === "ERROR")) {
        ctx.push(`${Math.round(detail.book_age_s)}s`);
      }
    }
    return ctx.slice(0, 2).join(", ");
  }

  function eventMarker(type) {
    if (type === "OPEN") return "→ +";
    if (type === "CLOSE_CHUNK") return "→ −";
    if (type === "SKIP") return "·";
    if (type === "ERROR") return "!";
    return "·";
  }

  async function setPauseState(nextPaused) {
    const url = nextPaused ? "/control/pause" : "/control/resume";
    const start = performance.now();
    try {
      const resp = await fetch(url, { method: "POST", headers: { "Accept": "application/json" } });
      const latency = performance.now() - start;
      setLatency(latency);
      if (!resp.ok) {
        showToast("PAUSE FAILED", "warn");
        return;
      }
      const data = await resp.json();
      setPaused(!!data.paused, data.paused_at || data.pausedAt || "");
      showToast(nextPaused ? "⛔ ИСПОЛНЕНИЕ ПРИОСТАНОВЛЕНО" : "✅ ИСПОЛНЕНИЕ ВОЗОБНОВЛЕНО", nextPaused ? "paused" : "resumed");
    } catch (e) {
      showToast("Контроль недоступен", "warn");
    }
  }

  function cancelHold() {
    if (holdTimer) {
      clearTimeout(holdTimer);
      holdTimer = null;
    }
    if (holdRaf) {
      cancelAnimationFrame(holdRaf);
      holdRaf = null;
    }
    if (progressEl) progressEl.style.transform = "scaleX(0)";
    if (killBtn) killBtn.classList.remove("is-holding");
  }

  function startHold() {
    if (!killBtn || killBtn.disabled) return;
    cancelHold();
    holdStart = performance.now();
    killBtn.classList.add("is-holding");
    const tick = (now) => {
      const pct = Math.min(1, (now - holdStart) / HOLD_MS);
      if (progressEl) progressEl.style.transform = `scaleX(${pct})`;
      if (pct < 1) holdRaf = requestAnimationFrame(tick);
    };
    holdRaf = requestAnimationFrame(tick);
    holdTimer = setTimeout(() => {
      cancelHold();
      setPauseState(!state.paused);
    }, HOLD_MS);
  }

  if (killBtn) {
    killBtn.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      startHold();
    });
    ["pointerup", "pointercancel"].forEach((ev) => {
      killBtn.addEventListener(ev, cancelHold);
    });
  }

  function schedule(fn, baseMs, getErrors) {
    const hiddenFactor = document.hidden ? 3 : 1;
    const err = getErrors();
    const backoff = err >= 3 ? 2 : 1;
    const nextMs = Math.max(500, baseMs * hiddenFactor * backoff);
    setTimeout(async () => {
      await fn();
      schedule(fn, baseMs, getErrors);
    }, nextMs);
  }

  function startPolling() {
    if (pollingStarted) return;
    pollingStarted = true;
    schedule(fetchPing, PING_MS, () => pingErrors);
    schedule(fetchState, REFRESH_MS, () => stateErrors);
    schedule(fetchHealth, REFRESH_MS, () => healthErrors);
    schedule(fetchExposure, REFRESH_MS, () => exposureErrors);
    schedule(fetchExecHealth, EXEC_MS, () => execErrors);
    schedule(fetchBookHealth, BOOK_MS, () => bookErrors);
    schedule(fetchAgent, AGENT_POLL_MS, () => agentErrors);
    schedule(fetchEdgePnlReport, 30000, () => edgeReportErrors);
  }

  document.addEventListener("visibilitychange", () => {
    // interval adapts on next tick
  });

  let casesErrors = 0;
  const microEdgeCache = new Map();
  const microEdgeInflight = new Set();
  const microEdgeQueued = new Set();
  const microEdgeQueue = [];
  let microEdgeActive = 0;
  const explainCache = new Map();
  const explainInflight = new Set();
  const explainQueued = new Set();
  const explainQueue = [];
  let explainActive = 0;

  function readMicroCache(marketId, ttlMs) {
    const cached = microCache.get(marketId);
    if (!cached) return null;
    if ((Date.now() - cached.ts) <= ttlMs) return cached.data;
    return null;
  }

  function getMicroEdge(marketId) {
    if (!marketId) return null;
    const cached = microEdgeCache.get(marketId);
    if (cached && (Date.now() - cached.ts) <= MICRO_EDGE_TTL) return cached.data;
    const shared = readMicroCache(marketId, MICRO_EDGE_TTL);
    if (shared) {
      microEdgeCache.set(marketId, { ts: Date.now(), data: shared });
      return shared;
    }
    queueMicroEdgeFetch(marketId);
    return null;
  }

  function queueMicroEdgeFetch(marketId) {
    if (!marketId) return;
    const cached = microEdgeCache.get(marketId);
    if (cached && (Date.now() - cached.ts) <= MICRO_EDGE_TTL) return;
    if (microEdgeInflight.has(marketId) || microEdgeQueued.has(marketId)) return;
    microEdgeQueue.push(marketId);
    microEdgeQueued.add(marketId);
    drainMicroEdgeQueue();
  }

  function drainMicroEdgeQueue() {
    while (microEdgeActive < MICRO_EDGE_MAX && microEdgeQueue.length > 0) {
      const marketId = microEdgeQueue.shift();
      microEdgeQueued.delete(marketId);
      microEdgeInflight.add(marketId);
      microEdgeActive += 1;
      fetch(`/market/micro?market_id=${encodeURIComponent(marketId)}`, { cache: "no-store" })
        .then((resp) => resp.json().then((data) => ({ ok: resp.ok, data })))
        .then(({ ok, data }) => {
          if (!ok || !data) return;
          microEdgeCache.set(marketId, { ts: Date.now(), data });
          microCache.set(marketId, { ts: Date.now(), data });
        })
        .catch(() => null)
        .finally(() => {
          microEdgeInflight.delete(marketId);
          microEdgeActive = Math.max(0, microEdgeActive - 1);
          drainMicroEdgeQueue();
        });
    }
  }

  function updateEdgeLine(row, item) {
    if (!row || !item) return;
    const edgeEl = row.querySelector("[data-edge-line]");
    if (!edgeEl) return;
    const marketId = row.getAttribute("data-case-id");
    const micro = marketId ? getMicroEdge(marketId) : null;
    let ageSec = null;
    if (item.updated_ts) {
      const ms = parseTs(item.updated_ts);
      if (ms) ageSec = Math.max(0, (Date.now() - ms) / 1000);
    }
    const line = buildEdgeLine({
      age_s: ageSec,
      spread_pct: item.spread_pct,
      liq_usd: item.liq_usd,
      depth_ask_1pct: micro ? micro.depth_ask_1pct_usd : null,
      depth_bid_1pct: micro ? micro.depth_bid_1pct_usd : null,
      book_age_s: micro ? micro.book_age_s : null,
      safe_buy: micro ? micro.safe_max_size_buy : null,
      safe_sell: micro ? micro.safe_max_size_sell : null,
      warnings: micro ? micro.warnings : [],
    });
    if (edgeEl.innerHTML !== line) {
      edgeEl.innerHTML = line;
    }
  }

  function getExplain(caseId) {
    if (!caseId) return null;
    const cached = explainCache.get(caseId);
    if (cached && (Date.now() - cached.ts) <= EXPLAIN_TTL) return cached.data;
    queueExplainFetch(caseId);
    return null;
  }

  function getMicro(caseId) {
    if (!caseId) return null;
    const cached = microCache.get(caseId);
    if (cached && cached.data) return cached.data;
    return null;
  }

  function queueExplainFetch(caseId) {
    if (!caseId) return;
    const cached = explainCache.get(caseId);
    if (cached && (Date.now() - cached.ts) <= EXPLAIN_TTL) return;
    if (explainInflight.has(caseId) || explainQueued.has(caseId)) return;
    explainQueue.push(caseId);
    explainQueued.add(caseId);
    drainExplainQueue();
  }

  function drainExplainQueue() {
    while (explainActive < EXPLAIN_MAX && explainQueue.length > 0) {
      const caseId = explainQueue.shift();
      explainQueued.delete(caseId);
      explainInflight.add(caseId);
      explainActive += 1;
      fetch(`/cases/explain?case_id=${encodeURIComponent(caseId)}`, { cache: "no-store" })
        .then((resp) => resp.json().then((data) => ({ ok: resp.ok, data })))
        .then(({ ok, data }) => {
          if (!ok || !data) return;
          explainCache.set(caseId, { ts: Date.now(), data });
        })
        .catch(() => null)
        .finally(() => {
          explainInflight.delete(caseId);
          explainActive = Math.max(0, explainActive - 1);
          drainExplainQueue();
        });
    }
  }

  function updateWhyLine(row, caseId) {
    if (!row || !caseId) return;
    const whyEl = row.querySelector("[data-why-line]");
    if (!whyEl) return;
    const explain = getExplain(caseId);
    const line = buildWhyLine(explain);
    if (whyEl.textContent !== line) {
      whyEl.textContent = line;
    }
  }

  function renderOppsGuided() {
    const wrap = document.querySelector("[data-opps-guided]");
    const grid = document.querySelector("[data-opps-guided-grid]");
    if (!wrap || !grid) return;
    if (localStorage.getItem("ps.opps.mode") !== "guided") return;
    const rows = Array.from(document.querySelectorAll("tr[data-case-id]"));
    const top = rows.slice(0, 5);
    grid.innerHTML = "";
    top.forEach((row) => {
      const caseId = row.getAttribute("data-case-id");
      if (!caseId) return;
      const titleEl = row.querySelector("[data-role='open']");
      const title = titleEl ? titleEl.textContent.trim() : caseId;
      const explain = getExplain(caseId);
      const micro = getMicro(caseId);
      const edgePct = explain && explain.edge_pct != null ? formatEdgePct(explain.edge_pct) : "—";
      const explainType = explain && explain.type ? String(explain.type) : "NONE";
      const badges = [];
      if (explainType) badges.push(explainType);
      const metrics = {
        age_s: null,
        spread_pct: getSpreadPctFromRow(row),
        liq_usd: null,
        depth_ask_1pct: micro ? micro.depth_ask_1pct_usd : null,
        depth_bid_1pct: micro ? micro.depth_bid_1pct_usd : null,
        book_age_s: micro ? micro.book_age_s : null,
        safe_buy: micro ? micro.safe_max_size_buy : null,
        safe_sell: micro ? micro.safe_max_size_sell : null,
        warnings: micro ? micro.warnings || [] : [],
      };
      const label = pickEdgeLabel(metrics);
      if (label && label.text) badges.push(label.text);
      if (metrics.warnings && metrics.warnings.includes("NO_ORDERBOOK")) badges.push("NO_BOOK");
      if (metrics.warnings && metrics.warnings.includes("STALE_BOOK")) badges.push("STALE_BOOK");
      const spreadTxt = formatSpreadPct(metrics.spread_pct);
      const bookAge = metrics.book_age_s != null ? formatAgeCompact(metrics.book_age_s) : "—";
      const depthTxt = formatDepthPair(metrics.depth_ask_1pct, metrics.depth_bid_1pct);
      const why = buildGuidedWhy(explain, micro);
      const depthMin = (metrics.depth_ask_1pct != null && metrics.depth_bid_1pct != null)
        ? Math.min(Number(metrics.depth_ask_1pct), Number(metrics.depth_bid_1pct))
        : null;
      const depthStatus = depthMin == null ? "—" : (depthMin >= GUARD_DEPTH_MIN_USD ? "OK" : "LOW");
      const previewBuy = getPreviewData(caseId, "buy");
      const previewClose = getPreviewData(caseId, "close");
      const safeBuy = previewBuy && previewBuy.safe_max_size_buy != null ? previewBuy.safe_max_size_buy : metrics.safe_buy;
      const safeSell = previewClose && previewClose.safe_max_size_sell != null ? previewClose.safe_max_size_sell : metrics.safe_sell;
      const safeTxt = `${safeBuy != null ? Math.floor(Number(safeBuy)) : "—"}/${safeSell != null ? Math.floor(Number(safeSell)) : "—"}`;
      const guardReasons = [];
      if (state.paused) guardReasons.push("PAUSED");
      if (metrics.book_age_s != null && metrics.book_age_s > GUARD_BOOK_AGE_MAX) guardReasons.push("STALE_BOOK");
      if (metrics.spread_pct != null && Number(metrics.spread_pct) > GUARD_SPREAD_MAX) guardReasons.push("WIDE_SPREAD");
      if (depthMin != null && depthMin < GUARD_DEPTH_MIN_USD) guardReasons.push("LOW_DEPTH");
      const guardBadges = guardReasons.length
        ? guardReasons.map((r) => `<span class="badge badge-yellow">${r}</span>`).join("")
        : "";

      const card = document.createElement("div");
      card.className = "opps-card";
      card.innerHTML = `
        <div class="opps-card-top">
          <div class="opps-edge">${edgePct}</div>
          <div class="opps-badges">
            ${badges.slice(0, 2).map((b) => `<span class="badge badge-gray">${escapeHtml(b)}</span>`).join("")}
          </div>
        </div>
        <div class="opps-title">${escapeHtml(title)}</div>
        <div class="opps-metric">spr ${spreadTxt} · book ${bookAge} · depth ${depthTxt}</div>
        <div class="opps-status mono">BOOK ${bookAge} · SPREAD ${spreadTxt} · DEPTH ${depthStatus} · SAFE ${safeTxt}</div>
        <div class="opps-why">${escapeHtml(why)}</div>
        <div class="opps-actions">
          <button class="btn btn-success btn-sm trade-action" type="button" data-paper-action="buy" data-case-id="${escapeHtml(caseId)}">BUY</button>
          <button class="btn btn-danger btn-sm trade-action" type="button" data-paper-action="close" data-case-id="${escapeHtml(caseId)}">SELL</button>
          ${guardBadges}
          <button class="pill" type="button" data-opps-why-toggle>Why…</button>
        </div>
        <div class="opps-why-details">${escapeHtml(why)}</div>
      `;
      grid.appendChild(card);
    });
  }

  async function pollCasesTop() {
    const table = document.querySelector("[data-cases-table]");
    if (!table) return;
    const rows = Array.from(document.querySelectorAll("tr[data-case-id]"));
    if (rows.length === 0) return;
    const params = new URLSearchParams(window.location.search);
    const ids = rows.map((r) => r.getAttribute("data-case-id")).filter(Boolean);
    params.set("limit", String(Math.min(ids.length, 50)));
    params.set("ids", ids.join(","));
    try {
      const resp = await fetch(`/cases/live?${params.toString()}`, { cache: "no-store" });
      if (!resp.ok) {
        casesErrors += 1;
        return;
      }
      const data = await resp.json();
      const map = new Map();
      (data.items || []).forEach((r) => {
        if (r.case_id) map.set(String(r.case_id), r);
      });
      rows.forEach((row) => {
        if (!row.querySelector("[data-edge-line]")) return;
        const marketId = row.getAttribute("data-case-id");
        if (marketId) queueMicroEdgeFetch(marketId);
      });
      rows.forEach((row) => {
        if (!row.querySelector("[data-why-line]")) return;
        const caseId = row.getAttribute("data-case-id");
        if (caseId) queueExplainFetch(caseId);
      });
      rows.forEach((row) => {
        const isPending = row.dataset.pending === "1";
        const caseId = row.getAttribute("data-case-id");
        const item = map.get(caseId);
        if (!item) return;
        if (item.spread_pct != null) {
          row.dataset.spreadPct = String(item.spread_pct);
        }

        if (!isPending) {
          const statusEl = row.querySelector("[data-case-status]");
          if (statusEl && item.status) {
            const statusMap = { OK: "ОК", INVESTIGATE: "Проверить", BLOCKED: "Заблокировано" };
            const nextStatus = statusMap[item.status] || item.status;
            if (statusEl.textContent !== nextStatus) {
              statusEl.textContent = nextStatus;
              if (state.staleLevel === "ok" && !state.paused) flashCell(statusEl);
            }
          }
        }
        const lastEl = row.querySelector("[data-case-last]");
        if (lastEl && item.updated_ts) {
          const txt = String(item.updated_ts).replace("T", " ");
          if (lastEl.textContent.indexOf(txt) < 0) {
            lastEl.textContent = txt;
            if (state.staleLevel === "ok" && !state.paused) flashCell(lastEl);
          }
        }

        const fmtNum = (v, d, suffix="") => (v == null ? "—" : `${Number(v).toFixed(d)}${suffix}`);
        const sumEl = row.querySelector("[data-case-sum-mid]");
        const sumVal = item.sum_mid;
        if (sumEl) {
          const next = fmtNum(sumVal, 3);
          if (sumEl.textContent !== next) {
            const prev = Number(sumEl.getAttribute("data-prev") || "0");
            sumEl.textContent = next;
            sumEl.setAttribute("data-prev", String(sumVal || 0));
            if (state.staleLevel === "ok" && !state.paused) {
              sumEl.classList.remove("tick-up", "tick-down");
              void sumEl.offsetWidth;
              sumEl.classList.add(sumVal > prev ? "tick-up" : "tick-down");
            }
          }
        }
        const spEl = row.querySelector("[data-case-spread]");
        const spVal = item.spread_pct;
        if (spEl) {
          const next = fmtNum(spVal, 2, "%");
          if (spEl.textContent !== next) {
            const prev = Number(spEl.getAttribute("data-prev") || "0");
            spEl.textContent = next;
            spEl.setAttribute("data-prev", String(spVal || 0));
            if (state.staleLevel === "ok" && !state.paused) {
              spEl.classList.remove("tick-up", "tick-down");
              void spEl.offsetWidth;
              spEl.classList.add(spVal < prev ? "tick-up" : "tick-down");
            }
          }
        }
        const liqEl = row.querySelector("[data-case-liq]");
        const liqVal = item.liq_usd;
        if (liqEl) {
          const next = fmtNum(liqVal, 0);
          if (liqEl.textContent !== next) {
            const prev = Number(liqEl.getAttribute("data-prev") || "0");
            liqEl.textContent = next;
            liqEl.setAttribute("data-prev", String(liqVal || 0));
            if (state.staleLevel === "ok" && !state.paused) {
              liqEl.classList.remove("tick-up", "tick-down");
              void liqEl.offsetWidth;
              liqEl.classList.add(liqVal > prev ? "tick-up" : "tick-down");
            }
          }
        }

        if (item.updated_ts) {
          const ms = parseTs(item.updated_ts);
          if (ms) {
            const ageSec = Math.max(0, (Date.now() - ms) / 1000);
            row.classList.remove("row-age-warn", "row-age-bad");
            const staleBadge = row.querySelector("[data-case-stale]");
            if (ageSec > 60) {
              row.classList.add("row-age-bad");
              if (staleBadge) staleBadge.style.display = "inline-flex";
                row.querySelectorAll("button[data-paper-action]").forEach((btn) => {
                  btn.setAttribute("disabled", "disabled");
                });
              } else if (ageSec > 20) {
                row.classList.add("row-age-warn");
                if (staleBadge) staleBadge.style.display = "none";
                row.querySelectorAll("button[data-paper-action]").forEach((btn) => {
                  if (state.staleLevel === "hard") return;
                  btn.removeAttribute("disabled");
                });
              } else {
                if (staleBadge) staleBadge.style.display = "none";
                row.querySelectorAll("button[data-paper-action]").forEach((btn) => {
                  if (state.staleLevel === "hard") return;
                  btn.removeAttribute("disabled");
                });
            }
          }
        }

        updateEdgeLine(row, item);
        updateWhyLine(row, caseId);
        renderOppsGuided();

        if (explainOpenId === caseId && explainAnchor) {
          const microCached = microCache.get(caseId);
          const preview = getPreviewData(caseId, explainOpenAction);
          renderExplainPopover(explainAnchor, row, explainOpenAction, microCached ? microCached.data : null, preview);
        }
        });
      casesErrors = 0;
    } catch (e) {
      casesErrors += 1;
    }
  }

  const previewCache = new Map();
  let previewEl = null;
  let explainEl = null;
  let explainOpenId = null;
  let explainOpenAction = "buy";
  let explainAnchor = null;
  let disabledTipEl = null;
  let disabledTipTarget = null;
  function ensurePreviewEl() {
    if (previewEl) return previewEl;
    previewEl = document.createElement("div");
    previewEl.className = "exec-preview";
    previewEl.style.display = "none";
    document.body.appendChild(previewEl);
    return previewEl;
  }

  function renderPreview(data) {
      if (!data) return "Нет данных";
    const fmt = (v, d = 3) => (v == null ? "—" : Number(v).toFixed(d));
      const warnings = data.warnings || [];
      const warnMap = {
        SIZE_MISSING: "РАЗМЕР НЕ ЗАДАН",
        INSUFFICIENT_DEPTH: "НЕДОСТАТОЧНАЯ ГЛУБИНА",
        NO_ORDERBOOK: "НЕТ КНИГИ",
        STALE_BOOK: "СТАРАЯ КНИГА",
        TOP_OF_BOOK_ONLY: "ТОЛЬКО ТОП КНИГИ",
      };
      const warn = warnings.map((w) => warnMap[w] || w).join(", ");
    const sizeMissing = warnings.includes("SIZE_MISSING");
    return `
        <div class="row"><span class="label">Мид</span><span class="value">${fmt(data.mid)}</span></div>
        <div class="row"><span class="label">VWAP (оценка)</span><span class="value">${fmt(data.est_vwap)}</span></div>
        <div class="row"><span class="label">Проскальз.</span><span class="value">${data.slip_bps != null ? `${Math.round(data.slip_bps)} бпс` : "—"}</span></div>
        <div class="row"><span class="label">На</span><span class="value">${data.as_of ? formatTs(data.as_of) : "—"}</span></div>
        ${sizeMissing ? `<div class="row"><span class="label">Примечание</span><span class="value warn">Только топ книги (размер не задан)</span></div>` : ""}
        ${warn ? `<div class="row"><span class="label">Предупр.</span><span class="value warn">${warn}</span></div>` : ""}
      `;
  }

  function showPreview(target, data) {
    const el = ensurePreviewEl();
    el.innerHTML = renderPreview(data);
    const rect = target.getBoundingClientRect();
    const top = Math.min(window.innerHeight - 120, rect.bottom + 6);
    const left = Math.min(window.innerWidth - 220, rect.left);
    el.style.top = `${Math.max(8, top)}px`;
    el.style.left = `${Math.max(8, left)}px`;
    el.style.display = "block";
  }

  function hidePreview() {
    if (!previewEl) return;
    previewEl.style.display = "none";
  }

  async function fetchPreview(marketId, action, size) {
    if (!marketId) return null;
    const key = `${marketId}:${action}`;
    const cached = previewCache.get(key);
    const now = Date.now();
    if (cached && (now - cached.ts) < 1500) return cached.data;
    if (state.paused || state.staleLevel === "hard") return null;
    try {
      const resp = await fetch("/exec/preview", {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        credentials: "same-origin",
        body: JSON.stringify({ market_id: marketId, action, side: "YES", size_shares: size }),
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.ok === false) return null;
      previewCache.set(key, { ts: now, data });
      return data;
    } catch (e) {
      return null;
    }
  }

  async function handlePreviewTrigger(target) {
    if (!target) return;
    const btn = target.closest("button[data-paper-action][data-case-id], [data-preview-trigger][data-case-id]");
    if (!btn) return;
    const row = btn.closest("tr");
    if (row && row.classList.contains("row-age-bad")) return;
    const marketId = btn.getAttribute("data-case-id");
    const action = btn.getAttribute("data-paper-action") || "buy";
    const size = getPaperSize(btn);
    const data = await fetchPreview(marketId, action, size);
    if (data) {
      showPreview(btn, data);
      if (row) applySafeSizeFromPreview(row, data);
    }
  }

  function handlePreviewEnter(e) {
    handlePreviewTrigger(e.target);
  }

  function handlePreviewLeave() {
    hidePreview();
  }

  const microCache = new Map();
  let microEl = null;
  let microOpenId = null;

  function ensureExplainEl() {
    if (explainEl) return explainEl;
    explainEl = document.createElement("div");
    explainEl.className = "explain-popover";
    explainEl.style.display = "none";
    document.body.appendChild(explainEl);
    return explainEl;
  }

  function ensureDisabledTipEl() {
    if (disabledTipEl) return disabledTipEl;
    disabledTipEl = document.createElement("div");
    disabledTipEl.className = "disabled-tooltip";
    disabledTipEl.style.display = "none";
    document.body.appendChild(disabledTipEl);
    return disabledTipEl;
  }

  function showDisabledTip(target, text) {
    if (!target || !text) return;
    const el = ensureDisabledTipEl();
    el.textContent = text;
    const rect = target.getBoundingClientRect();
    const top = Math.min(window.innerHeight - 40, rect.top - 6);
    const left = Math.min(window.innerWidth - 260, rect.left);
    el.style.top = `${Math.max(8, top)}px`;
    el.style.left = `${Math.max(8, left)}px`;
    el.style.display = "block";
    disabledTipTarget = target;
  }

  function hideDisabledTip() {
    if (!disabledTipEl) return;
    disabledTipEl.style.display = "none";
    disabledTipTarget = null;
  }

  function renderExplainPopover(target, row, action, micro, preview) {
    if (!target || !row) return;
    const el = ensureExplainEl();
    el.innerHTML = "";
    const lines = buildDecisionExplain(row, action, micro, preview);
    lines.forEach((line) => {
      const lineEl = document.createElement("div");
      lineEl.className = `explain-line ${line.ok === false ? "explain-fail" : "explain-ok"}${line.summary ? " explain-summary" : ""}`;
      const mark = document.createElement("span");
      mark.className = "explain-mark";
      mark.textContent = line.summary ? "→" : (line.ok === false ? "✗" : "✓");
      const text = document.createElement("span");
      text.className = "explain-text";
      text.textContent = line.text;
      lineEl.appendChild(mark);
      lineEl.appendChild(text);
      el.appendChild(lineEl);
    });

    const rect = target.getBoundingClientRect();
    const top = Math.min(window.innerHeight - 160, rect.bottom + 6);
    const left = Math.min(window.innerWidth - 260, rect.left);
    el.style.top = `${Math.max(8, top)}px`;
    el.style.left = `${Math.max(8, left)}px`;
    el.style.display = "block";
    explainOpenId = row.getAttribute("data-case-id");
    explainOpenAction = action;
    explainAnchor = target;
  }

  function hideExplain() {
    if (!explainEl) return;
    explainEl.style.display = "none";
    explainOpenId = null;
    explainOpenAction = "buy";
    explainAnchor = null;
  }

  async function handleExplainClick(e) {
    const btn = e.target.closest("[data-explain-trigger][data-case-id]");
    if (!btn) {
      if (explainEl && explainEl.style.display !== "none" && !explainEl.contains(e.target)) {
        hideExplain();
      }
      return;
    }
    e.preventDefault();
    if (state.paused || state.staleLevel === "hard") {
      showToast(state.paused ? "⛔ Исполнение на паузе" : "⚠ Данные устарели — торговля заблокирована", "warn");
      return;
    }
    const marketId = btn.getAttribute("data-case-id");
    const action = btn.getAttribute("data-paper-action") || "buy";
    if (explainOpenId === marketId && explainOpenAction === action && explainEl && explainEl.style.display !== "none") {
      hideExplain();
      return;
    }
    const row = btn.closest("tr");
    const micro = await fetchMicro(marketId);
    const size = getPaperSize(btn);
    const preview = await fetchPreview(marketId, action, size);
    renderExplainPopover(btn, row, action, micro, preview);
  }

  function ensureMicroEl() {
    if (microEl) return microEl;
    microEl = document.createElement("div");
    microEl.className = "micro-popover";
    microEl.style.display = "none";
    document.body.appendChild(microEl);
    return microEl;
  }

  function renderMicro(data) {
    const fmt = (v, d = 3) => (v == null ? "—" : Number(v).toFixed(d));
    const fmtUsd = (v) => (v == null ? "—" : `$${Number(v).toFixed(0)}`);
    const d1a = fmtUsd(data.depth_ask_1pct_usd);
    const d1b = fmtUsd(data.depth_bid_1pct_usd);
    const d2a = fmtUsd(data.depth_ask_2pct_usd);
    const d2b = fmtUsd(data.depth_bid_2pct_usd);
    const spread = (data.spread_abs != null && data.spread_pct != null)
      ? `${fmt(data.spread_abs)} (${Number(data.spread_pct).toFixed(2)}%)`
      : "—";
    return `
      <div class="row"><span class="label">Мид</span><span class="value">${fmt(data.mid)}</span></div>
      <div class="row"><span class="label">Бид</span><span class="value">${fmt(data.bid)}</span></div>
      <div class="row"><span class="label">Аск</span><span class="value">${fmt(data.ask)}</span></div>
      <div class="row"><span class="label">Спред</span><span class="value">${spread}</span></div>
      <div class="row"><span class="label">Глубина@1%</span><span class="value">A ${d1a} / B ${d1b}</span></div>
      <div class="row"><span class="label">Глубина@2%</span><span class="value">A ${d2a} / B ${d2b}</span></div>
      <div class="row"><span class="label">Возраст книги</span><span class="value">${data.book_age_s != null ? `${Math.round(data.book_age_s)}с` : "—"}</span></div>
    `;
  }

  async function fetchMicro(marketId) {
    if (!marketId) return null;
    const cached = microCache.get(marketId);
    const now = Date.now();
    if (cached && (now - cached.ts) < 2000) return cached.data;
    try {
      const resp = await fetch(`/market/micro?market_id=${encodeURIComponent(marketId)}`, { cache: "no-store" });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data) return null;
      microCache.set(marketId, { ts: now, data });
      return data;
    } catch (e) {
      return null;
    }
  }

  function showMicro(target, data, marketId) {
    const el = ensureMicroEl();
    el.innerHTML = renderMicro(data);
    const rect = target.getBoundingClientRect();
    const top = Math.min(window.innerHeight - 160, rect.bottom + 6);
    const left = Math.min(window.innerWidth - 240, rect.left);
    el.style.top = `${Math.max(8, top)}px`;
    el.style.left = `${Math.max(8, left)}px`;
    el.style.display = "block";
    microOpenId = marketId;
  }

  function hideMicro() {
    if (!microEl) return;
    microEl.style.display = "none";
    microOpenId = null;
  }

  async function handleMicroClick(e) {
    const btn = e.target.closest("[data-micro-trigger][data-market-id]");
    if (!btn) return;
    e.preventDefault();
    if (state.paused || state.staleLevel === "hard") {
      showToast(state.paused ? "⛔ Исполнение на паузе" : "⚠ Данные устарели — торговля заблокирована", "warn");
      return;
    }
    const marketId = btn.getAttribute("data-market-id");
    if (microOpenId === marketId && microEl && microEl.style.display !== "none") {
      hideMicro();
      return;
    }
    const data = await fetchMicro(marketId);
    if (data) {
      showMicro(btn, data, marketId);
      const row = btn.closest("tr");
      if (row) applySafeSizeFromMicro(row, data, false);
    }
  }

  function handleSizeClick(e) {
    const chip = e.target.closest(".size-chip[data-paper-size]");
    if (!chip) return;
    const wrap = chip.closest(".paper-size");
    if (!wrap) return;
    const sizeVal = chip.getAttribute("data-paper-size");
    if (!sizeVal) return;
    wrap.setAttribute("data-paper-size", sizeVal);
    wrap.querySelectorAll(".size-chip").forEach((el) => el.classList.remove("is-active"));
    chip.classList.add("is-active");
  }

  async function refreshGuardForRow(row) {
    const marketId = row.getAttribute("data-case-id");
    if (!marketId) return;
    const micro = await fetchMicro(marketId);
    const { spreadPct, bookAge } = evaluateGuard(row, micro);
    const warnBuy = getPreviewWarnings(marketId, "buy");
    const warnClose = getPreviewWarnings(marketId, "close");
    const prevBuy = getPreviewData(marketId, "buy");
    const prevClose = getPreviewData(marketId, "close");
    const hasPreviewSafe = (prevBuy && (prevBuy.safe_max_size_buy != null || prevBuy.safe_max_size_sell != null)) ||
      (prevClose && (prevClose.safe_max_size_buy != null || prevClose.safe_max_size_sell != null));
    applySafeSizeFromMicro(row, micro, hasPreviewSafe);
    const depthAsk = micro ? micro.depth_ask_1pct_usd : null;
    const depthBid = micro ? micro.depth_bid_1pct_usd : null;

    const buyBtn = row.querySelector("button[data-paper-action='buy']");
    const closeBtn = row.querySelector("button[data-paper-action='close']");

    let buyReason = "";
    let buyDetail = "";
    const buySize = getPaperSize(buyBtn);
    const closeSize = getPaperSize(closeBtn);
    if (spreadPct != null && spreadPct > GUARD_SPREAD_MAX) buyReason = "ШИРОКИЙ СПРЕД";
    else if (depthAsk != null && Number(depthAsk) < GUARD_DEPTH_MIN_USD) buyReason = "СЛАБАЯ ГЛУБИНА";
    else if (bookAge != null && Number(bookAge) > GUARD_BOOK_AGE_MAX) buyReason = "СТАРАЯ КНИГА";
    else if (warnBuy.includes("INSUFFICIENT_DEPTH")) buyReason = "СЛАБАЯ ГЛУБИНА";
    else if (buySize != null && prevBuy && prevBuy.slip_bps != null && Number.isFinite(Number(prevBuy.slip_bps)) && Math.abs(Number(prevBuy.slip_bps)) > GUARD_MAX_SLIP_BPS) {
      const bps = Math.round(Number(prevBuy.slip_bps));
      buyReason = "ВЫСОКИЙ ИМПАКТ";
      const safeHint = prevBuy.safe_max_size_buy != null ? `, макс. безопасный ${Math.floor(Number(prevBuy.safe_max_size_buy))}` : "";
      buyDetail = `Высокий импакт (${bps} бпс > ${GUARD_MAX_SLIP_BPS} бпс${safeHint})`;
    }
    if (buyBtn) {
      if (buyDetail) buyBtn.dataset.guardDetail = buyDetail;
      else delete buyBtn.dataset.guardDetail;
    }
    setGuardState(buyBtn, buyReason);

    let closeReason = "";
    let closeDetail = "";
    if (spreadPct != null && spreadPct > GUARD_SPREAD_MAX) closeReason = "ШИРОКИЙ СПРЕД";
    else if (depthBid != null && Number(depthBid) < GUARD_DEPTH_MIN_USD) closeReason = "СЛАБАЯ ГЛУБИНА";
    else if (bookAge != null && Number(bookAge) > GUARD_BOOK_AGE_MAX) closeReason = "СТАРАЯ КНИГА";
    else if (warnClose.includes("INSUFFICIENT_DEPTH")) closeReason = "СЛАБАЯ ГЛУБИНА";
    else if (closeSize != null && prevClose && prevClose.slip_bps != null && Number.isFinite(Number(prevClose.slip_bps)) && Math.abs(Number(prevClose.slip_bps)) > GUARD_MAX_SLIP_BPS) {
      const bps = Math.round(Number(prevClose.slip_bps));
      closeReason = "ВЫСОКИЙ ИМПАКТ";
      const safeHint = prevClose.safe_max_size_sell != null ? `, макс. безопасный ${Math.floor(Number(prevClose.safe_max_size_sell))}` : "";
      closeDetail = `Высокий импакт (${bps} бпс > ${GUARD_MAX_SLIP_BPS} бпс${safeHint})`;
    }
    if (closeBtn) {
      if (closeDetail) closeBtn.dataset.guardDetail = closeDetail;
      else delete closeBtn.dataset.guardDetail;
    }
    setGuardState(closeBtn, closeReason);

    if (prevBuy || prevClose) {
      const safeBuy = prevBuy && prevBuy.safe_max_size_buy != null ? prevBuy.safe_max_size_buy : (prevClose ? prevClose.safe_max_size_buy : null);
      const safeSell = prevBuy && prevBuy.safe_max_size_sell != null ? prevBuy.safe_max_size_sell : (prevClose ? prevClose.safe_max_size_sell : null);
      updateSafeSizeDisplay(row, safeBuy, safeSell);
    }

    syncTradeButtons();

    if (explainOpenId === marketId) {
      const preview = getPreviewData(marketId, explainOpenAction);
      renderExplainPopover(explainAnchor || row, row, explainOpenAction, micro, preview);
    }
  }

  async function refreshGuardRows() {
    const rows = Array.from(document.querySelectorAll("tr[data-case-id]"));
    if (!rows.length) return;
    for (const row of rows) {
      await refreshGuardForRow(row);
    }
  }

  let guardHoldTimer = null;
  let guardHoldRaf = null;
  let guardHoldBtn = null;
  let guardHoldReason = "";

  function cancelGuardHold() {
    if (guardHoldTimer) clearTimeout(guardHoldTimer);
    if (guardHoldRaf) cancelAnimationFrame(guardHoldRaf);
    guardHoldTimer = null;
    guardHoldRaf = null;
    if (guardHoldBtn) guardHoldBtn.classList.remove("guard-holding");
    guardHoldBtn = null;
    guardHoldReason = "";
  }

  function startGuardHold(btn) {
    if (!btn || btn.getAttribute("data-guarded") !== "1") return;
    cancelGuardHold();
    guardHoldBtn = btn;
    guardHoldReason = btn.nextElementSibling ? btn.nextElementSibling.textContent : "";
    btn.classList.add("guard-holding");
    guardHoldTimer = setTimeout(() => {
      btn.setAttribute("data-guard-override", "1");
      showToast(`Обход защиты: ${guardHoldReason || "защита"}`, "warn");
      const caseId = btn.getAttribute("data-case-id");
      const action = btn.getAttribute("data-paper-action");
      cancelGuardHold();
      paperActionRequest(caseId, action, btn);
      setTimeout(() => {
        btn.removeAttribute("data-guard-override");
      }, 1500);
    }, GUARD_HOLD_MS);
  }

  function previewActiveRow() {
    const rows = getNavRows();
    if (!rows.length) return;
    const idx = activeIndex >= 0 ? activeIndex : 0;
    const row = rows[idx];
    const btn = row.querySelector("button[data-paper-action]");
    if (btn) handlePreviewTrigger(btn);
  }

  function togglePaperDisclosure(row, force) {
    if (!row) return;
    const cell = row.querySelector(".paper-cell");
    if (!cell) return;
    const next = force != null ? !!force : !cell.classList.contains("is-expanded");
    cell.classList.toggle("is-expanded", next);
    const toggle = cell.querySelector("[data-paper-toggle]");
    if (toggle) toggle.setAttribute("aria-expanded", next ? "true" : "false");
  }

  function toggleActivePaperDisclosure() {
    const rows = getNavRows();
    if (!rows.length) return;
    const idx = activeIndex >= 0 ? activeIndex : 0;
    togglePaperDisclosure(rows[idx]);
  }

  let batchHoldTimer = null;
  let batchHoldRaf = null;
  let batchHoldStart = 0;
  let batchHoldBtn = null;

  function cancelBatchHold() {
    if (batchHoldTimer) clearTimeout(batchHoldTimer);
    if (batchHoldRaf) cancelAnimationFrame(batchHoldRaf);
    batchHoldTimer = null;
    batchHoldRaf = null;
    if (batchHoldBtn) {
      batchHoldBtn.classList.remove("is-holding");
      const prog = batchHoldBtn.querySelector(".batch-progress");
      if (prog) prog.style.transform = "scaleX(0)";
    }
    batchHoldBtn = null;
  }

  async function runBatch(btn) {
    const op = btn.getAttribute("data-batch-op");
    const count = Number(btn.getAttribute("data-batch-count") || "0");
    if (!op) return;
    if (state.paused || state.staleLevel === "hard") {
      showToast(state.paused ? "⛔ Исполнение на паузе" : "⚠ Данные устарели — торговля заблокирована", "warn");
      return;
    }
    setButtonLoading(btn, true);
    try {
      const resp = await fetch("/paper/batch", {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        credentials: "same-origin",
        body: JSON.stringify({ mode: "paper", op, filters: { status: "OPEN" } }),
      });
      const data = await resp.json().catch(() => null);
      if (!resp.ok || !data || data.ok === false) {
        showToast("Пакетное закрытие не выполнено", "warn");
        return;
      }
      showToast(`✅ Закрыто ${data.closed || 0} / ${count}`, "resumed");
      document.querySelectorAll("tr[data-case-id] [data-position-status]").forEach((el) => {
        el.textContent = "ЗАКРЫТО";
      });
      document.querySelectorAll("button[data-paper-action='close']").forEach((b) => b.setAttribute("disabled", "disabled"));
      if (data.updated_badges) updateNavBadges(data.updated_badges);
      fetchExposure();
    } catch (e) {
      showToast("Ошибка сети", "warn");
    } finally {
      setButtonLoading(btn, false);
    }
  }

  function startBatchHold(btn) {
    if (!btn || btn.disabled) return;
    cancelBatchHold();
    batchHoldBtn = btn;
    batchHoldStart = performance.now();
    btn.classList.add("is-holding");
    const prog = btn.querySelector(".batch-progress");
    const tick = (now) => {
      const pct = Math.min(1, (now - batchHoldStart) / HOLD_MS);
      if (prog) prog.style.transform = `scaleX(${pct})`;
      if (pct < 1) batchHoldRaf = requestAnimationFrame(tick);
    };
    batchHoldRaf = requestAnimationFrame(tick);
    batchHoldTimer = setTimeout(() => {
      cancelBatchHold();
      runBatch(btn);
    }, HOLD_MS);
  }

  function isEditableTarget(target) {
    if (!target) return false;
    if (target.isContentEditable) return true;
    const tag = (target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select";
  }

  let activeIndex = -1;
  function getNavRows() {
    const rows = Array.from(document.querySelectorAll("tr[data-case-id], tr[data-market-id]"));
    return rows.filter((row) => row.querySelector("[data-role='open']") || row.dataset.href);
  }

  function clearActiveRow() {
    document.querySelectorAll("tr.is-active").forEach((row) => row.classList.remove("is-active"));
    activeIndex = -1;
  }

  function setActiveRow(index) {
    const rows = getNavRows();
    if (!rows.length) return;
    const nextIndex = Math.max(0, Math.min(index, rows.length - 1));
    rows.forEach((r) => r.classList.remove("is-active"));
    const row = rows[nextIndex];
    row.classList.add("is-active");
    row.scrollIntoView({ block: "nearest" });
    activeIndex = nextIndex;
  }

  function moveActiveRow(delta) {
    const rows = getNavRows();
    if (!rows.length) return;
    if (activeIndex < 0 || activeIndex >= rows.length) {
      setActiveRow(0);
      return;
    }
    setActiveRow(activeIndex + delta);
  }

  function openActiveRow() {
    const rows = getNavRows();
    if (!rows.length) return;
    const idx = activeIndex >= 0 ? activeIndex : 0;
    const row = rows[idx];
    const link = row.querySelector("[data-role='open']");
    if (link && link.href) {
      link.click();
      return;
    }
    if (row.dataset.href) window.location.assign(row.dataset.href);
  }

  function runRowAction(action) {
    const rows = getNavRows();
    if (!rows.length) return;
    const idx = activeIndex >= 0 ? activeIndex : 0;
    const row = rows[idx];
    const btn = row.querySelector(`button[data-paper-action='${action}']`);
    if (btn) btn.click();
  }

  let gotoTimer = null;
  let gotoMode = false;

  function startGotoMode() {
    gotoMode = true;
    if (gotoTimer) clearTimeout(gotoTimer);
    gotoTimer = setTimeout(() => {
      gotoMode = false;
    }, 900);
  }

  function handleHotkeys(e) {
    if (e.defaultPrevented) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (isEditableTarget(e.target)) return;

    const key = e.key;

    if (gotoMode) {
      gotoMode = false;
      if (key === "o") window.location.assign("/cases");
      if (key === "s") window.location.assign("/signals");
      if (key === "p") window.location.assign("/positions");
      return;
    }

    if (key === "g") {
      startGotoMode();
      return;
    }

    if (key === "/") {
      const input = document.querySelector("input[type='search'], input[name='q'], input[data-role='search']");
      if (input) {
        e.preventDefault();
        input.focus();
        input.select?.();
      }
      return;
    }

    if (key === "Escape") {
      if (document.activeElement && isEditableTarget(document.activeElement)) document.activeElement.blur();
      clearActiveRow();
      hideExplain();
      hideDisabledTip();
      return;
    }

    if (key === "ArrowDown") {
      e.preventDefault();
      moveActiveRow(1);
      return;
    }
    if (key === "ArrowUp") {
      e.preventDefault();
      moveActiveRow(-1);
      return;
    }
    if (key === "Enter") {
      e.preventDefault();
      openActiveRow();
      return;
    }
    if (key === "b") {
      runRowAction("buy");
      return;
    }
    if (key === "c") {
      runRowAction("close");
      return;
    }
    if (key === "v") {
      previewActiveRow();
      return;
    }
    if (key === "e") {
      e.preventDefault();
      toggleActivePaperDisclosure();
      return;
    }
  }

  let microErrors = 0;
  async function fetchMicroPanel() {
    const panel = document.querySelector("[data-micro-panel][data-market-id]");
    if (!panel) return;
    const marketId = panel.getAttribute("data-market-id");
    if (!marketId) return;
    try {
      const resp = await fetch(`/market/micro?market_id=${encodeURIComponent(marketId)}`, { cache: "no-store" });
      if (!resp.ok) {
        microErrors += 1;
        return;
      }
      const data = await resp.json();
      const fmt = (v, d = 3) => (v == null ? "—" : Number(v).toFixed(d));
      const fmtUsd = (v) => (v == null ? "—" : `$${Number(v).toFixed(0)}`);
      panel.querySelector("[data-micro='mid']").textContent = fmt(data.mid);
      panel.querySelector("[data-micro='bid']").textContent = fmt(data.bid);
      panel.querySelector("[data-micro='ask']").textContent = fmt(data.ask);
      if (data.spread_abs != null && data.spread_pct != null) {
        panel.querySelector("[data-micro='spread']").textContent = `${fmt(data.spread_abs)} (${Number(data.spread_pct).toFixed(2)}%)`;
      } else {
        panel.querySelector("[data-micro='spread']").textContent = "—";
      }
      panel.querySelector("[data-micro='depth1']").textContent = fmtUsd(data.depth_1pct_usd);
      panel.querySelector("[data-micro='depth2']").textContent = fmtUsd(data.depth_2pct_usd);
      panel.querySelector("[data-micro='age']").textContent = data.book_age_s != null ? `${Math.round(data.book_age_s)}s` : "—";
      microErrors = 0;
    } catch (e) {
      microErrors += 1;
    }
  }

  setPaused(state.paused, "");
  setFreshness(state.lastUpdate);
  ensurePausedBanner();
  fetchState();
  fetchPing();
  fetchHealth();
  fetchExposure();
  fetchEdgePnlReport();
  fetchExecHealth();
  fetchBookHealth();
  fetchMicroPanel();
  document.addEventListener("click", handlePaperClick);
  document.addEventListener("keydown", handleHotkeys);
  document.addEventListener("click", handleMicroClick);
  document.addEventListener("click", handleExplainClick);
  document.addEventListener("click", handleSizeClick);
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-opps-mode]");
    if (!btn) return;
    e.preventDefault();
    const mode = btn.getAttribute("data-opps-mode") || "terminal";
    localStorage.setItem("ps.opps.mode", mode);
    const guided = document.querySelector("[data-opps-guided]");
    const table = document.querySelector("[data-cases-table]");
    if (guided) guided.style.display = mode === "guided" ? "block" : "none";
    if (table) table.style.display = mode === "guided" ? "none" : "block";
    document.querySelectorAll("[data-opps-mode]").forEach((b) => {
      b.classList.toggle("pill-ok", b.getAttribute("data-opps-mode") === mode);
      b.classList.toggle("pill-muted", b.getAttribute("data-opps-mode") !== mode);
    });
    renderOppsGuided();
  });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-opps-why-toggle]");
    if (!btn) return;
    e.preventDefault();
    const details = btn.closest(".opps-card")?.querySelector(".opps-why-details");
    if (details) details.classList.toggle("show");
  });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-paper-toggle]");
    if (!btn) return;
    e.preventDefault();
    const row = btn.closest("tr");
    togglePaperDisclosure(row);
  });
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-preview-trigger]");
    if (!btn) return;
    e.preventDefault();
    handlePreviewTrigger(btn);
  });
  function setupGlobalHScroll() {
    const bar = document.getElementById("global-hscroll");
    const inner = document.getElementById("global-hscroll-inner");
    if (!bar || !inner) return;
    if (window.ENABLE_STICKY_XSCROLL === false) return;
    const wrap = document.querySelector("[data-xscroll='opps']");
    if (!wrap) return;
    let active = null;
    let syncing = false;

    function updateBar() {
      if (!active) {
        bar.style.display = "none";
        body.classList.remove("has-global-hscroll");
        return;
      }
      const host = active;
      const table = host.querySelector("table");
      const needs = host.scrollWidth > host.clientWidth + 1;
      if (window.ENABLE_STICKY_XSCROLL_DEBUG) {
        console.log(
          "[xscroll]",
          "host",
          !!host,
          "bar",
          !!bar,
          "hostW",
          host.clientWidth,
          host.scrollWidth,
          "tableW",
          table ? table.clientWidth : null,
          table ? table.scrollWidth : null,
          "needs",
          needs
        );
      }
      if (!needs) {
        bar.style.display = "none";
        body.classList.remove("has-global-hscroll");
        return;
      }
      inner.style.width = `${active.scrollWidth}px`;
      bar.scrollLeft = active.scrollLeft;
      bar.style.display = "block";
      body.classList.add("has-global-hscroll");
    }

    wrap.addEventListener("mouseenter", () => {
      active = wrap;
      updateBar();
    });
    wrap.addEventListener("scroll", () => {
      if (active !== wrap) active = wrap;
      if (syncing) return;
      syncing = true;
      bar.scrollLeft = wrap.scrollLeft;
      syncing = false;
      updateBar();
    });

    bar.addEventListener("scroll", () => {
      if (!active) return;
      if (syncing) return;
      syncing = true;
      active.scrollLeft = bar.scrollLeft;
      syncing = false;
    });

    window.addEventListener("resize", updateBar);
    active = wrap;
    updateBar();
  }

  function setupTopXScroll() {
    const host = document.querySelector("[data-xscroll='opps']");
    const topBar = document.querySelector("[data-xscroll-top='opps']");
    if (!host || !topBar) return;
    const inner = topBar.querySelector(".xscroll-top__inner");
    if (!inner) return;
    let syncing = false;

    function updateTop() {
      const needs = host.scrollWidth > host.clientWidth + 1;
      if (!needs) {
        topBar.style.display = "none";
        return;
      }
      inner.style.width = `${host.scrollWidth}px`;
      topBar.scrollLeft = host.scrollLeft;
      topBar.style.display = "block";
    }

    host.addEventListener("scroll", () => {
      if (syncing) return;
      syncing = true;
      topBar.scrollLeft = host.scrollLeft;
      syncing = false;
    });
    topBar.addEventListener("scroll", () => {
      if (syncing) return;
      syncing = true;
      host.scrollLeft = topBar.scrollLeft;
      syncing = false;
    });
    window.addEventListener("resize", updateTop);
    updateTop();
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-edge-type]");
    if (!btn) return;
    e.preventDefault();
    const type = btn.getAttribute("data-edge-type") || "NONE";
    fetchEdgeTrades(type);
  });
  setupGlobalHScroll();
  setupTopXScroll();
  const oppsMode = localStorage.getItem("ps.opps.mode") || "terminal";
  const guided = document.querySelector("[data-opps-guided]");
  const table = document.querySelector("[data-cases-table]");
  if (guided) guided.style.display = oppsMode === "guided" ? "block" : "none";
  if (table) table.style.display = oppsMode === "guided" ? "none" : "block";
  document.querySelectorAll("[data-opps-mode]").forEach((b) => {
    b.classList.toggle("pill-ok", b.getAttribute("data-opps-mode") === oppsMode);
    b.classList.toggle("pill-muted", b.getAttribute("data-opps-mode") !== oppsMode);
  });
  renderOppsGuided();
  if (edgeTradesClose) {
    edgeTradesClose.addEventListener("click", (e) => {
      e.preventDefault();
      if (edgeTradesPanel) edgeTradesPanel.classList.add("hidden");
    });
  }
  document.addEventListener("mousemove", (e) => {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const btn = el && el.closest ? el.closest("button") : null;
    if (!btn || !btn.dataset || !btn.dataset.disabledReason) {
      if (disabledTipTarget) hideDisabledTip();
      return;
    }
    if (disabledTipTarget === btn) return;
    showDisabledTip(btn, btn.dataset.disabledReason);
  });
  document.addEventListener("mouseout", (e) => {
    if (!disabledTipTarget) return;
    if (!e.relatedTarget || !disabledTipTarget.contains(e.relatedTarget)) hideDisabledTip();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideExplain();
  });
  document.addEventListener("mouseover", handlePreviewEnter);
  document.addEventListener("focusin", handlePreviewEnter);
  document.addEventListener("mouseout", handlePreviewLeave);
  document.addEventListener("focusout", handlePreviewLeave);
  document.addEventListener("pointerdown", (e) => {
    const btn = e.target.closest("button[data-paper-action][data-case-id]");
    if (!btn) return;
    if (btn.getAttribute("data-guarded") === "1") {
      e.preventDefault();
      startGuardHold(btn);
    }
  });
  ["pointerup", "pointerleave", "pointercancel", "pointerout"].forEach((ev) => {
    document.addEventListener(ev, cancelGuardHold);
  });
  document.addEventListener("pointerdown", (e) => {
    const btn = e.target.closest(".batch-action");
    if (!btn) return;
    e.preventDefault();
    startBatchHold(btn);
  });
  ["pointerup", "pointerleave", "pointercancel", "pointerout"].forEach((ev) => {
    document.addEventListener(ev, cancelBatchHold);
  });
  schedule(pollCasesTop, 5000, () => casesErrors);
  schedule(refreshGuardRows, 5000, () => 0);
  schedule(fetchMicroPanel, 5000, () => microErrors);
  startPolling();

  async function forceRefreshNow() {
    if (forceRefreshBtn) {
      forceRefreshBtn.classList.remove("is-spinning");
      void forceRefreshBtn.offsetWidth;
      forceRefreshBtn.classList.add("is-spinning");
    }
    try {
      await Promise.all([
        fetchPing(),
        fetchHealth(),
        fetchExposure(),
        fetchEdgePnlReport(),
        fetchBookHealth(),
        fetchAgent(),
        pollCasesTop(),
      ]);
    } catch (e) {
      console.warn("Force refresh failed", e);
    }
  }

  if (forceRefreshBtn) {
    forceRefreshBtn.addEventListener("click", (e) => {
      e.preventDefault();
      forceRefreshNow();
    });
  }

  async function startAgent() {
    if (!agentStartBtn) return;
    agentStartBtn.disabled = true;
    try {
      const resp = await fetch("/agent/start", { method: "POST", headers: { "Accept": "application/json" } });
      if (!resp.ok) {
        showToast("Agent: старт не удался", "warn");
        return;
      }
      showToast("Agent: запущен", "resumed");
      await fetchAgent();
    } catch (e) {
      showToast("Agent: ошибка запуска", "warn");
    } finally {
      agentStartBtn.disabled = false;
    }
  }

  let agentStopTimer = null;
  let agentStopRaf = null;
  let agentStopStart = 0;
  const agentStopProgress = agentStopBtn ? agentStopBtn.querySelector(".agent-hold-progress") : null;

  function cancelAgentStopHold() {
    if (agentStopTimer) {
      clearTimeout(agentStopTimer);
      agentStopTimer = null;
    }
    if (agentStopRaf) {
      cancelAnimationFrame(agentStopRaf);
      agentStopRaf = null;
    }
    if (agentStopProgress) agentStopProgress.style.transform = "scaleX(0)";
    if (agentStopBtn) agentStopBtn.classList.remove("is-holding");
  }

  function startAgentStopHold() {
    if (!agentStopBtn || agentStopBtn.disabled) return;
    cancelAgentStopHold();
    agentStopStart = performance.now();
    agentStopBtn.classList.add("is-holding");
    const tick = (now) => {
      const pct = Math.min(1, (now - agentStopStart) / HOLD_MS);
      if (agentStopProgress) agentStopProgress.style.transform = `scaleX(${pct})`;
      if (pct < 1) agentStopRaf = requestAnimationFrame(tick);
    };
    agentStopRaf = requestAnimationFrame(tick);
    agentStopTimer = setTimeout(async () => {
      cancelAgentStopHold();
      try {
        const resp = await fetch("/agent/stop", { method: "POST", headers: { "Accept": "application/json" } });
        if (!resp.ok) {
          showToast("Agent: стоп не удался", "warn");
          return;
        }
        showToast("Agent: остановлен", "warn");
        await fetchAgent();
      } catch (e) {
        showToast("Agent: ошибка стопа", "warn");
      }
    }, HOLD_MS);
  }

  if (agentStartBtn) {
    agentStartBtn.addEventListener("click", (e) => {
      e.preventDefault();
      startAgent();
    });
  }

  if (agentStopBtn) {
    agentStopBtn.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      startAgentStopHold();
    });
    ["pointerup", "pointerleave", "pointercancel", "pointerout"].forEach((ev) => {
      agentStopBtn.addEventListener(ev, cancelAgentStopHold);
    });
  }
})();
