const {DeckGL, TerrainLayer, GeoJsonLayer, ScatterplotLayer} = deck;

const COLORS = {
  boundary: [143, 166, 189, 220],
  pipelines: [157, 0, 255, 120],
  railroads: [215, 221, 230, 92],
  roads: [255, 210, 122, 120],
  places: [154, 167, 180, 60],
  ports: [77, 208, 225, 160],
  ghg: [255, 140, 66, 190]
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadManifest() {
  return loadJson('../output/deck-data/manifest.json');
}

function formatTons(value) {
  return Number(value || 0).toLocaleString('en-US', {maximumFractionDigits: 0});
}

function clampToVirginia(viewState, bounds) {
  const [minLon, minLat, maxLon, maxLat] = bounds;
  return {
    ...viewState,
    longitude: clamp(viewState.longitude, minLon - 0.4, maxLon + 0.4),
    latitude: clamp(viewState.latitude, minLat - 0.4, maxLat + 0.4),
    zoom: clamp(viewState.zoom, 6, 11)
  };
}

(async () => {
  try {
    const manifest = await loadManifest();
    const ghgGeoJson = await loadJson(`../${manifest.files.ghg}`);
    const ghgFeatures = ghgGeoJson.features || [];
    const terrainBounds = manifest.bounds;

    const viewState = {
      longitude: manifest.center[0],
      latitude: manifest.center[1],
      zoom: 7,
      minZoom: 6,
      maxZoom: 11,
      pitch: 45,
      bearing: 18
    };

    const layers = [
      new GeoJsonLayer({
        id: 'va-mask',
        data: `../${manifest.files.boundary}`,
        filled: true,
        stroked: false,
        getFillColor: [0, 0, 0, 255],
        operation: 'mask'
      }),
      new TerrainLayer({
        id: 'terrain',
        elevationData: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
        texture: 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
        bounds: terrainBounds,
        extent: terrainBounds,
        maskId: 'va-mask',
        elevationDecoder: {rScaler: 256, gScaler: 1, bScaler: 1 / 256, offset: -32768},
        strategy: 'no-overlap',
        minZoom: 0,
        maxZoom: 12,
        wireframe: false,
        color: [255, 255, 255],
        material: {ambient: 0.4, diffuse: 0.6, shininess: 12, specularColor: [120, 120, 120]},
        operation: 'terrain+draw',
        elevationScale: manifest.terrain_exaggeration || 1.8
      }),
      new GeoJsonLayer({
        id: 'boundary',
        data: `../${manifest.files.boundary}`,
        stroked: true,
        filled: true,
        getFillColor: [0, 0, 0, 0],
        getLineColor: COLORS.boundary,
        getLineWidth: 120,
        lineWidthMinPixels: 1
      }),
      new GeoJsonLayer({
        id: 'pipelines',
        data: `../${manifest.files.pipelines}`,
        stroked: true,
        filled: false,
        getLineColor: COLORS.pipelines,
        getLineWidth: 80,
        lineWidthMinPixels: 1
      }),
      new GeoJsonLayer({
        id: 'railroads',
        data: `../${manifest.files.railroads}`,
        stroked: true,
        filled: false,
        getLineColor: COLORS.railroads,
        getLineWidth: 50,
        lineWidthMinPixels: 1
      }),
      new GeoJsonLayer({
        id: 'primary-roads',
        data: `../${manifest.files.primary_roads}`,
        stroked: true,
        filled: false,
        getLineColor: COLORS.roads,
        getLineWidth: 95,
        lineWidthMinPixels: 1
      }),
      new GeoJsonLayer({
        id: 'incorporated-places',
        data: `../${manifest.files.incorporated_places}`,
        stroked: true,
        filled: false,
        getLineColor: COLORS.places,
        getLineWidth: 40,
        lineWidthMinPixels: 1
      }),
      new GeoJsonLayer({
        id: 'ports',
        data: `../${manifest.files.principal_ports}`,
        pointType: 'circle',
        filled: true,
        getPointRadius: 1200,
        pointRadiusMinPixels: 2,
        getFillColor: COLORS.ports,
        pickable: true
      }),
      new ScatterplotLayer({
        id: 'ghg-facilities',
        data: ghgFeatures,
        filled: true,
        stroked: false,
        getPosition: (d) => d.geometry.coordinates,
        getRadius: (d) => d.properties.radius_m,
        radiusUnits: 'meters',
        radiusMinPixels: 2,
        getFillColor: COLORS.ghg,
        pickable: true
      })
    ];

    new DeckGL({
      container: 'app',
      mapStyle: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
      controller: true,
      initialViewState: viewState,
      onViewStateChange: ({viewState: next}) => clampToVirginia(next, manifest.bounds),
      layers,
      getTooltip: ({object, layer}) => {
        if (!object) return null;
        if (layer.id === 'ghg-facilities') {
          const props = object.properties || {};
          return {
            html: `<strong>${props.facility_name || 'Facility'}</strong><br/>Subparts: ${props.subparts || 'N/A'}<br/>GHG: ${formatTons(props.ghg_quantity_metric_tons_co2e)} tCO2e`
          };
        }
        return {text: layer.id};
      }
    });
  } catch (error) {
    document.getElementById('app').innerHTML = `<div style="color:#d8e2ee;padding:16px;">${error.message}</div>`;
    console.error(error);
  }
})();
