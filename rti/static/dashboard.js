/* RTI Command Center — Globe + 3D Planes + WebSocket */

const API = "http://localhost:8000/api/v1";
const WS_URL = `ws://${location.host}/ws`;

// ── airports ──
const AIRPORTS = {
  DXB: { lat: 25.25, lng: 55.37 }, LHR: { lat: 51.47, lng: -0.45 },
  JFK: { lat: 40.64, lng: -73.78 }, DOH: { lat: 25.27, lng: 51.61 },
  AUH: { lat: 24.45, lng: 54.65 }, CDG: { lat: 49.01, lng: 2.55 },
  SIN: { lat: 1.36, lng: 103.99 }, RUH: { lat: 24.96, lng: 46.70 },
  JED: { lat: 21.68, lng: 39.16 }, IST: { lat: 41.28, lng: 28.75 },
  CAI: { lat: 30.12, lng: 31.41 }, BOM: { lat: 19.09, lng: 72.87 },
  DEL: { lat: 28.56, lng: 77.10 }, KUL: { lat: 2.75, lng: 101.71 },
  BKK: { lat: 13.69, lng: 100.75 }, HKG: { lat: 22.31, lng: 113.92 },
  NRT: { lat: 35.77, lng: 140.39 }, FRA: { lat: 50.04, lng: 8.56 },
  AMS: { lat: 52.31, lng: 4.77 }, ORD: { lat: 41.97, lng: -87.91 },
  LAX: { lat: 33.94, lng: -118.41 }, SYD: { lat: -33.95, lng: 151.18 },
  MCT: { lat: 23.59, lng: 58.28 }, BAH: { lat: 26.27, lng: 50.63 },
  KWI: { lat: 29.23, lng: 47.97 }, AMM: { lat: 31.72, lng: 35.99 },
  TLV: { lat: 32.01, lng: 34.89 }, BGW: { lat: 33.26, lng: 44.23 },
  IKA: { lat: 35.42, lng: 51.15 }, PEK: { lat: 40.08, lng: 116.60 },
  ICN: { lat: 37.46, lng: 126.44 }, MNL: { lat: 14.51, lng: 121.02 },
  LOS: { lat: 6.58, lng: 3.32 }, ADD: { lat: 8.98, lng: 38.80 },
  CMB: { lat: 7.18, lng: 79.88 }, KHI: { lat: 24.91, lng: 67.16 },
  DAC: { lat: 23.84, lng: 90.40 }, MLE: { lat: 4.19, lng: 73.53 },
  MAN: { lat: 53.35, lng: -2.27 }, MUC: { lat: 48.35, lng: 11.79 },
};

// ── airspace zones ──
const ZONES = {
  iran:         { lat: 32.5,  lng: 53.75, baseline: 40 },
  persian_gulf: { lat: 27.0,  lng: 52.5,  baseline: 35 },
  red_sea:      { lat: 20.0,  lng: 40.0,  baseline: 25 },
  iraq:         { lat: 33.25, lng: 43.75, baseline: 30 },
  levant:       { lat: 33.5,  lng: 36.5,  baseline: 20 },
  eastern_med:  { lat: 34.0,  lng: 30.75, baseline: 30 },
};

// ── region coords for conflict markers ──
const REGION_MAP = {
  "middle east": { lat: 29, lng: 47 },
  "iran":        { lat: 32.5, lng: 53.7 },
  "israel":      { lat: 31.5, lng: 34.8 },
  "palestine":   { lat: 31.9, lng: 35.2 },
  "iraq":        { lat: 33.2, lng: 44.2 },
  "syria":       { lat: 35.0, lng: 38.0 },
  "yemen":       { lat: 15.5, lng: 48.5 },
  "lebanon":     { lat: 33.9, lng: 35.8 },
  "gulf":        { lat: 27, lng: 52 },
  "turkey":      { lat: 39, lng: 35 },
  "egypt":       { lat: 30, lng: 31 },
  "saudi":       { lat: 24, lng: 45 },
};

let globe;
let ws;
let planes = [];       // 3d plane objects
let planeData = [];    // route data for animation
let animFrame;

// ── init ──
window.addEventListener("DOMContentLoaded", () => {
  initGlobe();
  initPlanes();
  fetchAndRender();   // initial http fetch
  connectWS();        // then switch to ws
  animate();
});


// ═══════════════════════════════════════
//  GLOBE
// ═══════════════════════════════════════

function initGlobe() {
  const el = document.getElementById("globe-container");

  globe = Globe()
    .globeImageUrl("https://unpkg.com/three-globe@2.35.0/example/img/earth-night.jpg")
    .bumpImageUrl("https://unpkg.com/three-globe@2.35.0/example/img/earth-topology.png")
    .backgroundImageUrl("https://unpkg.com/three-globe@2.35.0/example/img/night-sky.png")
    .atmosphereColor("#00d8ff")
    .atmosphereAltitude(0.18)
    .showAtmosphere(true)
    // arcs
    .arcColor(d => d.color)
    .arcDashLength(0.6)
    .arcDashGap(0.3)
    .arcDashAnimateTime(d => d.animTime)
    .arcStroke(d => d.stroke)
    .arcAltitudeAutoScale(0.4)
    // points
    .pointColor(d => d.color)
    .pointAltitude(d => d.alt)
    .pointRadius(d => d.size)
    .pointsMerge(false)
    // rings
    .ringColor(d => () => d.color)
    .ringMaxRadius(d => d.maxR)
    .ringPropagationSpeed(d => d.speed)
    .ringRepeatPeriod(d => d.period)
    // labels
    .labelColor(d => d.color)
    .labelSize(d => d.size)
    .labelDotRadius(d => d.dotRadius)
    .labelAltitude(0.01)
    .labelText("text")
    .labelResolution(2)
    (el);

  // initial POV — upper-left bias
  globe.pointOfView({ lat: 34, lng: 40, altitude: 2.2 }, 0);

  // controls
  const ctrl = globe.controls();
  ctrl.autoRotate = true;
  ctrl.autoRotateSpeed = 0.3;
  ctrl.enableDamping = true;
  ctrl.dampingFactor = 0.1;

  window.addEventListener("resize", () => {
    globe.width(window.innerWidth).height(window.innerHeight);
  });
}


// ═══════════════════════════════════════
//  3D AIRPLANES
// ═══════════════════════════════════════

function buildPlaneGeometry() {
  // low-poly jet: fuselage + wings + tail fin
  const shape = new THREE.Group();

  // fuselage
  const fuse = new THREE.Mesh(
    new THREE.ConeGeometry(0.15, 1.2, 4),
    new THREE.MeshBasicMaterial({ color: 0x00d8ff, transparent: true, opacity: 0.9 })
  );
  fuse.rotation.x = Math.PI / 2;
  shape.add(fuse);

  // wings
  const wingGeo = new THREE.BufferGeometry();
  const wingVerts = new Float32Array([
    0, 0, -0.1,    -0.8, 0, 0.2,    0, 0, 0.1,  // left
    0, 0, -0.1,     0.8, 0, 0.2,    0, 0, 0.1,  // right
  ]);
  wingGeo.setAttribute("position", new THREE.BufferAttribute(wingVerts, 3));
  wingGeo.computeVertexNormals();
  const wing = new THREE.Mesh(
    wingGeo,
    new THREE.MeshBasicMaterial({ color: 0x00d8ff, transparent: true, opacity: 0.7, side: THREE.DoubleSide })
  );
  shape.add(wing);

  // tail fin
  const tailGeo = new THREE.BufferGeometry();
  const tailVerts = new Float32Array([
    0, 0, 0.3,   0, 0.4, 0.5,   0, 0, 0.5,
  ]);
  tailGeo.setAttribute("position", new THREE.BufferAttribute(tailVerts, 3));
  tailGeo.computeVertexNormals();
  const tail = new THREE.Mesh(
    tailGeo,
    new THREE.MeshBasicMaterial({ color: 0x00d8ff, transparent: true, opacity: 0.7, side: THREE.DoubleSide })
  );
  shape.add(tail);

  shape.scale.set(0.6, 0.6, 0.6);
  return shape;
}

function initPlanes() {
  // we'll add planes to the scene once we have route data
  planes = [];
  planeData = [];
}

function spawnPlanes(routeHealth) {
  const scene = globe.scene();

  // remove old planes
  planes.forEach(p => scene.remove(p));
  planes = [];
  planeData = [];

  // pick top routes to visualize (max 20 planes for perf)
  const routes = routeHealth
    .filter(r => {
      const from = AIRPORTS[r.origin];
      const to = AIRPORTS[r.destination];
      return from && to;
    })
    .slice(0, 20);

  routes.forEach((r, i) => {
    const from = AIRPORTS[r.origin];
    const to = AIRPORTS[r.destination];
    const isDisrupted = r.status === "disrupted" || r.status === "degraded";

    const plane = buildPlaneGeometry();

    // color based on status
    const color = isDisrupted ? 0xef4444 : 0x00d8ff;
    plane.traverse(child => {
      if (child.isMesh) {
        child.material.color.setHex(color);
      }
    });

    // add glow for disrupted
    if (isDisrupted) {
      const glow = new THREE.PointLight(0xef4444, 0.5, 3);
      plane.add(glow);
    }

    scene.add(plane);
    planes.push(plane);

    planeData.push({
      from, to, plane,
      progress: Math.random(),       // stagger start positions
      speed: 0.001 + Math.random() * 0.001,
      alt: 0.04 + Math.random() * 0.03,
    });
  });
}

function updatePlanes() {
  const R = 100; // globe radius in scene units (globe.gl default)

  planeData.forEach(d => {
    d.progress += d.speed;
    if (d.progress > 1) d.progress -= 1;

    const t = d.progress;

    // interpolate lat/lng along great circle (linear approx is fine for visuals)
    const lat = d.from.lat + (d.to.lat - d.from.lat) * t;
    const lng = d.from.lng + (d.to.lng - d.from.lng) * t;

    // arc altitude — peaks at midpoint
    const arcAlt = d.alt * Math.sin(t * Math.PI);
    const altitude = 1 + arcAlt; // 1 = surface

    // convert lat/lng/alt to 3d coords
    const phi = (90 - lat) * Math.PI / 180;
    const theta = (lng + 180) * Math.PI / 180;
    const r = R * altitude;

    d.plane.position.set(
      -r * Math.sin(phi) * Math.cos(theta),
       r * Math.cos(phi),
       r * Math.sin(phi) * Math.sin(theta)
    );

    // orient plane along flight path
    const nextT = Math.min(t + 0.02, 1);
    const nextLat = d.from.lat + (d.to.lat - d.from.lat) * nextT;
    const nextLng = d.from.lng + (d.to.lng - d.from.lng) * nextT;
    const nextArc = d.alt * Math.sin(nextT * Math.PI);
    const nextAltitude = 1 + nextArc;

    const nextPhi = (90 - nextLat) * Math.PI / 180;
    const nextTheta = (nextLng + 180) * Math.PI / 180;
    const nr = R * nextAltitude;

    const nextPos = new THREE.Vector3(
      -nr * Math.sin(nextPhi) * Math.cos(nextTheta),
       nr * Math.cos(nextPhi),
       nr * Math.sin(nextPhi) * Math.sin(nextTheta)
    );

    d.plane.lookAt(nextPos);
  });
}

function animate() {
  updatePlanes();
  animFrame = requestAnimationFrame(animate);
}


// ═══════════════════════════════════════
//  WEBSOCKET
// ═══════════════════════════════════════

function connectWS() {
  const dot = document.getElementById("ws-dot");

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    dot.classList.add("connected");
    console.log("ws connected");
  };

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      renderGlobeData(data);
      renderPanels(data);
      spawnPlanes(data.route_health || []);
    } catch (err) {
      console.warn("ws parse error:", err);
    }
  };

  ws.onclose = () => {
    dot.classList.remove("connected");
    console.log("ws disconnected, reconnecting in 5s...");
    setTimeout(connectWS, 5000);
  };

  ws.onerror = () => {
    ws.close();
  };
}


// ═══════════════════════════════════════
//  HTTP FETCH (initial load fallback)
// ═══════════════════════════════════════

async function fetchAndRender() {
  try {
    const res = await fetch(`${API}/briefing`);
    if (!res.ok) return;
    const data = await res.json();
    renderGlobeData(data);
    renderPanels(data);
    spawnPlanes(data.route_health || []);
  } catch (e) {
    console.warn("initial fetch error:", e);
  }
}


// ═══════════════════════════════════════
//  GLOBE VISUALIZATIONS
// ═══════════════════════════════════════

function renderGlobeData(data) {
  // arcs
  const arcs = [];
  data.route_health.forEach(r => {
    const from = AIRPORTS[r.origin];
    const to = AIRPORTS[r.destination];
    if (!from || !to) return;

    const bad = r.status === "disrupted" || r.status === "degraded";
    arcs.push({
      startLat: from.lat, startLng: from.lng,
      endLat: to.lat, endLng: to.lng,
      color: bad
        ? ["rgba(239,68,68,0.9)", "rgba(239,68,68,0.3)"]
        : ["rgba(34,197,94,0.7)", "rgba(34,197,94,0.2)"],
      stroke: bad ? 0.6 : 0.3,
      animTime: bad ? 800 + Math.random() * 600 : 2000 + Math.random() * 1000,
    });
  });
  globe.arcsData(arcs);

  // rings
  const rings = [];
  data.airspace_zones.forEach(z => {
    const c = ZONES[z.name];
    if (!c) return;
    const closed = z.status === "closed";
    const restricted = z.status === "restricted" || z.status === "degraded";
    rings.push({
      lat: c.lat, lng: c.lng,
      color: closed ? "rgba(239,68,68,0.7)" : restricted ? "rgba(245,158,11,0.6)" : "rgba(34,197,94,0.4)",
      maxR: closed ? 6 : 4,
      speed: closed ? 4 : 2,
      period: closed ? 1200 : 2500,
    });
  });
  globe.ringsData(rings);

  // points
  const points = [];
  const used = new Set();
  data.route_health.forEach(r => { used.add(r.origin); used.add(r.destination); });
  used.forEach(code => {
    const ap = AIRPORTS[code];
    if (ap) points.push({ lat: ap.lat, lng: ap.lng, color: "#00d8ff", alt: 0.01, size: 0.25 });
  });

  data.conflict_events.forEach(e => {
    const key = Object.keys(REGION_MAP).find(k => (e.region || "").toLowerCase().includes(k));
    const coords = key ? REGION_MAP[key] : REGION_MAP["middle east"];
    const jitter = () => (Math.random() - 0.5) * 3;
    points.push({
      lat: coords.lat + jitter(), lng: coords.lng + jitter(),
      color: e.tone < -30 ? "#ef4444" : e.tone < -10 ? "#f59e0b" : "#22c55e",
      alt: 0.08, size: 0.4,
    });
  });
  globe.pointsData(points);

  // labels
  const labels = data.airspace_zones.map(z => {
    const c = ZONES[z.name];
    if (!c) return null;
    return {
      lat: c.lat, lng: c.lng,
      text: z.name.replace(/_/g, " ").toUpperCase(),
      color: z.status === "closed" ? "rgba(239,68,68,0.7)" : "rgba(0,216,255,0.5)",
      size: 0.6, dotRadius: 0.3,
    };
  }).filter(Boolean);
  globe.labelsData(labels);
}


// ═══════════════════════════════════════
//  SIDE PANELS
// ═══════════════════════════════════════

function renderPanels(data) {
  const ts = new Date(data.timestamp);

  // time
  document.getElementById("brief-time").textContent =
    ts.getUTCHours().toString().padStart(2, "0") + ":" +
    ts.getUTCMinutes().toString().padStart(2, "0");

  // gauge
  const score = data.escalation_score;
  const gv = document.getElementById("gauge-value");
  const gf = document.getElementById("gauge-fill");
  gv.textContent = score;
  const offset = 327 * (1 - score / 100);
  gf.style.strokeDashoffset = offset;

  if (score >= 70) {
    gf.style.stroke = "#ef4444";
    gv.style.color = "#ef4444";
    gv.style.textShadow = "0 0 15px rgba(239,68,68,0.5)";
  } else if (score >= 40) {
    gf.style.stroke = "#f59e0b";
    gv.style.color = "#f59e0b";
    gv.style.textShadow = "0 0 15px rgba(245,158,11,0.5)";
  } else {
    gf.style.stroke = "#00d8ff";
    gv.style.color = "#00d8ff";
    gv.style.textShadow = "0 0 15px rgba(0,216,255,0.5)";
  }

  // zone tooltip
  const tooltip = document.getElementById("zone-tooltip");
  const worst = [...data.airspace_zones].sort((a, b) => a.aircraft_count - b.aircraft_count)[0];
  if (worst) {
    tooltip.classList.remove("hidden");
    document.getElementById("tt-zone-name").textContent = worst.name.replace(/_/g, " ").toUpperCase() + " AIRSPACE";
    const base = (ZONES[worst.name] || {}).baseline || 30;
    const density = worst.aircraft_count >= 0
      ? Math.round(((worst.aircraft_count - base) / base) * 100)
      : -82;
    document.getElementById("tt-density").textContent = density + "%";
    document.getElementById("tt-risk").textContent = worst.status === "closed" ? "HIGH" : worst.status === "restricted" ? "MEDIUM" : "LOW";
    document.getElementById("tt-risk").className = worst.status === "closed" ? "sev-high" : worst.status === "restricted" ? "sev-medium" : "sev-low";
    document.getElementById("tt-news").textContent = score > 50 ? "Conflict Escalation" : "Normal Traffic";
  }

  // brief
  document.getElementById("situation-summary").textContent = data.situation_summary;

  // impact
  const total = data.route_health.length;
  const disrupted = data.route_health.filter(r => r.status !== "normal").length;
  const avgDelay = data.route_health.reduce((s, r) => s + r.avg_delay_min, 0) / (total || 1);
  const pct = total > 0 ? Math.round((disrupted / total) * 100) : 0;
  document.getElementById("brief-impact").textContent = `${pct}% Routes Disrupted | Avg Delay: ${avgDelay.toFixed(0)}min`;

  // recommendation
  document.getElementById("brief-rec").textContent = data.recommendations[0] || "Maintain situational monitoring.";

  // confidence
  document.getElementById("brief-conf").textContent = Math.min(95, 70 + Math.round(score / 5)) + "%";

  renderRouteCards(data);
  renderAlerts(data);
}


// ── route cards ──
function renderRouteCards(data) {
  const el = document.getElementById("route-cards");
  const routes = data.route_health
    .filter(r => r.status !== "normal")
    .sort((a, b) => b.disrupted_count - a.disrupted_count)
    .slice(0, 5);

  if (!routes.length) {
    el.innerHTML = `<div class="route-card"><div class="rc-top"><span class="rc-route dim">All routes nominal</span></div></div>`;
    return;
  }

  el.innerHTML = routes.map(r => {
    const delay = r.total_count > 0 ? Math.round((r.disrupted_count / r.total_count) * 100) : 0;
    const density = r.total_count > 0 ? r.total_count : "N/A";
    let bc = "badge-stable", bt = "STABLE";
    if (r.status === "disrupted") { bc = "badge-degraded"; bt = "⚠ ⚠ DEGRADED"; }
    else if (r.status === "degraded") { bc = "badge-warning"; bt = "⚠ WARNING"; }

    return `
      <div class="route-card">
        <div class="rc-top">
          <span class="rc-route">${r.origin} <span class="rc-arrow">→</span> ${r.destination}</span>
          <span class="rc-badge ${bc}">${bt}</span>
        </div>
        <div class="rc-stats">
          <span>Delay Rate: <span class="rc-stat-val">${delay}%</span> <span class="trend-up">»</span></span>
          <span>Flight Density: <span class="rc-stat-val">${density}</span>
            ${sparkline(r)}
          </span>
        </div>
      </div>`;
  }).join("");
}

function sparkline(route) {
  const d = route.disrupted_count;
  const pts = [4, 3 + d % 3, 2, 5 - d % 4, 1 + d % 2, 3, 4 - d % 3, 2 + d % 2];
  const mx = Math.max(...pts);
  const w = 40, h = 14;
  const path = pts.map((v, i) => `${(i / (pts.length - 1)) * w},${h - (v / mx) * h}`).join(" ");
  const c = route.status === "disrupted" ? "#ef4444" : route.status === "degraded" ? "#f59e0b" : "#22c55e";
  return `<span class="sparkline-container"><svg width="${w}" height="${h}"><polyline points="${path}" fill="none" stroke="${c}" stroke-width="1.2" opacity="0.7"/></svg></span>`;
}


// ── alerts ──
function renderAlerts(data) {
  const el = document.getElementById("alert-list");

  if (!data.conflict_events.length) {
    el.innerHTML = `<div class="alert-item"><span class="alert-text dim">No active alerts.</span></div>`;
    return;
  }

  el.innerHTML = data.conflict_events.slice(0, 12).map(e => {
    let time = "LIVE";
    if (e.published_at) {
      const m = e.published_at.match(/T(\d{2}:\d{2})/);
      if (m) time = m[1];
    }
    const dot = e.tone < -30 ? "dot-red" : e.tone < -10 ? "dot-amber" : "dot-green";
    const t = e.tone;
    const pts = [2, 4, Math.abs(t) % 6, 3, Math.abs(t) % 5, 5, 2, Math.abs(t) % 4];
    const mx = Math.max(...pts, 1);
    const path = pts.map((v, i) => `${(i / 7) * 36},${12 - (v / mx) * 12}`).join(" ");
    const sc = t < -30 ? "#ef4444" : t < -10 ? "#f59e0b" : "#22c55e";

    return `
      <div class="alert-item">
        <span class="alert-time">${time}</span>
        <div class="alert-dot ${dot}"></div>
        <span class="alert-text">${truncate(e.title, 60)}</span>
        <span class="sparkline-container"><svg width="36" height="12"><polyline points="${path}" fill="none" stroke="${sc}" stroke-width="1" opacity="0.5"/></svg></span>
      </div>`;
  }).join("");
}

function truncate(s, n) {
  return s.length > n ? s.substring(0, n) + "…" : s;
}


// ── pipeline trigger ──
async function triggerRun() {
  const overlay = document.getElementById("loading-overlay");
  const btn = document.getElementById("run-btn");
  overlay.classList.remove("hidden");
  btn.classList.add("loading");

  globe.pointOfView({ lat: 28, lng: 48, altitude: 1.8 }, 1500);

  try {
    // prefer ws if connected
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send("run");
      // ws.onmessage will handle the response
      await new Promise(r => setTimeout(r, 3000)); // give it time
    } else {
      const res = await fetch(`${API}/run`, { method: "POST" });
      const data = await res.json();
      renderGlobeData(data);
      renderPanels(data);
      spawnPlanes(data.route_health || []);
    }
  } catch (e) {
    console.error("run failed:", e);
  } finally {
    overlay.classList.add("hidden");
    btn.classList.remove("loading");
  }
}

window.triggerRun = triggerRun;
