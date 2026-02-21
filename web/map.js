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

async function loadManifest() {
  const response = await fetch('../output/deck-data/manifest.json');
  if (!response.ok) {
    throw new Error('Missing output/deck-data/manifest.json. Run `python -m scripts.build --target deck`.');
  }
  return response.json();
}

function formatTons(value) {
  return Number(value || 0).toLocaleString('en-US', {maximumFractionDigits: 0});
}

loadManifest().then((manifest) => {
  const viewState = {
    longitude: manifest.center[0],
    latitude: manifest.center[1],
    zoom: 6.35,
    minZoom: 5,
    maxZoom: 16,
    pitch: 45,
    bearing: 18
  };

  const layers = [
    new TerrainLayer({
      id: 'terrain',
      elevationData: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
      texture: 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
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
      data: `../${manifest.files.ghg}`,
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
}).catch((error) => {
  document.getElementById('app').innerHTML = `<div style="color:#d8e2ee;padding:16px;">${error.message}</div>`;
  console.error(error);
});
