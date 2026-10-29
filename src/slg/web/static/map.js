/**
 * map.js - SVG Map renderer for Three Kingdoms SLG.
 *
 * Implements interactive tactical map with Fog of War, faction coloring,
 * roads between cities, responsive scaling, and accessibility labels.
 * Strictly guarantees font-size >= 14px on all textual elements.
 */

export const CITY_NAMES = {
  hanzhong: "漢中",
  wancheng: "宛城",
  luoyang: "洛陽",
  chenliu: "陳留",
  xuchang: "許昌",
  xiangyang: "襄陽",
  jianye: "建業",
  wujun: "吳郡",
  kuaiji: "會稽",
};

export const FACTION_INFO = {
  faction_1: { name: "曹操", tag: "魏", color: "#3b82f6", border: "#60a5fa", bg: "#1e293b" },
  faction_2: { name: "劉備", tag: "蜀", color: "#10b981", border: "#34d399", bg: "#064e3b" },
  faction_3: { name: "孫權", tag: "吳", color: "#ef4444", border: "#f87171", bg: "#7f1d1d" },
};

export const CITY_POS = {
  hanzhong: [1.4, 2.6],
  wancheng: [3.4, 3.8],
  luoyang: [4.2, 6.4],
  chenliu: [7.2, 7.2],
  xuchang: [7.0, 4.8],
  xiangyang: [5.6, 2.2],
  jianye: [8.8, 3.4],
  wujun: [9.8, 2.1],
  kuaiji: [9.8, 0.7],
};

const CITY_TERRAIN_ICON = { hanzhong: "basin", wancheng: "plain", luoyang: "pass", chenliu: "plain", xuchang: "plain",
  xiangyang: "river", jianye: "river", wujun: "sea", kuaiji: "sea" };

// Visual offsets applied on frontend to ensure all city boxes do not overlap,
// while strictly preserving backend coordinates and JSON semantics.
export const CITY_VISUAL_OFFSETS = {
  wujun: [0, 5],
  kuaiji: [-10, 28],
};

function coordToSvg(x, y, cityId = null) {
  let px = 70 + x * 82;
  let py = 50 + (8.5 - y) * 75;
  if (cityId && CITY_VISUAL_OFFSETS[cityId]) {
    px += CITY_VISUAL_OFFSETS[cityId][0];
    py += CITY_VISUAL_OFFSETS[cityId][1];
  }
  return [px, py];
}

/**
 * Render the tactical SVG map into container.
 * @param {HTMLElement} container
 * @param {Object} state - FactionView + map payload
 * @param {string} selectedCityId
 * @param {Function} onCitySelect
 */
export function renderMap(container, state, selectedCityId, onCitySelect) {
  container.innerHTML = "";

  const ownCityMap = new Map((state.cities || []).map((c) => [c.id, c]));
  const frontierMap = new Map((state.frontier || []).map((f) => [f.id, f]));
  const nodeVisMap = new Map((state.map?.nodes || []).map((n) => [n.id, n.visibility]));
  const edges = state.map?.edges || [];

  // Build node pixel coordinate cache using backend state.map.nodes coordinates with fallback to CITY_POS
  const backendNodes = state.map?.nodes || [];
  const backendCoords = new Map(backendNodes.map((n) => [n.id, [n.x, n.y]]));
  const nodeIds = Array.from(new Set([...Object.keys(CITY_POS), ...backendNodes.map((n) => n.id)]));

  const coords = {};
  for (const cid of nodeIds) {
    const [x, y] = backendCoords.get(cid) || CITY_POS[cid] || [5.0, 5.0];
    coords[cid] = coordToSvg(x, y, cid);
  }

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  let vb = "0 0 960 720";
  if (window.matchMedia && window.matchMedia("(max-width: 899px)").matches) {
    // Mobile: crop the viewBox tightly around the city boxes so no empty bands are drawn.
    const pts = Object.values(coords);
    const x0 = Math.min(...pts.map((p) => p[0])) - 84, x1 = Math.max(...pts.map((p) => p[0])) + 84;
    const y0 = Math.min(...pts.map((p) => p[1])) - 64, y1 = Math.max(...pts.map((p) => p[1])) + 64;
    vb = `${x0} ${y0} ${x1 - x0} ${y1 - y0}`;
    svg.dataset.mobileWidth = String(Math.round(x1 - x0));
  }
  svg.setAttribute("viewBox", vb);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.classList.add("tactical-map-svg");
  svg.setAttribute("role", "region");
  svg.setAttribute("aria-label", "三國勢力全境地圖");

  // Defs: Filters and gradients
  const defs = document.createElementNS(svgNS, "defs");
  defs.innerHTML = `
    <pattern id="gridPattern" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="1"/>
    </pattern>
    <filter id="glowGold" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="#facc15" flood-opacity="0.9"/>
    </filter>
    <filter id="nodeShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.6"/>
    </filter>
  `;
  svg.appendChild(defs);

  // Background rect with subtle tactical grid
  const bg = document.createElementNS(svgNS, "rect");
  bg.setAttribute("width", "960");
  bg.setAttribute("height", "720");
  bg.setAttribute("fill", "#0b1120");
  svg.appendChild(bg);

  // Terrain illustration, aligned to the city coordinate system (px = 70 + 82x, py = 50 + 75(8.5 - y)).
  const terrain = document.createElementNS(svgNS, "image");
  terrain.setAttribute("href", "./assets/art/map_terrain.svg");
  terrain.setAttribute("x", "70");
  terrain.setAttribute("y", "50");
  terrain.setAttribute("width", "902");
  terrain.setAttribute("height", "637.5");
  terrain.setAttribute("preserveAspectRatio", "none");
  terrain.setAttribute("style", "filter: brightness(1.3)");
  svg.appendChild(terrain);

  const gridRect = document.createElementNS(svgNS, "rect");
  gridRect.setAttribute("width", "960");
  gridRect.setAttribute("height", "720");
  gridRect.setAttribute("fill", "url(#gridPattern)");
  svg.appendChild(gridRect);

  // Map Title / Compass Watermark
  const compass = document.createElementNS(svgNS, "text");
  compass.setAttribute("x", "40");
  compass.setAttribute("y", "40");
  compass.setAttribute("fill", "rgba(255,255,255,0.35)");
  compass.setAttribute("font-size", "14");
  compass.setAttribute("font-weight", "bold");
  compass.textContent = "北 (North) ↑";
  svg.appendChild(compass);

  // Edges layer (roads between cities)
  const edgesGroup = document.createElementNS(svgNS, "g");
  edgesGroup.setAttribute("class", "map-edges-layer");

  const farLabels = [];
  const FAR = { "xiangyang|jianye": 628, "hanzhong|wancheng": 513 };
  edges.forEach(([fromId, toId]) => {
    const farKm = FAR[[fromId, toId].sort().join("|")];
    const fromCoord = coords[fromId];
    const toCoord = coords[toId];
    if (!fromCoord || !toCoord) return;

    const isConnectedToSelected = fromId === selectedCityId || toId === selectedCityId;

    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", fromCoord[0]);
    line.setAttribute("y1", fromCoord[1]);
    line.setAttribute("x2", toCoord[0]);
    line.setAttribute("y2", toCoord[1]);
    line.setAttribute("stroke", isConnectedToSelected ? "#facc15" : "#334155");
    line.setAttribute("stroke-width", isConnectedToSelected ? "4" : "3");
    line.setAttribute("stroke-dasharray", isConnectedToSelected ? "6,4" : (farKm ? "2,9" : "none"));
    line.setAttribute("stroke-linecap", "round");
    edgesGroup.appendChild(line);
    if (farKm) {
      const mx = (fromCoord[0] + toCoord[0]) / 2, my = (fromCoord[1] + toCoord[1]) / 2;
      const g = document.createElementNS(svgNS, "g");
      const bg = document.createElementNS(svgNS, "rect");
      bg.setAttribute("x", mx - 38); bg.setAttribute("y", my - 10); bg.setAttribute("width", 76); bg.setAttribute("height", 20);
      bg.setAttribute("rx", 10); bg.setAttribute("fill", "#0b1220"); bg.setAttribute("stroke", "#fbbf24"); bg.setAttribute("stroke-width", 1);
      const lab = document.createElementNS(svgNS, "text");
      lab.setAttribute("x", mx); lab.setAttribute("y", my + 5);
      lab.setAttribute("text-anchor", "middle"); lab.setAttribute("fill", "#fbbf24"); lab.setAttribute("font-size", "13");
      lab.textContent = `道遠 ${farKm}km`;
      g.appendChild(bg); g.appendChild(lab); farLabels.push(g);
    }
  });
  svg.appendChild(edgesGroup);

  // Nodes layer (cities)
  const nodesGroup = document.createElementNS(svgNS, "g");
  nodesGroup.setAttribute("class", "map-nodes-layer");

  nodeIds.forEach((cid) => {
    const [cx, cy] = coords[cid];
    const vis = nodeVisMap.get(cid) || "fog";
    const isSelected = cid === selectedCityId;
    const cityName = CITY_NAMES[cid] || cid;

    let factionTag = "[？]";
    let factionColor = "#64748b";
    let factionBg = "#1e293b";
    let nodeStroke = "#475569";
    let factionEmblem = "neutral";
    let troopText = "";
    let defText = "";
    let resText = "";
    let accessibleDesc = "";

    if (vis === "own") {
      const city = ownCityMap.get(cid);
      const fInfo = FACTION_INFO[state.faction_id] || FACTION_INFO.faction_2;
      factionEmblem = state.faction_id;
      factionTag = `[${fInfo.tag}] 我方`;
      factionColor = fInfo.color;
      factionBg = fInfo.bg;
      nodeStroke = fInfo.border;
      if (city) {
        troopText = `兵 ${city.troops}`;
        defText = `防 ${city.defense}`;
        resText = `金 ${city.gold} / 糧 ${city.food}`;
        accessibleDesc = `我方城池：${cityName}，兵力 ${city.troops}，城防 ${city.defense}，金 ${city.gold}，糧 ${city.food}`;
      }
    } else if (vis === "frontier") {
      const fcity = frontierMap.get(cid);
      const owner = fcity?.owner || "unknown";
      const fInfo = FACTION_INFO[owner] || { tag: "敵", color: "#ef4444", border: "#f87171", bg: "#7f1d1d" };
      factionEmblem = owner;
      factionTag = `[${fInfo.tag}] 前線`;
      factionColor = fInfo.color;
      factionBg = fInfo.bg;
      nodeStroke = fInfo.border;
      if (fcity) {
        troopText = `兵 ${fcity.troops}`;
        defText = `防 ${fcity.defense}`;
        resText = `【內政迷霧】`;
        accessibleDesc = `前線城池：${cityName}，所屬 ${fInfo.name || "敵軍"}，兵力 ${fcity.troops}，城防 ${fcity.defense}`;
      }
    } else {
      // fog
      factionTag = "[迷霧]";
      factionColor = "#64748b";
      factionBg = "#0f172a";
      nodeStroke = "#334155";
      troopText = "？ 未知";
      defText = "";
      resText = "無斥候回報";
      accessibleDesc = `迷霧遮蔽城池：${cityName}，情報未明`;
    }

    const nodeG = document.createElementNS(svgNS, "g");
    nodeG.setAttribute("class", `map-city-node ${isSelected ? "selected" : ""} vis-${vis}`);
    nodeG.setAttribute("transform", `translate(${cx}, ${cy})`);
    nodeG.setAttribute("role", "button");
    nodeG.setAttribute("tabindex", "0");
    nodeG.setAttribute("aria-label", accessibleDesc);
    nodeG.style.cursor = "pointer";

    // Tooltip
    const titleEl = document.createElementNS(svgNS, "title");
    titleEl.textContent = accessibleDesc;
    nodeG.appendChild(titleEl);

    // Selection Halo
    if (isSelected) {
      const halo = document.createElementNS(svgNS, "rect");
      halo.setAttribute("x", "-74");
      halo.setAttribute("y", "-54");
      halo.setAttribute("width", "148");
      halo.setAttribute("height", "108");
      halo.setAttribute("rx", "12");
      halo.setAttribute("fill", "none");
      halo.setAttribute("stroke", "#facc15");
      halo.setAttribute("stroke-width", "4");
      halo.setAttribute("stroke-dasharray", "8,4");
      halo.setAttribute("filter", "url(#glowGold)");
      nodeG.appendChild(halo);
    }

    // Node Box
    const rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("x", "-68");
    rect.setAttribute("y", "-48");
    rect.setAttribute("width", "136");
    rect.setAttribute("height", "96");
    rect.setAttribute("rx", "8");
    rect.setAttribute("fill", factionBg);
    rect.setAttribute("stroke", nodeStroke);
    rect.setAttribute("stroke-width", isSelected ? "3" : "2");
    rect.setAttribute("filter", "url(#nodeShadow)");
    nodeG.appendChild(rect);

    // Top Header Pill on Node
    const tagBg = document.createElementNS(svgNS, "rect");
    tagBg.setAttribute("x", "-66");
    tagBg.setAttribute("y", "-46");
    tagBg.setAttribute("width", "132");
    tagBg.setAttribute("height", "24");
    tagBg.setAttribute("rx", "5");
    tagBg.setAttribute("fill", factionColor);
    tagBg.setAttribute("opacity", "0.9");
    nodeG.appendChild(tagBg);

    // Header Tag Text (>= 14px)
    const tagText = document.createElementNS(svgNS, "text");
    tagText.setAttribute("x", "0");
    tagText.setAttribute("y", "-29");
    tagText.setAttribute("text-anchor", "middle");
    tagText.setAttribute("fill", "#ffffff");
    tagText.setAttribute("font-size", "14");
    tagText.setAttribute("font-weight", "bold");
    tagText.textContent = factionTag;
    nodeG.appendChild(tagText);
    const emblemKey = factionEmblem;
    const emblem = document.createElementNS(svgNS, "image");
    emblem.setAttribute("href", `./assets/art/emblems/${["faction_1","faction_2","faction_3"].includes(emblemKey) ? emblemKey : "neutral"}.svg`);
    emblem.setAttribute("x", "-65"); emblem.setAttribute("y", "-45"); emblem.setAttribute("width", "22"); emblem.setAttribute("height", "22");
    nodeG.appendChild(emblem);
    if (CITY_TERRAIN_ICON[cid] && vis !== "fog") {
      const ti = document.createElementNS(svgNS, "image");
      ti.setAttribute("href", `./assets/art/icons/${CITY_TERRAIN_ICON[cid]}.svg`);
      ti.setAttribute("x", "46"); ti.setAttribute("y", "-22"); ti.setAttribute("width", "20"); ti.setAttribute("height", "20");
      ti.setAttribute("opacity", "0.85");
      nodeG.appendChild(ti);
    }

    if (vis === "fog") {
      // Large Question Mark for Fog
      const fogQ = document.createElementNS(svgNS, "text");
      fogQ.setAttribute("x", "0");
      fogQ.setAttribute("y", "12");
      fogQ.setAttribute("text-anchor", "middle");
      fogQ.setAttribute("fill", "#94a3b8");
      fogQ.setAttribute("font-size", "28");
      fogQ.setAttribute("font-weight", "900");
      fogQ.textContent = "？";
      nodeG.appendChild(fogQ);

      const fogName = document.createElementNS(svgNS, "text");
      fogName.setAttribute("x", "0");
      fogName.setAttribute("y", "36");
      fogName.setAttribute("text-anchor", "middle");
      fogName.setAttribute("fill", "#cbd5e1");
      fogName.setAttribute("font-size", "14");
      fogName.textContent = `${cityName} (未探)`;
      nodeG.appendChild(fogName);
    } else {
      // City Name (16px)
      const nameText = document.createElementNS(svgNS, "text");
      nameText.setAttribute("x", "0");
      nameText.setAttribute("y", "-3");
      nameText.setAttribute("text-anchor", "middle");
      nameText.setAttribute("fill", "#f8fafc");
      nameText.setAttribute("font-size", "16");
      nameText.setAttribute("font-weight", "bold");
      nameText.textContent = cityName;
      nodeG.appendChild(nameText);

      // Troop / Def text (>= 14px)
      const statLine = document.createElementNS(svgNS, "text");
      statLine.setAttribute("x", "0");
      statLine.setAttribute("y", "18");
      statLine.setAttribute("text-anchor", "middle");
      statLine.setAttribute("fill", "#cbd5e1");
      statLine.setAttribute("font-size", "14");
      statLine.textContent = `${troopText}  ${defText}`;
      nodeG.appendChild(statLine);

      // Gold/Food or Fog indicator (>= 14px)
      const resLine = document.createElementNS(svgNS, "text");
      resLine.setAttribute("x", "0");
      resLine.setAttribute("y", "38");
      resLine.setAttribute("text-anchor", "middle");
      resLine.setAttribute("fill", vis === "own" ? "#facc15" : "#94a3b8");
      resLine.setAttribute("font-size", "14");
      resLine.textContent = resText;
      nodeG.appendChild(resLine);
    }

    // Click / Enter interaction
    const selectHandler = (e) => {
      e.stopPropagation();
      onCitySelect(cid);
    };

    nodeG.addEventListener("click", selectHandler);
    nodeG.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectHandler(e);
      }
    });

    nodesGroup.appendChild(nodeG);
  });
  svg.appendChild(nodesGroup);
  farLabels.forEach((g) => svg.appendChild(g));

  // Legend at bottom left
  const legend = document.createElementNS(svgNS, "g");
  legend.setAttribute("transform", "translate(20, 655)");
  legend.innerHTML = `
    <rect width="460" height="50" rx="6" fill="rgba(15, 23, 42, 0.88)" stroke="#334155" stroke-width="1"/>
    <circle cx="22" cy="25" r="8" fill="#10b981"/>
    <text x="36" y="30" fill="#cbd5e1" font-size="14">我方領地</text>
    <circle cx="135" cy="25" r="8" fill="#3b82f6"/>
    <text x="149" y="30" fill="#cbd5e1" font-size="14">魏 (曹操)</text>
    <circle cx="245" cy="25" r="8" fill="#ef4444"/>
    <text x="259" y="30" fill="#cbd5e1" font-size="14">吳 (孫權)</text>
    <circle cx="355" cy="25" r="8" fill="#64748b"/>
    <text x="369" y="30" fill="#cbd5e1" font-size="14">迷霧 (？)</text>
  `;
  svg.appendChild(legend);

  container.appendChild(svg);
}
