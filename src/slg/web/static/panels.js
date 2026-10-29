/**
 * panels.js - Tactical Information Panels for Three Kingdoms SLG.
 *
 * Implements:
 * 1. City Info Panel (城池情報)
 * 2. Officers List & Stats Panel (武將列表 / 能力表)
 * 3. Dispatch Panel (派遣面板: 嚴格依照 legal_structured，同城預算顯示)
 * 4. Siege Panel (攻城面板: 估算勝率，目標選擇)
 * 5. Watchlist Panel (關注名單: next_cast 勾選上限6，警示色)
 * 6. Chronicle Panel (奏摺起草: ≤ 300字)
 * 7. Settlement Panel (回合結算: feedback 醒目顯示，事件逐條呈現)
 * 8. Game Over Panel (結束畫面: 統計勝負)
 */

import { CITY_NAMES, FACTION_INFO } from "./map.js";

// Comprehensive officer encyclopedia (42 officers across 3 factions)
// Own-faction officers only, filled from /api/state `roster_info` (never hard-code other factions: fog of war).
export const portraitUrl = (id) => `./assets/portraits/${id}.png`;
export const portraitImg = (id, cls = "mini-portrait") =>
  `<img class="${cls}" src="${portraitUrl(id)}" alt="" loading="lazy" onerror="this.style.display='none'">`;
export const NARRATIVE = { officers: {}, cities: {} };
export function ingestNarrative(n) {
  NARRATIVE.officers = (n && n.officers) || {};
  NARRATIVE.cities = (n && n.cities) || {};
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const OFFICER_CATALOG = {};
export const NAME_TO_ID = {};
export function ingestRoster(state) {
  for (const k of Object.keys(OFFICER_CATALOG)) delete OFFICER_CATALOG[k];
  for (const k of Object.keys(NAME_TO_ID)) delete NAME_TO_ID[k];
  Object.values(state?.roster_info || {}).forEach((list) =>
    (list || []).forEach((o) => {
      OFFICER_CATALOG[o.id] = { ...o, faction: state.faction_id };
      NAME_TO_ID[o.name] = o.id;
    })
  );
}

export const ACTION_ICONS = { develop_agri: "develop", develop_commerce: "develop", develop_defense: "defend", recruit: "recruit", move: "march", siege: "siege", rest: "defend" };
export const actionIcon = (k) => ACTION_ICONS[k] ? `<img class="action-icon" src="./assets/art/icons/${ACTION_ICONS[k]}.svg" alt="">` : "";

export const ACTION_NAMES = {
  develop_agri: "開墾農業",
  develop_commerce: "發展商業",
  develop_defense: "構築城防",
  recruit: "招募新兵",
  move: "將領調度",
  siege: "出征攻城",
  rest: "休養生息",
};

/**
 * Helper to get live or catalog officer data
 */
export function getOfficerData(officerId, state) {
  const castOfficer = (state?.cast || []).find((c) => c.id === officerId);
  if (castOfficer) return { ...castOfficer, inCast: true };

  const catalog = OFFICER_CATALOG[officerId];
  if (catalog) return { ...catalog, neglect: 0, inCast: false };

  return {
    id: officerId,
    name: officerId,
    city: "unknown",
    politics: 50,
    war: 50,
    leadership: 50,
    loyalty: 80,
    neglect: 0,
    inCast: false,
  };
}

/**
 * 1. Render City Info Panel (城池情報)
 */
export function renderCityInfo(container, state, selectedCityId, onCitySelect) {
  const ownCity = (state.cities || []).find((c) => c.id === selectedCityId);
  const frontierCity = (state.frontier || []).find((f) => f.id === selectedCityId);
  const cityName = CITY_NAMES[selectedCityId] || selectedCityId;

  let html = `<div class="panel-content city-info-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【城池情報】${cityName}</h3>
    <span class="city-id-badge">${selectedCityId}</span>
  </div>`;
  const lore = NARRATIVE.cities[selectedCityId];
  if (lore) html += `<div class="city-blurb"><span class="flavor">${esc(lore.flavor)}</span>${esc(lore.blurb)}</div>`;

  if (ownCity) {
    const fInfo = FACTION_INFO[state.faction_id] || FACTION_INFO.faction_2;
    html += `
      <div class="city-badge-bar own-badge">
        <span class="badge badge-own">[${fInfo.tag}] 我方所屬領地</span>
      </div>

      <div class="stat-grid">
        <div class="stat-item"><span class="stat-label">城池農業：</span><span class="stat-val highlight">${ownCity.agri}</span></div>
        <div class="stat-item"><span class="stat-label">城池商業：</span><span class="stat-val highlight">${ownCity.commerce}</span></div>
        <div class="stat-item"><span class="stat-label">城防強度：</span><span class="stat-val highlight">${ownCity.defense}</span></div>
        <div class="stat-item"><span class="stat-label">駐留兵力：</span><span class="stat-val troop-val">${ownCity.troops}</span></div>
        <div class="stat-item"><span class="stat-label">庫存金錢：</span><span class="stat-val gold-val">${ownCity.gold}</span></div>
        <div class="stat-item"><span class="stat-label">儲備軍糧：</span><span class="stat-val food-val">${ownCity.food}</span></div>
      </div>

      <div class="section-sub-block">
        <h4 class="sub-block-title">駐紮武將名冊</h4>
        <div class="stationed-officers-list">
    `;

    // Stationed officers from cast
    const castInCity = (state.cast || []).filter((o) => o.city === selectedCityId);
    // Stationed officers from roster
    const rosterInCity = (state.roster && state.roster[selectedCityId]) || [];

    if (castInCity.length === 0 && rosterInCity.length === 0) {
      html += `<div class="empty-notice">此城目前無駐紮武將。</div>`;
    } else {
      castInCity.forEach((o) => {
        html += `<span class="officer-pill cast-pill">${portraitImg(o.id)} ★ ${o.name} <span class="tag-cast">[焦點]</span></span>`;
      });
      rosterInCity.forEach((name) => {
        html += `<span class="officer-pill roster-pill">${name} <span class="tag-roster">[留守/自動]</span></span>`;
      });
    }

    html += `
        </div>
      </div>

      <div class="section-sub-block">
        <h4 class="sub-block-title">鄰接城池與疆界</h4>
        <div class="neighbors-list">
    `;

    const neighbors = ownCity.neighbors || [];
    neighbors.forEach((nbr) => {
      const [nid, owner] = nbr.split(":");
      const nName = CITY_NAMES[nid] || nid;
      const isFriend = owner === state.faction_id;
      html += `
        <button class="neighbor-btn ${isFriend ? "friend" : "enemy"}" data-city="${nid}">
          ${nName} ${isFriend ? "(友軍)" : "(前線敵境)"}
        </button>
      `;
    });

    html += `
        </div>
      </div>
    `;
  } else if (frontierCity) {
    const ownerInfo = FACTION_INFO[frontierCity.owner] || { tag: "敵", color: "#ef4444" };
    html += `
      <div class="city-badge-bar enemy-badge">
        <span class="badge badge-frontier">[${ownerInfo.tag}] 前線敵境</span>
      </div>

      <div class="alert-box info-alert">
        <strong>【斥候前線偵察】</strong>
        <p>因戰爭迷霧阻隔，非我方城池僅能探測兵力與防禦工事，內政、金錢與軍糧情資遮蔽。</p>
      </div>

      <div class="stat-grid">
        <div class="stat-item"><span class="stat-label">所屬勢力：</span><span class="stat-val">${ownerInfo.name || frontierCity.owner}</span></div>
        <div class="stat-item"><span class="stat-label">守備兵力：</span><span class="stat-val troop-val">${frontierCity.troops}</span></div>
        <div class="stat-item"><span class="stat-label">城防強度：</span><span class="stat-val highlight">${frontierCity.defense}</span></div>
        <div class="stat-item"><span class="stat-label">內政情資：</span><span class="stat-val text-muted">【迷霧遮蔽】</span></div>
      </div>

      <div class="section-sub-block">
        <h4 class="sub-block-title">鄰接我方防線城池</h4>
        <div class="neighbors-list">
    `;

    (frontierCity.adjacent_to || []).forEach((aid) => {
      const aName = CITY_NAMES[aid] || aid;
      html += `<button class="neighbor-btn friend" data-city="${aid}">${aName} (我方基地)</button>`;
    });

    html += `</div></div>`;
  } else {
    // Fog of war
    html += `
      <div class="city-badge-bar fog-badge">
        <span class="badge badge-fog">[？] 戰略迷霧遮蔽</span>
      </div>

      <div class="alert-box fog-alert">
        <strong>【全境迷霧覆蓋】</strong>
        <p>此城池非鄰接前線，斥候探子無法滲透。城內兵馬、防務、內政一切未明。</p>
      </div>
    `;
  }

  html += `</div>`;
  container.innerHTML = html;

  // Neighbor button click handlers
  container.querySelectorAll(".neighbor-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetCid = btn.getAttribute("data-city");
      if (targetCid && onCitySelect) {
        onCitySelect(targetCid);
      }
    });
  });
}

/**
 * 2. Render Officers List & Stats Panel (武將列表 / 能力表)
 */
export function renderOfficers(container, state, orders, onGoDispatch) {
  let html = `<div class="panel-content officers-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【將領名冊與能力表】</h3>
    <span class="officers-count">焦點名單：${(state.cast || []).length} / 6 人</span>
  </div>`;

  html += `
    <div class="table-scroll-container">
      <table class="data-table officers-table">
        <thead>
          <tr>
            <th>武將</th>
            <th>駐地</th>
            <th>統率</th>
            <th>武力</th>
            <th>政治</th>
            <th>忠誠</th>
            <th>冷落</th>
            <th>當前軍令</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
  `;

  (state.cast || []).forEach((o) => {
    const assignedOrder = (orders || []).find((ord) => ord.officer === o.id);
    const cityName = CITY_NAMES[o.city] || o.city;

    let loyBadge = `<span class="badge badge-good">${o.loyalty}</span>`;
    if (o.loyalty < 50) {
      loyBadge = `<span class="badge badge-danger" title="忠誠過低，極易違令或叛變！">${o.loyalty} (危)</span>`;
    } else if (o.loyalty < 80) {
      loyBadge = `<span class="badge badge-warning" title="忠誠動搖">${o.loyalty} (警)</span>`;
    }

    let negBadge = `<span class="badge badge-neutral">${o.neglect}</span>`;
    if (o.neglect >= 4) {
      negBadge = `<span class="badge badge-danger" title="冷落達到警示值，可能陳情或被策反！">${o.neglect} (危)</span>`;
    }

    let orderDesc = `<span class="text-muted">待命 (休息)</span>`;
    if (assignedOrder) {
      const actName = ACTION_NAMES[assignedOrder.action] || assignedOrder.action;
      orderDesc = `<strong class="order-assigned">${actName}</strong>`;
    }

    html += `
      <tr>
        <td class="bold-name">★ ${o.name}</td>
        <td>${cityName}</td>
        <td class="stat-cell">${o.leadership}</td>
        <td class="stat-cell">${o.war}</td>
        <td class="stat-cell">${o.politics}</td>
        <td>${loyBadge}</td>
        <td>${negBadge}</td>
        <td>${orderDesc}</td>
        <td>
          <button class="btn btn-sm btn-dispatch-jump" data-officer="${o.id}">
            派令
          </button>
        </td>
      </tr>
    `;
  });

  html += `
        </tbody>
      </table>
    </div>

    <div class="section-sub-block">
      <h4 class="sub-block-title">【留守代管武將（由規則 AI 自動指派）】</h4>
      <div class="roster-grid">
  `;

  let totalRoster = 0;
  if (state.roster) {
    Object.entries(state.roster).forEach(([cid, names]) => {
      const cName = CITY_NAMES[cid] || cid;
      (names || []).forEach((name) => {
        totalRoster++;
        const offId = NAME_TO_ID[name];
        const catalog = offId ? OFFICER_CATALOG[offId] : null;
        const pol = catalog ? catalog.politics : 50;
        const war = catalog ? catalog.war : 50;
        const ldr = catalog ? catalog.leadership : 50;

        html += `
          <div class="roster-card">
            <div class="roster-card-header">
              <span class="roster-name">${name}</span>
              <span class="roster-city">${cName}</span>
            </div>
            <div class="roster-card-stats">
              統 ${ldr} | 武 ${war} | 政 ${pol}
            </div>
            <div class="roster-card-badge">留守代管中</div>
          </div>
        `;
      });
    });
  }

  if (totalRoster === 0) {
    html += `<div class="empty-notice">目前無留守代管武將。</div>`;
  }

  html += `</div></div>`;

  // Biographies of our own officers (static history text; own faction only, so nothing leaks)
  const ownIds = [...new Set([...(state.cast || []).map((o) => o.id), ...Object.keys(OFFICER_CATALOG)])];
  const bios = ownIds.filter((id) => NARRATIVE.officers[id]);
  if (bios.length) {
    html += `<div class="section-sub-block bio-list"><h4 class="sub-block-title">【武將傳略】</h4>`;
    bios.forEach((id) => {
      const b = NARRATIVE.officers[id];
      html += `<details><summary>${portraitImg(id)} ${esc(b.name)}<span class="bio-title">${esc(b.title)}</span><span class="bio-tag">${esc(b.tag)}</span></summary>
        <p>${esc(b.bio)}</p><p class="bio-quote">「${esc(b.quote)}」</p>${b.tie ? `<p class="bio-tie">交遊：${esc(b.tie)}</p>` : ""}</details>`;
    });
    html += `</div>`;
  }
  html += `</div>`;
  container.innerHTML = html;

  // Jump to dispatch handlers
  container.querySelectorAll(".btn-dispatch-jump").forEach((btn) => {
    btn.addEventListener("click", () => {
      const oid = btn.getAttribute("data-officer");
      if (oid && onGoDispatch) {
        onGoDispatch(oid);
      }
    });
  });
}

/**
 * 3. Render Dispatch Panel (派遣面板)
 * STRICT RULE: Only cast officers, legal actions and params ONLY from legal_structured.
 * Frontend MUST NOT calculate any rules!
 * Shows same-city budget preview.
 */
export function renderDispatch(
  container,
  state,
  orders,
  activeOfficerId,
  onSetActiveOfficer,
  onAddOrder,
  onDeleteOrder
) {
  const cast = state.cast || [];
  if (cast.length === 0) {
    container.innerHTML = `<div class="panel-content"><p class="empty-notice">名單中無焦點武將。</p></div>`;
    return;
  }

  let selectedOfficer = cast.find((o) => o.id === activeOfficerId) || cast[0];
  const officerCity = (state.cities || []).find((c) => c.id === selectedOfficer.city);
  const cityName = CITY_NAMES[selectedOfficer.city] || selectedOfficer.city;
  const cityGold = officerCity ? officerCity.gold : 0;

  // Calculate same-city budget
  const cityOrdersCost = (orders || []).reduce((acc, ord) => {
    const oData = cast.find((c) => c.id === ord.officer);
    if (oData && oData.city === selectedOfficer.city) {
      return acc + (ord.cost || 0);
    }
    return acc;
  }, 0);
  const remainingGold = cityGold - cityOrdersCost;

  let html = `<div class="panel-content dispatch-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【派遣軍令 · 決策部署】</h3>
    <span class="orders-counter">已規劃軍令：${orders.length} / ${cast.length}</span>
  </div>`;

  // 1. Officer Selection Bar (Only cast officers!)
  html += `<div class="officer-select-bar" role="tablist" aria-label="選擇受令武將">`;
  cast.forEach((o) => {
    const hasOrder = (orders || []).some((ord) => ord.officer === o.id);
    const isCurrent = o.id === selectedOfficer.id;
    html += `
      <button class="officer-tab-btn ${isCurrent ? "active" : ""} ${hasOrder ? "has-order" : ""}"
              data-officer="${o.id}" role="tab" aria-selected="${isCurrent}">
        ${portraitImg(o.id)}${hasOrder ? "✓" : "○"} ${o.name}
      </button>
    `;
  });
  html += `</div>`;

  // 2. Selected Officer Details & Same-City Budget
  html += `
    <div class="officer-brief-card">
      <div class="officer-brief-main">
        <h4 class="officer-name">★ ${selectedOfficer.name}</h4>
        <span class="officer-loc">駐守於：${cityName}</span>
        <span class="brief-stats">統 ${selectedOfficer.leadership} | 武 ${selectedOfficer.war} | 政 ${selectedOfficer.politics} | 忠 ${selectedOfficer.loyalty}</span>
      </div>
      <div class="city-budget-box ${remainingGold < 0 ? "budget-overdrawn" : ""}">
        <div class="budget-title">【${cityName} 庫存金錢預算】</div>
        <div class="budget-row">
          <span>原庫存金：<strong>${cityGold}</strong></span>
          <span>已規劃花費：<strong>${cityOrdersCost}</strong></span>
          <span>預計剩餘金：<strong class="${remainingGold < 0 ? "text-danger" : "text-success"}">${remainingGold}</strong></span>
        </div>
        ${
          remainingGold < 0
            ? `<div class="budget-warn">⚠️ 提醒：同城命令花費超出城池現有黃金，引擎驗證時可能駁回超支軍令！</div>`
            : ""
        }
      </div>
    </div>
  `;

  // 3. Legal Actions Form (strictly from legal_structured)
  const legalList = selectedOfficer.legal_structured || [];
  const existingOrder = (orders || []).find((ord) => ord.officer === selectedOfficer.id);

  html += `
    <div class="actions-form-box">
      <h4 class="form-title">合法軍令選項（由規則引擎提供，請選擇行動與參數）：</h4>
      <div class="action-items-list" id="dispatchActionList">
  `;

  legalList.forEach((la, idx) => {
    const actKey = la.action;
    const isActSelected = existingOrder ? existingOrder.action === actKey : idx === 0;
    const actChinese = ACTION_NAMES[actKey] || actKey;

    html += `
      <div class="action-card ${isActSelected ? "selected" : ""}" data-action="${actKey}" data-cost="${la.cost || 0}">
        <div class="action-card-header">
          <label class="action-radio-label">
            <input type="radio" name="selectedAction" value="${actKey}" ${isActSelected ? "checked" : ""}>
            <span class="action-name">${actionIcon(actKey)}${actChinese} (${actKey})</span>
          </label>
          <span class="action-cost-badge">花費: ${la.cost || 0} 金</span>
        </div>
        <div class="action-note">${la.note ? `說明: ${la.note}` : ""}</div>
    `;

    // Render siege odds if action is siege
    if (actKey === "siege" && selectedOfficer.siege_odds) {
      html += `<div class="siege-odds-preview"><strong>偵察勝率估算：</strong>`;
      Object.entries(selectedOfficer.siege_odds).forEach(([tCity, odds]) => {
        const tName = CITY_NAMES[tCity] || tCity;
        html += `<span class="odds-pill">${tName}: ${(odds * 100).toFixed(0)}%</span> `;
      });
      html += `</div>`;
    }

    // Parameters inputs (strictly from la.params)
    const paramKeys = Object.keys(la.params || {});
    if (paramKeys.length > 0) {
      html += `<div class="action-params-box" data-action="${actKey}">`;
      paramKeys.forEach((pName) => {
        const spec = la.params[pName];
        const existingVal = existingOrder && existingOrder.action === actKey ? existingOrder.params?.[pName] : undefined;

        if (spec.choices) {
          // Discrete choice parameter
          html += `
            <div class="param-row">
              <label class="param-label">${pName === "to" ? "目的地" : pName}：</label>
              <select class="param-input-choice" name="param_${actKey}_${pName}">
          `;
          spec.choices.forEach((choice) => {
            const label = CITY_NAMES[choice] ? `${CITY_NAMES[choice]} (${choice})` : choice;
            const isChoiceSelected = existingVal !== undefined ? existingVal === choice : false;
            html += `<option value="${choice}" ${isChoiceSelected ? "selected" : ""}>${label}</option>`;
          });
          html += `</select></div>`;
        } else if (spec.min !== undefined && spec.max !== undefined) {
          // Numeric range parameter
          const min = spec.min;
          const max = spec.max;
          const step = spec.step || 1;
          const val = existingVal !== undefined ? existingVal : min;

          html += `
            <div class="param-row param-range-row">
              <label class="param-label">${pName === "troops" ? "出征/招募兵力" : pName}：</label>
              <div class="range-controls">
                <input type="range" class="param-range-slider"
                       name="param_${actKey}_${pName}_slider"
                       min="${min}" max="${max}" step="${step}" value="${val}">
                <input type="number" class="param-number-input"
                       name="param_${actKey}_${pName}"
                       min="${min}" max="${max}" step="${step}" value="${val}">
                <span class="range-bounds-text">(${min} ~ ${max}，間隔 ${step})</span>
              </div>
            </div>
          `;
        }
      });
      html += `</div>`;
    }

    html += `</div>`;
  });

  html += `
      </div>
      <div class="form-btn-row">
        <button id="btnAddDispatchOrder" class="btn btn-primary btn-lg">
          ${existingOrder ? "更新此將領軍令" : "加入軍令清單"}
        </button>
      </div>
    </div>
  `;

  // 4. Current Orders List
  html += `
    <div class="section-sub-block orders-list-block">
      <h4 class="sub-block-title">本回合已登錄軍令清單（每位將領最多一道軍令）</h4>
      <div class="orders-summary-table-wrap">
  `;

  if (orders.length === 0) {
    html += `<div class="empty-notice">尚無任何軍令。未下令之關注武將將預設為休養生息。</div>`;
  } else {
    html += `
      <table class="data-table orders-table">
        <thead>
          <tr>
            <th>受令武將</th>
            <th>駐地</th>
            <th>行動</th>
            <th>參數</th>
            <th>花費</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
    `;

    orders.forEach((ord) => {
      const oData = cast.find((c) => c.id === ord.officer) || getOfficerData(ord.officer, state);
      const cName = CITY_NAMES[oData.city] || oData.city;
      const actCh = ACTION_NAMES[ord.action] || ord.action;
      let paramStr = "-";
      if (ord.params && Object.keys(ord.params).length > 0) {
        paramStr = Object.entries(ord.params)
          .map(([k, v]) => `${k}=${CITY_NAMES[v] || v}`)
          .join(", ");
      }

      html += `
        <tr>
          <td class="bold-name">${oData.name}</td>
          <td>${cName}</td>
          <td><span class="badge badge-act">${actCh}</span></td>
          <td class="param-desc">${paramStr}</td>
          <td class="gold-val">${ord.cost || 0} 金</td>
          <td>
            <button class="btn btn-danger btn-sm btn-delete-order" data-officer="${ord.officer}">
              刪除
            </button>
          </td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
  }

  html += `</div></div></div>`;
  container.innerHTML = html;

  // Sync sliders and number inputs
  container.querySelectorAll(".param-range-slider").forEach((slider) => {
    const numInput = slider.parentElement.querySelector(".param-number-input");
    if (numInput) {
      slider.addEventListener("input", () => {
        numInput.value = slider.value;
      });
      numInput.addEventListener("input", () => {
        slider.value = numInput.value;
      });
    }
  });

  // Switch active officer tab
  container.querySelectorAll(".officer-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const oid = btn.getAttribute("data-officer");
      if (oid && onSetActiveOfficer) {
        onSetActiveOfficer(oid);
      }
    });
  });

  // Action card selection radio toggle
  container.querySelectorAll(".action-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) return;
      const radio = card.querySelector("input[type='radio']");
      if (radio) {
        radio.checked = true;
        container.querySelectorAll(".action-card").forEach((c) => c.classList.remove("selected"));
        card.classList.add("selected");
      }
    });
  });

  // Add / Update order click
  const btnAdd = container.querySelector("#btnAddDispatchOrder");
  if (btnAdd) {
    btnAdd.addEventListener("click", () => {
      const selectedRadio = container.querySelector("input[name='selectedAction']:checked");
      if (!selectedRadio) return;

      const actKey = selectedRadio.value;
      const la = legalList.find((item) => item.action === actKey);
      if (!la) return;

      // Extract parameters
      const params = {};
      Object.keys(la.params || {}).forEach((pName) => {
        const choiceEl = container.querySelector(`[name="param_${actKey}_${pName}"]`);
        if (choiceEl) {
          const val = choiceEl.value;
          params[pName] = isNaN(Number(val)) || choiceEl.tagName === "SELECT" ? val : Number(val);
        }
      });

      // Calculate cost
      let cost = la.cost || 0;
      if (actKey === "recruit" && params.troops) {
        cost = Number(params.troops);
      }

      onAddOrder({
        officer: selectedOfficer.id,
        action: actKey,
        params,
        cost,
      });
    });
  }

  // Delete order handlers
  container.querySelectorAll(".btn-delete-order").forEach((btn) => {
    btn.addEventListener("click", () => {
      const oid = btn.getAttribute("data-officer");
      if (oid && onDeleteOrder) {
        onDeleteOrder(oid);
      }
    });
  });
}

/**
 * 4. Render Siege Panel (攻城面板)
 */
export function renderSiege(container, state, orders, onAddOrder, onEstimateOdds) {
  const cast = state.cast || [];
  // Find cast officers that can siege
  const siegeCapableOfficers = cast.filter((o) =>
    (o.legal_structured || []).some((la) => la.action === "siege")
  );

  let html = `<div class="panel-content siege-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【攻城戰略部署】</h3>
    <span class="badge badge-frontier">前線軍事行動</span>
  </div>`;

  if (siegeCapableOfficers.length === 0) {
    html += `
      <div class="alert-box info-alert">
        <strong>目前無可行攻城軍令：</strong>
        <p>名單中的焦點武將皆未駐紮於前線，或駐紮城池剩餘兵力未達出征門檻（需保留至少 100 守備守軍）。</p>
      </div>
    `;
    container.innerHTML = html;
    return;
  }

  const selectedOfficer = siegeCapableOfficers[0];
  const siegeAction = selectedOfficer.legal_structured.find((la) => la.action === "siege");
  const toChoices = siegeAction.params.to.choices || [];
  const troopsMin = siegeAction.params.troops.min || 500;
  const troopsMax = siegeAction.params.troops.max || 1000;
  const troopsStep = siegeAction.params.troops.step || 100;

  html += `
    <div class="siege-form-card">
      <div class="form-row">
        <label class="form-label">出征主將：</label>
        <select id="siegeOfficerSelect" class="form-select">
  `;

  siegeCapableOfficers.forEach((o) => {
    html += `<option value="${o.id}">${o.name} (武力: ${o.war}, 統率: ${o.leadership}, 駐守: ${CITY_NAMES[o.city] || o.city})</option>`;
  });

  html += `
        </select>
      </div>

      <div class="form-row">
        <label class="form-label">進攻目標城池：</label>
        <select id="siegeTargetSelect" class="form-select">
  `;

  toChoices.forEach((t) => {
    const fcity = (state.frontier || []).find((f) => f.id === t);
    const troopsInfo = fcity ? ` [敵兵: ${fcity.troops}, 防禦: ${fcity.defense}]` : "";
    html += `<option value="${t}">${CITY_NAMES[t] || t}${troopsInfo}</option>`;
  });

  html += `
        </select>
      </div>

      <div class="form-row">
        <label class="form-label">出征兵力規模：</label>
        <div class="range-controls">
          <input type="range" id="siegeTroopsSlider" class="param-range-slider"
                 min="${troopsMin}" max="${troopsMax}" step="${troopsStep}" value="${troopsMin}">
          <input type="number" id="siegeTroopsInput" class="param-number-input"
                 min="${troopsMin}" max="${troopsMax}" step="${troopsStep}" value="${troopsMin}">
          <span class="range-bounds-text">(${troopsMin} ~ ${troopsMax} 人)</span>
        </div>
      </div>

      <div class="siege-odds-box">
        <div class="odds-title">勝率估算情報：</div>
        <div id="siegeOddsResult" class="odds-display">
          ${
            selectedOfficer.siege_odds && toChoices[0]
              ? `預估勝率：${(selectedOfficer.siege_odds[toChoices[0]] * 100).toFixed(0)}%`
              : "尚無估算資料"
          }
        </div>
        <button id="btnRequestEstimate" class="btn btn-secondary btn-sm">
          向參謀部查詢即時勝率 (/api/estimate)
        </button>
      </div>

      <div class="form-btn-row">
        <button id="btnCommitSiege" class="btn btn-danger btn-lg">
          簽發出征攻城令
        </button>
      </div>
    </div>
  `;

  container.innerHTML = html;

  const slider = container.querySelector("#siegeTroopsSlider");
  const numInput = container.querySelector("#siegeTroopsInput");
  const targetSelect = container.querySelector("#siegeTargetSelect");
  const officerSelect = container.querySelector("#siegeOfficerSelect");
  const oddsResult = container.querySelector("#siegeOddsResult");

  if (slider && numInput) {
    slider.addEventListener("input", () => {
      numInput.value = slider.value;
    });
    numInput.addEventListener("input", () => {
      slider.value = numInput.value;
    });
  }

  // Estimate button
  const btnEstimate = container.querySelector("#btnRequestEstimate");
  if (btnEstimate) {
    btnEstimate.addEventListener("click", async () => {
      const oid = officerSelect.value;
      const target = targetSelect.value;
      const troops = Number(numInput.value);
      const o = cast.find((c) => c.id === oid);
      if (onEstimateOdds && o) {
        oddsResult.textContent = "參謀部推演中...";
        const res = await onEstimateOdds(o.city, target, troops);
        oddsResult.textContent = `參謀部估算勝率：${((res.ratio || 0.5) * 100).toFixed(0)}%`;
      }
    });
  }

  // Commit siege order
  const btnCommit = container.querySelector("#btnCommitSiege");
  if (btnCommit) {
    btnCommit.addEventListener("click", () => {
      const oid = officerSelect.value;
      const target = targetSelect.value;
      const troops = Number(numInput.value);
      onAddOrder({
        officer: oid,
        action: "siege",
        params: { to: target, troops },
        cost: 0,
      });
    });
  }
}

/**
 * 5. Render Watchlist / Cast Spotlight Panel (關注名單: next_cast 勾選上限6，警示色)
 */
export function renderWatchlist(container, state, nextCast, onToggleNextCast, onResetNextCast) {
  let html = `<div class="panel-content watchlist-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【下回合關注焦點名單】</h3>
    <span class="watchlist-counter badge ${nextCast.length === 6 ? "badge-good" : "badge-neutral"}">
      已勾選：${nextCast.length} / 6 人 (上限 6)
    </span>
  </div>`;

  html += `
    <div class="alert-box info-alert">
      <strong>【焦點名單機制說明】</strong>
      <p>君主每回合精力有限，最多關注 6 位武將。在名單內者可由玩家親自下達軍令；未入名單者將由規則 AI 自動指派任務。長期未關注者冷落度上升 (neglect ≥ 4) 或忠誠偏低 (< 80) 可能陳情或有叛變風險。</p>
    </div>

    <div class="watchlist-controls-row">
      <button id="btnResetWatchlist" class="btn btn-secondary btn-sm">恢復為當前焦點</button>
      <span class="hint-text">超過 6 人時將鎖定其餘選項</span>
    </div>

    <div class="watchlist-grid">
  `;

  // Build candidate pool: current cast + all officers in roster belonging to this faction
  const candidateIds = new Set((state.cast || []).map((o) => o.id));
  if (state.roster) {
    Object.values(state.roster).forEach((names) => {
      (names || []).forEach((name) => {
        const oid = NAME_TO_ID[name];
        if (oid) candidateIds.add(oid);
      });
    });
  }

  // Also fallback to all officers of this faction in catalog if empty
  if (candidateIds.size === 0) {
    Object.values(OFFICER_CATALOG)
      .filter((o) => o.faction === state.faction_id)
      .forEach((o) => candidateIds.add(o.id));
  }

  const sortedCandidates = Array.from(candidateIds).map((oid) => getOfficerData(oid, state));
  // Sort: cast first, then high stats
  sortedCandidates.sort((a, b) => {
    if (a.inCast !== b.inCast) return a.inCast ? -1 : 1;
    return b.leadership + b.war + b.politics - (a.leadership + a.war + a.politics);
  });

  const isFull = nextCast.length >= 6;

  sortedCandidates.forEach((o) => {
    const isChecked = nextCast.includes(o.id);
    const isDisabled = !isChecked && isFull;
    const cName = CITY_NAMES[o.city] || o.city;

    // Neglect alert
    let neglectAlert = "";
    if (o.neglect >= 4) {
      neglectAlert = `<span class="badge badge-danger">冷落: ${o.neglect} (危)</span>`;
    } else if (o.neglect > 0) {
      neglectAlert = `<span class="badge badge-warning">冷落: ${o.neglect}</span>`;
    } else {
      neglectAlert = `<span class="badge badge-neutral">冷落: 0</span>`;
    }

    // Loyalty alert
    let loyaltyAlert = "";
    if (o.loyalty < 50) {
      loyaltyAlert = `<span class="badge badge-danger">忠誠: ${o.loyalty} (極度危險)</span>`;
    } else if (o.loyalty < 80) {
      loyaltyAlert = `<span class="badge badge-warning">忠誠: ${o.loyalty} (動搖)</span>`;
    } else {
      loyaltyAlert = `<span class="badge badge-good">忠誠: ${o.loyalty}</span>`;
    }

    html += `
      <div class="watchlist-card ${isChecked ? "checked" : ""} ${isDisabled ? "disabled" : ""}">
        <label class="watchlist-checkbox-label">
          <input type="checkbox" class="watchlist-cb" value="${o.id}"
                 ${isChecked ? "checked" : ""} ${isDisabled ? "disabled" : ""}>
          <div class="watchlist-card-body">
            <div class="w-head">
              <span class="w-name">${o.name}</span>
              <span class="w-city">${cName}</span>
            </div>
            <div class="w-stats">
              統 ${o.leadership} | 武 ${o.war} | 政 ${o.politics}
            </div>
            <div class="w-badges">
              ${loyaltyAlert}
              ${neglectAlert}
              ${o.inCast ? `<span class="tag-cast">本回合焦點</span>` : `<span class="tag-roster">留守</span>`}
            </div>
          </div>
        </label>
      </div>
    `;
  });

  html += `</div></div>`;
  container.innerHTML = html;

  // Checkbox change handlers
  container.querySelectorAll(".watchlist-cb").forEach((cb) => {
    cb.addEventListener("change", () => {
      const oid = cb.value;
      if (oid && onToggleNextCast) {
        onToggleNextCast(oid, cb.checked);
      }
    });
  });

  // Reset watchlist handler
  const btnReset = container.querySelector("#btnResetWatchlist");
  if (btnReset) {
    btnReset.addEventListener("click", () => {
      if (onResetNextCast) onResetNextCast();
    });
  }
}

/**
 * 6. Render Chronicle Panel (奏摺起草: ≤ 300字)
 */
export function renderChronicle(container, chronicle, onUpdateChronicle) {
  const currentLength = (chronicle || "").length;

  let html = `<div class="panel-content chronicle-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【君主奏摺 · 治國札記】</h3>
    <span class="char-counter ${currentLength > 300 ? "text-danger" : ""}">${currentLength} / 300 字</span>
  </div>`;

  html += `
    <div class="alert-box info-alert">
      <strong>【奏摺用途】</strong>
      <p>記錄君主本回合的治國方針與戰略意圖（限 300 字）。此內容將記入歷史日誌，並可供推演回放與戰報閱覽。</p>
    </div>

    <div class="chronicle-textarea-wrap">
      <textarea id="chronicleInput" class="chronicle-textarea" maxlength="300"
                placeholder="請撰寫本回合戰略方針，例如：厚植農業基石，充實宛城防禦；遣關將軍伺機圖襄陽...">${chronicle || ""}</textarea>
    </div>

    <div class="presets-row">
      <span class="preset-label">快捷策論：</span>
      <button class="btn btn-sm btn-preset" data-text="休養生息，厚植國力，開墾農田以實倉廩。">休養生息</button>
      <button class="btn btn-sm btn-preset" data-text="厲兵秣馬，廣招精兵，枕戈待旦伺機北伐。">整軍備戰</button>
      <button class="btn btn-sm btn-preset" data-text="築壘固防，深溝高壘，嚴防各路諸侯奇襲。">固守防禦</button>
    </div>
  </div>`;

  container.innerHTML = html;

  const textarea = container.querySelector("#chronicleInput");
  if (textarea) {
    textarea.addEventListener("input", () => {
      if (onUpdateChronicle) onUpdateChronicle(textarea.value);
    });
  }

  container.querySelectorAll(".btn-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      const text = btn.getAttribute("data-text");
      if (text && textarea) {
        textarea.value = text;
        if (onUpdateChronicle) onUpdateChronicle(text);
      }
    });
  });
}

/**
 * 7. Render Settlement Panel (回合結算: feedback 醒目顯示，事件逐條呈現)
 */
export function renderSettlement(container, status, onProceedNextTurn) {
  let html = `<div class="panel-content settlement-panel">`;
  html += `<div class="panel-header-bar">
    <h3 class="panel-title">【第 ${status.turn || 0} 回合 · 全境推演結算】</h3>
    <span class="badge badge-good">階段：結算完畢</span>
  </div>`;

  // Feedback (醒目顯示)
  const feedbacks = status.feedback || [];
  if (feedbacks.length > 0) {
    html += `
      <div class="alert-box feedback-alert-box">
        <h4 class="alert-title">⚠️ 軍務反饋與審查結果：</h4>
        <ul class="feedback-list">
    `;
    feedbacks.forEach((fb) => {
      html += `<li class="feedback-item">${fb}</li>`;
    });
    html += `</ul></div>`;
  } else {
    html += `
      <div class="alert-box good-alert-box">
        <h4 class="alert-title">✓ 全軍軍令順利執行</h4>
        <p>本回合下達之所有合法軍令皆已依序執行完畢，無駁回項目。</p>
      </div>
    `;
  }

  // Events (事件逐條顯示)
  const events = status.report || status.events || [];
  html += `
    <div class="section-sub-block">
      <h4 class="sub-block-title">【天下戰報與各方動態】</h4>
      <div class="events-timeline">
  `;

  const scene = status.scene || {};
  if (scene.season) {
    html += `<div class="scene-card">${scene.key ? `<img class="scene-art" src="./assets/art/scenes/${scene.key}.svg" alt="" onerror="this.style.display='none'">` : ""}<div class="scene-label">${scene.label}</div>`
      + (scene.new_year ? `<p>${scene.new_year}</p>` : "")
      + `<p>${scene.season}</p>`
      + (scene.quiet ? `<p class="scene-quiet">${scene.quiet}</p>` : "") + `</div>`;
  }
  const story = status.story || [];
  story.forEach((line, i) => {
    const art = (status.story_art || [])[i];
    if (art) html += `<img class="story-art" src="./assets/art/scenes/${art}.svg" alt="" onerror="this.style.display='none'">`;
    html += `<div class="event-card event-story"><span class="event-bullet">⚔</span> <span class="event-text">${line}</span></div>`;
  });

  if (events.length === 0 && story.length === 0) {
    html += `<div class="empty-notice">本回合無重大戰事事件。</div>`;
  } else {
    events.forEach((ev) => {
      html += `<div class="event-card"><span class="event-bullet">◆</span> <span class="event-text">${ev}</span></div>`;
    });
  }

  html += `
      </div>
    </div>

    <div class="form-btn-row">
      <button id="btnProceedTurn" class="btn btn-primary btn-lg">
        進入下一回合 (Enter)
      </button>
    </div>
  </div>`;

  container.innerHTML = html;

  const btnProceed = container.querySelector("#btnProceedTurn");
  if (btnProceed) {
    btnProceed.addEventListener("click", () => {
      if (onProceedNextTurn) onProceedNextTurn();
    });
  }
}

/**
 * 8. Render Game Over Panel (結束畫面)
 */
export function renderGameOver(container, status, state, onRestart) {
  const isWinner = status.winner === state.faction_id;
  const winnerName = status.winner ? (FACTION_INFO[status.winner]?.name || status.winner) : "平局";

  let html = `<div class="panel-content game-over-panel">`;
  html += `
    <div class="game-over-banner ${isWinner ? "victory" : "defeat"}">
      <h2 class="game-over-title">${isWinner ? "【大獲全勝 · 天下歸一】" : "【勢力覆滅 · 抱憾終局】"}</h2>
      <p class="game-over-subtitle">
        ${isWinner ? "漢室復興，四海承平，萬民擁戴！" : `由 ${winnerName} 奪得中原霸權，一統天下。`}
      </p>
    </div>

    <div class="stat-grid summary-grid">
      <div class="stat-item"><span class="stat-label">存續回合數：</span><span class="stat-val highlight">${status.turn || 0}</span></div>
      <div class="stat-item"><span class="stat-label">最終佔領城池：</span><span class="stat-val highlight">${(state.cities || []).length} 座</span></div>
      <div class="stat-item"><span class="stat-label">麾下總兵力：</span><span class="stat-val troop-val">
        ${(state.cities || []).reduce((acc, c) => acc + (c.troops || 0), 0)} 人
      </span></div>
    </div>

    <div class="form-btn-row">
      <button id="btnRestartGame" class="btn btn-primary btn-lg">返回主選單 / 重新開始</button>
    </div>
  </div>`;

  container.innerHTML = html;

  const btnRestart = container.querySelector("#btnRestartGame");
  if (btnRestart) {
    btnRestart.addEventListener("click", () => {
      if (onRestart) onRestart();
    });
  }
}
