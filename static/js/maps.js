/* YugKrit - maps.js: Leaflet + OpenStreetMap helpers */

document.addEventListener("DOMContentLoaded", function () {
  initChallengeMap();
  initLocationPicker();
});

/* Government / marketplace map showing multiple challenge markers.
   Expects: <div id="challenge-map" data-locations='[{"id":1,"title":"...", "lat":..,"lng":..,"category":"..","priority":80,"status":"VERIFIED"}]'></div> */
function initChallengeMap() {
  const el = document.getElementById("challenge-map");
  if (!el || typeof L === "undefined") return;

  let locations = [];
  try {
    locations = JSON.parse(el.getAttribute("data-locations") || "[]");
  } catch (e) {
    locations = [];
  }

  const center = locations.length ? [locations[0].lat, locations[0].lng] : [26.8467, 80.9462]; // Lucknow default
  const map = L.map(el).setView(center, locations.length ? 7 : 5);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(map);

  locations.forEach((loc) => {
    if (!loc.lat || !loc.lng) return;
    const marker = L.marker([loc.lat, loc.lng]).addTo(map);
    const priorityColor = loc.priority >= 70 ? "#c0392b" : loc.priority >= 40 ? "#b8860b" : "#1c8a54";
    marker.bindPopup(`
      <h4>${loc.title}</h4>
      <p style="margin:2px 0;font-size:12px;">${loc.category || ""}</p>
      <p style="margin:2px 0;font-size:12px;">Priority: <b style="color:${priorityColor}">${loc.priority || "-"}</b> &middot; ${loc.status || ""}</p>
      ${loc.url ? `<a href="${loc.url}" style="font-size:12px;">View Challenge &rarr;</a>` : ""}
    `);
  });
}

/* Single-pin picker for the "submit challenge" location step.
   Expects: <div id="location-picker"></div>, and hidden inputs #latitude / #longitude */
function initLocationPicker() {
  const el = document.getElementById("location-picker");
  if (!el || typeof L === "undefined") return;

  const latInput = document.getElementById("latitude");
  const lngInput = document.getElementById("longitude");

  const defaultCenter = [26.8467, 80.9462]; // Lucknow
  const map = L.map(el).setView(defaultCenter, 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18,
  }).addTo(map);

  let marker = L.marker(defaultCenter, { draggable: true }).addTo(map);
  setCoords(defaultCenter[0], defaultCenter[1]);

  marker.on("dragend", () => {
    const pos = marker.getLatLng();
    setCoords(pos.lat, pos.lng);
  });

  map.on("click", (e) => {
    marker.setLatLng(e.latlng);
    setCoords(e.latlng.lat, e.latlng.lng);
  });

  function setCoords(lat, lng) {
    if (latInput) latInput.value = lat.toFixed(6);
    if (lngInput) lngInput.value = lng.toFixed(6);
  }
}
