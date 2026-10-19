/**
 * app.js - Main Application State Machine & Entry Point for Three Kingdoms SLG.
 *
 * Implements:
 * - State machine (Title -> Setup -> Main -> Settlement -> GameOver)
 * - Numbered keyboard navigation (1..8, 0)
 * - API client (GET /api/state, POST /api/plan, GET /api/status, POST /api/estimate)
 * - 1-second polling during resolution phase
 * - Responsive UI bindings
 */

import { renderMap, CITY_NAMES, FACTION_INFO } from "./map.js";
import {
  renderCityInfo,
  renderOfficers,
  renderDispatch,
  renderSiege,
  renderWatchlist,
  renderChronicle,
  renderSettlement,
  renderGameOver,
  OFFICER_CATALOG,
  ingestRoster,
  ingestNarrative,
} from "./panels.js";

// One game per browser tab: the server keys games by this id (see server.py).
const SESSION_ID = (() => {
  try {
    let id = sessionStorage.getItem("slg_sid");
    if (!id) {
      id = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
      sessionStorage.setItem("slg_sid", id);
    }
    return id;
  } catch (err) {
    return "main";
  }
})();
const apiFetch = (url, opts = {}) =>
  fetch(url, { ...opts, headers: { ...(opts.headers || {}), "X-Session": SESSION_ID } });

class SLGApp {
  constructor() {
    this.screen = "title"; // 'title' | 'setup' | 'main'
    this.activeTab = "city"; // 'city' | 'officers' | 'dispatch' | 'siege' | 'watchlist' | 'chronicle' | 'settlement' | 'game_over'

    this.state = null; // Latest FactionView from /api/state
    this.status = null; // Latest status from /api/status
    this.selectedCityId = null;
    this.activeOfficerId = null;

    this.orders = []; // [{officer: id, action: str, params: {...}, cost: num}]
    this.nextCast = []; // Array of officer IDs, max 6
    this.chronicle = "";

    this.narrative = null; // story text for the chosen scenario + lord (/api/narrative)
    this.pollTimer = null;
    this.isResolving = false;
    this.resolveStartTime = null;

    this.initDOM();
    this.bindEvents();
    this.bindKeyboard();
  }

  initDOM() {
    this.dom = {
      screenTitle: document.getElementById("screenTitle"),
      screenSetup: document.getElementById("screenSetup"),
      screenMain: document.getElementById("screenMain"),

      // Title & Setup
      btnTitleNewGame: document.getElementById("btnTitleNewGame"),
      btnTitleHelp: document.getElementById("btnTitleHelp"),
      titleHelpBox: document.getElementById("titleHelpBox"),
      setupForm: document.getElementById("setupForm"),
      btnSetupStart: document.getElementById("btnSetupStart"),
      btnSetupBack: document.getElementById("btnSetupBack"),
      setupPreview: document.getElementById("setupPreview"),
      openingOverlay: document.getElementById("openingOverlay"),

      // Header Elements
      monarchPortraitImg: document.getElementById("monarchPortraitImg"),
      factionNameTitle: document.getElementById("factionNameTitle"),
      turnBadge: document.getElementById("turnBadge"),
      phaseBadge: document.getElementById("phaseBadge"),
      mCityCount: document.getElementById("mCityCount"),
      mTroopCount: document.getElementById("mTroopCount"),
      mGoldCount: document.getElementById("mGoldCount"),
      mFoodCount: document.getElementById("mFoodCount"),

      // Main Content Containers
      mapContainer: document.getElementById("mapContainer"),
      mapStatusText: document.getElementById("mapStatusText"),
      panelsContainer: document.getElementById("panelsContainer"),
      resolvingOverlay: document.getElementById("resolvingOverlay"),
      resolvingSeconds: document.getElementById("resolvingSeconds"),
      commandBarNav: document.getElementById("commandBarNav"),
    };
  }

  setScreen(newScreen) {
    this.screen = newScreen;
    this.dom.screenTitle.classList.toggle("active", newScreen === "title");
    this.dom.screenSetup.classList.toggle("active", newScreen === "setup");
    this.dom.screenMain.classList.toggle("active", newScreen === "main");
  }

  setActiveTab(newTab) {
    this.activeTab = newTab;

    // Update active state in bottom command bar
    this.dom.commandBarNav.querySelectorAll(".cmd-btn").forEach((btn) => {
      const tab = btn.getAttribute("data-tab");
      btn.classList.toggle("active", tab === newTab);
    });

    this.renderCurrentPanel();
  }

  bindEvents() {
    // Title buttons
    this.dom.btnTitleNewGame.addEventListener("click", () => this.setScreen("setup"));
    this.dom.btnTitleHelp.addEventListener("click", () => {
      const isVisible = this.dom.titleHelpBox.style.display !== "none";
      this.dom.titleHelpBox.style.display = isVisible ? "none" : "block";
    });

    // Setup buttons
    this.dom.btnSetupBack.addEventListener("click", () => this.setScreen("title"));
    this.dom.btnSetupStart.addEventListener("click", () => this.handleStartNewGame());
    this.dom.setupForm.addEventListener("change", (e) => {
      if (e.target.name === "setupScenario" || e.target.name === "setupFaction") this.refreshSetupPreview();
    });
    this.dom.btnTitleNewGame.addEventListener("click", () => this.refreshSetupPreview());

    // Command Bar buttons
    this.dom.commandBarNav.addEventListener("click", (e) => {
      const btn = e.target.closest(".cmd-btn");
      if (!btn) return;

      const tab = btn.getAttribute("data-tab");
      const action = btn.getAttribute("data-action");

      if (tab) {
        this.setActiveTab(tab);
      } else if (action === "submit") {
        this.handleSubmitPlan();
      } else if (action === "refresh") {
        this.fetchState();
      } else if (action === "menu") {
        if (confirm("是否要暫停推演並返回主選單？")) {
          this.stopPolling();
          this.setScreen("title");
        }
      }
    });
  }

  bindKeyboard() {
    document.addEventListener("keydown", (e) => {
      // Do not hijack typing inside form fields
      if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) {
        return;
      }

      const key = e.key;

      if (this.isOpeningOpen()) {
        if (["Enter", "Escape", "1", " "].includes(key)) {
          e.preventDefault();
          this.closeOpening();
        }
        return;
      }

      if (this.screen === "title") {
        if (key === "1") this.setScreen("setup");
        if (key === "2") {
          const isVisible = this.dom.titleHelpBox.style.display !== "none";
          this.dom.titleHelpBox.style.display = isVisible ? "none" : "block";
        }
      } else if (this.screen === "setup") {
        if (key === "1" || key === "Enter") this.handleStartNewGame();
        if (key === "0" || key === "Escape") this.setScreen("title");
      } else if (this.screen === "main") {
        switch (key) {
          case "1":
            this.setActiveTab("city");
            break;
          case "2":
            this.setActiveTab("officers");
            break;
          case "3":
            this.setActiveTab("dispatch");
            break;
          case "4":
            this.setActiveTab("siege");
            break;
          case "5":
            this.setActiveTab("watchlist");
            break;
          case "6":
            this.setActiveTab("chronicle");
            break;
          case "7":
            this.handleSubmitPlan();
            break;
          case "8":
            this.fetchState();
            break;
          case "0":
            if (confirm("返回主選單？")) {
              this.stopPolling();
              this.setScreen("title");
            }
            break;
          case "Enter":
            if (this.activeTab === "settlement") {
              this.setActiveTab("city");
            }
            break;
        }
      }
    });
  }

  async handleStartNewGame() {
    const scenario = document.querySelector('input[name="setupScenario"]:checked')?.value || "default";
    const faction = document.querySelector('input[name="setupFaction"]:checked')?.value || "faction_2";
    const aiMode = document.querySelector('input[name="setupAI"]:checked')?.value || "rule";

    try {
      const resp = await apiFetch("/api/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario,
          seed: 42,
          player_faction: faction,
          ai: {
            faction_1: aiMode,
            faction_2: aiMode,
            faction_3: aiMode,
          },
          turns: 30,
        }),
      });
      if (!resp.ok) {
        console.warn("Server /api/new error:", resp.status);
      }
    } catch (err) {
      console.warn("Could not reach /api/new, continuing offline mock mode:", err);
    }

    this.orders = [];
    this.chronicle = "";
    this.nextCast = [];

    await this.fetchNarrative(scenario, faction);
    await this.fetchState();
    await this.checkInitialStatus();
    this.setScreen("main");
    this.setActiveTab("city");
    this.showOpening();
  }

  // ---- Story text -------------------------------------------------------------------------
  async loadNarrative(scenario, faction) {
    try {
      const resp = await apiFetch(`/api/narrative?scenario=${encodeURIComponent(scenario)}&faction=${encodeURIComponent(faction)}`);
      return resp.ok ? await resp.json() : null;
    } catch (err) {
      console.warn("Could not load /api/narrative:", err);
      return null;
    }
  }

  async fetchNarrative(scenario, faction) {
    this.narrative = await this.loadNarrative(scenario, faction);
    ingestNarrative(this.narrative);
  }

  async refreshSetupPreview() {
    const scenario = document.querySelector('input[name="setupScenario"]:checked')?.value || "default";
    const faction = document.querySelector('input[name="setupFaction"]:checked')?.value || "faction_2";
    const n = await this.loadNarrative(scenario, faction);
    const box = this.dom.setupPreview;
    if (!box) return;
    box.textContent = "";
    if (!n) return;
    const o = n.opening;
    const head = document.createElement("div");
    const strong = document.createElement("strong");
    strong.textContent = `${n.lord.name}（${n.lord.title}）・${o.headline}`;
    const tone = document.createElement("span");
    tone.className = `tone-badge tone-${o.tone}`;
    tone.textContent = o.tone;
    head.append(strong, tone);
    const body = document.createElement("div");
    body.textContent = o.situation;
    box.append(head, body);
  }

  isOpeningOpen() {
    return !!this.dom.openingOverlay && this.dom.openingOverlay.style.display !== "none";
  }

  closeOpening() {
    this.dom.openingOverlay.style.display = "none";
    this.dom.openingOverlay.textContent = "";
  }

  showOpening() {
    const n = this.narrative;
    if (!n || !this.dom.openingOverlay) return;
    const el = (tag, cls, text) => {
      const e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text !== undefined) e.textContent = text;
      return e;
    };
    const card = el("div", "opening-card");
    const h = el("h2", "", n.opening.headline);
    h.id = "openingTitle";
    const tone = el("span", `tone-badge tone-${n.opening.tone}`, n.opening.tone);
    h.append(tone);
    card.append(h, el("div", "opening-sub", `${n.scenario.name}・${n.lord.name}（${n.lord.title}）`));
    card.append(el("p", "opening-lord", `${n.lord.intro}　「${n.lord.opening}」`));
    card.append(el("p", "", n.opening.situation));
    const ol = el("ol");
    n.opening.advice.forEach((a) => ol.append(el("li", "", a)));
    card.append(ol);
    const btn = el("button", "btn btn-primary btn-lg", "起兵（Enter）");
    btn.type = "button";
    btn.addEventListener("click", () => this.closeOpening());
    card.append(btn);
    this.dom.openingOverlay.textContent = "";
    this.dom.openingOverlay.append(card);
    this.dom.openingOverlay.style.display = "flex";
    btn.focus();
  }

  async checkInitialStatus() {
    try {
      const resp = await apiFetch("/api/status");
      if (!resp.ok) return;
      const status = await resp.json();
      this.status = status;
      if (status.phase === "resolving") {
        this.isResolving = true;
        this.resolveStartTime = Date.now();
        this.updateResolvingUI();
        this.startPolling();
      }
    } catch (err) {
      console.warn("Could not check initial status:", err);
    }
  }

  async fetchState() {
    try {
      const resp = await apiFetch("/api/state");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      this.state = data;
      ingestRoster(data);
      this.onStateLoaded();
    } catch (err) {
      console.error("Failed to load state from /api/state:", err);
    }
  }

  onStateLoaded() {
    if (!this.state) return;

    // Pick default selected city if not set
    const ownCities = this.state.cities || [];
    if (!this.selectedCityId || !ownCities.some((c) => c.id === this.selectedCityId)) {
      this.selectedCityId = ownCities.length > 0 ? ownCities[0].id : "luoyang";
    }

    // Pick default active officer if not set
    const cast = this.state.cast || [];
    if (!this.activeOfficerId || !cast.some((c) => c.id === this.activeOfficerId)) {
      this.activeOfficerId = cast.length > 0 ? cast[0].id : null;
    }

    // Initialize nextCast spotlight to current cast if empty
    if (this.nextCast.length === 0) {
      this.nextCast = cast.map((c) => c.id).slice(0, 6);
    }

    this.updateHeader();
    this.renderMap();
    this.renderCurrentPanel();
  }

  updateHeader() {
    if (!this.state) return;

    const fId = this.state.faction_id || "faction_2";
    const fName = this.state.faction_name || "劉備";
    this.dom.factionNameTitle.textContent = `${fName} 軍`;

    // Portrait image mapping
    if (fId === "faction_1") {
      this.dom.monarchPortraitImg.src = "./assets/portraits/lord_cao_cao.png";
    } else if (fId === "faction_3") {
      this.dom.monarchPortraitImg.src = "./assets/portraits/lord_sun_quan.png";
    } else {
      this.dom.monarchPortraitImg.src = "./assets/portraits/lord_liu_bei.png";
    }
    this.dom.monarchPortraitImg.onerror = () => { this.dom.monarchPortraitImg.onerror = null; this.dom.monarchPortraitImg.src = "./assets/portrait_default.svg"; };

    // Turn
    const turn = this.state.turn !== undefined ? this.state.turn : 0;
    const cal = this.state.calendar;
    this.dom.turnBadge.textContent = cal ? `${cal.label}・第 ${turn} 回合` : `第 ${turn} 回合`;
    this.dom.turnBadge.title = cal ? cal.flavor : "";

    // Metrics summary
    const cities = this.state.cities || [];
    const totalTroops = cities.reduce((acc, c) => acc + (c.troops || 0), 0);
    const totalGold = cities.reduce((acc, c) => acc + (c.gold || 0), 0);
    const totalFood = cities.reduce((acc, c) => acc + (c.food || 0), 0);

    this.dom.mCityCount.textContent = cities.length;
    this.dom.mTroopCount.textContent = totalTroops;
    this.dom.mGoldCount.textContent = totalGold;
    this.dom.mFoodCount.textContent = totalFood;

    // Phase Badge & Resolving State
    this.updateResolvingUI();
  }

  updateResolvingUI() {
    const elapsed = this.resolveStartTime ? Math.floor((Date.now() - this.resolveStartTime) / 1000) : 0;
    if (this.dom.resolvingOverlay) {
      this.dom.resolvingOverlay.style.display = this.isResolving ? "flex" : "none";
    }
    if (this.dom.resolvingSeconds) {
      this.dom.resolvingSeconds.textContent = elapsed;
    }
    if (this.isResolving) {
      this.dom.phaseBadge.className = "phase-indicator-pill phase-resolving";
      this.dom.phaseBadge.innerHTML = `<span class="badge-spinner" aria-hidden="true"></span>各勢力正在決策… (${elapsed}秒)`;
    } else {
      this.dom.phaseBadge.className = "phase-indicator-pill phase-awaiting";
      this.dom.phaseBadge.textContent = "● 等待軍令輸入";
    }
  }

  renderMap() {
    if (!this.state) return;
    renderMap(
      this.dom.mapContainer,
      this.state,
      this.selectedCityId,
      (cityId) => {
        this.selectedCityId = cityId;
        this.renderMap();
        if (this.activeTab === "city") {
          this.renderCurrentPanel();
        }
      }
    );
  }

  renderCurrentPanel() {
    if (!this.state) return;

    const container = this.dom.panelsContainer;

    switch (this.activeTab) {
      case "city":
        renderCityInfo(
          container,
          this.state,
          this.selectedCityId,
          (targetCityId) => {
            this.selectedCityId = targetCityId;
            this.renderMap();
            this.renderCurrentPanel();
          }
        );
        break;

      case "officers":
        renderOfficers(container, this.state, this.orders, (officerId) => {
          this.activeOfficerId = officerId;
          this.setActiveTab("dispatch");
        });
        break;

      case "dispatch":
        renderDispatch(
          container,
          this.state,
          this.orders,
          this.activeOfficerId,
          (newActiveId) => {
            this.activeOfficerId = newActiveId;
            this.renderCurrentPanel();
          },
          (newOrder) => {
            // Rule: Each officer at most 1 order!
            this.orders = this.orders.filter((ord) => ord.officer !== newOrder.officer);
            this.orders.push(newOrder);
            this.renderCurrentPanel();
          },
          (officerIdToDelete) => {
            this.orders = this.orders.filter((ord) => ord.officer !== officerIdToDelete);
            this.renderCurrentPanel();
          }
        );
        break;

      case "siege":
        renderSiege(
          container,
          this.state,
          this.orders,
          (newOrder) => {
            this.orders = this.orders.filter((ord) => ord.officer !== newOrder.officer);
            this.orders.push(newOrder);
            this.setActiveTab("dispatch");
          },
          async (city, target, troops) => {
            return this.requestEstimate(city, target, troops);
          }
        );
        break;

      case "watchlist":
        renderWatchlist(
          container,
          this.state,
          this.nextCast,
          (officerId, isChecked) => {
            if (isChecked) {
              if (this.nextCast.length < 6 && !this.nextCast.includes(officerId)) {
                this.nextCast.push(officerId);
              }
            } else {
              this.nextCast = this.nextCast.filter((id) => id !== officerId);
            }
            this.renderCurrentPanel();
          },
          () => {
            // Reset to current cast
            this.nextCast = (this.state.cast || []).map((c) => c.id).slice(0, 6);
            this.renderCurrentPanel();
          }
        );
        break;

      case "chronicle":
        renderChronicle(container, this.chronicle, (newText) => {
          this.chronicle = newText;
        });
        break;

      case "settlement":
        renderSettlement(container, this.status || {}, () => {
          this.setActiveTab("city");
        });
        break;

      case "game_over":
        renderGameOver(container, this.status || {}, this.state, () => {
          this.setScreen("title");
        });
        break;
    }
  }

  async requestEstimate(city, target, troops) {
    try {
      const resp = await apiFetch("/api/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city, target, troops }),
      });
      if (resp.ok) return await resp.json();
    } catch (e) {
      console.warn("Estimate failed, falling back to 0.5:", e);
    }
    return { ratio: 0.5 };
  }

  async handleSubmitPlan() {
    if (this.isResolving) {
      alert("全境推演解析中，請稍候...");
      return;
    }

    // Build payload strictly adhering to specification
    const payload = {
      orders: this.orders.map((ord) => ({
        officer: ord.officer,
        action: ord.action,
        params: ord.params || {},
      })),
      chronicle: this.chronicle || "全軍安守本分，修明政理。",
      next_cast: this.nextCast.length > 0 ? this.nextCast : (this.state?.cast || []).map((c) => c.id).slice(0, 6),
    };

    try {
      this.isResolving = true;
      this.resolveStartTime = Date.now();
      this.updateResolvingUI();

      const resp = await apiFetch("/api/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        console.warn("POST /api/plan returned non-200:", resp.status);
      }

      this.startPolling();
    } catch (err) {
      console.error("Failed to submit plan:", err);
      this.isResolving = false;
      this.resolveStartTime = null;
      this.updateResolvingUI();
    }
  }

  startPolling() {
    this.stopPolling();
    this.pollTimer = setInterval(async () => {
      if (this.isResolving) {
        this.updateResolvingUI();
      }
      await this.pollStatus();
    }, 1000);
  }

  stopPolling() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  async pollStatus() {
    try {
      const resp = await apiFetch("/api/status");
      if (!resp.ok) return;

      const status = await resp.json();
      this.status = status;

      if (status.winner) {
        this.stopPolling();
        this.isResolving = false;
        this.resolveStartTime = null;
        this.updateResolvingUI();
        this.updateHeader();
        this.setActiveTab("game_over");
        return;
      }

      if (status.phase === "awaiting_input") {
        this.stopPolling();
        this.isResolving = false;
        this.resolveStartTime = null;
        this.updateResolvingUI();
        // Turn completed: clear previous orders for new turn
        this.orders = [];
        this.updateHeader();
        await this.fetchState();
        // Show settlement report panel
        this.setActiveTab("settlement");
      }
    } catch (err) {
      console.warn("Polling /api/status error:", err);
    }
  }
}

// Instantiate and start app on DOM ready
window.addEventListener("DOMContentLoaded", () => {
  window.slgApp = new SLGApp();
});
