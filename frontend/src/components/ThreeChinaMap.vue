<template>
  <div ref="rootRef" class="three-map" :class="{ 'is-province-view': focusedProvince }">
    <div ref="labelLayerRef" class="three-map-labels"></div>
    <div ref="hoverLabelRef" class="map-hover-label" v-show="hoverInfo.visible">
      <strong>{{ hoverInfo.province }}</strong>
      <span v-if="!hoverInfo.isCity">{{ hoverInfo.count }} 座</span>
    </div>
    <button v-if="focusedProvince" class="map-reset" type="button" @click="resetView">返回全国</button>
    <div class="map-focus-card" v-if="focusedProvince">
      <span>当前省级地图</span>
      <strong>{{ focusedProvince }}</strong>
      <small>{{ focusedProvinceStationCount }} 座电站</small>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { geoCentroid, geoContains, geoMercator } from "d3-geo";
import gsap from "gsap";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const props = defineProps({
  geoJson: { type: Object, default: null },
  stats: { type: Array, default: () => [] },
  stations: { type: Array, default: () => [] },
  provinceNames: { type: Object, default: () => ({}) },
  normalizeProvinceName: { type: Function, required: true },
  mode: { type: String, default: "dashboard" },
  resultPoint: { type: Object, default: null },
  provincePvpi: { type: Object, default: () => ({}) }
});

const emit = defineEmits(["province-focus", "map-pick"]);

const rootRef = ref(null);
const labelLayerRef = ref(null);
const hoverLabelRef = ref(null);
const focusedProvince = ref("");
const drilldownFeatures = ref(null);
const hoverInfo = ref({ visible: false, province: "", count: 0 });

let scene;
let camera;
let renderer;
let controls;
let raycaster;
let pointer;
let projection;
let animationId;
let resizeObserver;
let mapGroup;
let labelItems = [];
let provinceMeshes = [];
let hoverMesh = null;
let clock;
let pointerDown = null;
let didDrag = false;
let cityGeoCache = new Map();
let cityStatsByProvince = new Map();
let focusedProvinceAdcode = null;
let cityBoundaryFailed = false;
let pillarMaterial = null;
let flightMovers = [];

const CHINA_CENTER = [104.2, 35.8];
const LON_RANGE = { west: 73, east: 136, south: 17, north: 54 };
const FLAT_MAP_DEPTH = 3.2;

const profile = computed(() => {
  if (props.mode === "realtime") return { sampleStep: 3, interactive: true, nationalSpan: 134, provinceSpan: 112 };
  if (props.mode === "mini") return { sampleStep: 6, interactive: false, nationalSpan: 110, provinceSpan: 88 };
  return { sampleStep: 3, interactive: true, nationalSpan: 118, provinceSpan: 104 };
});

const statByName = computed(() => {
  const map = new Map();
  for (const row of props.stats) {
    const name = props.normalizeProvinceName(props.provinceNames[row.province] || row.province);
    map.set(name, row);
  }
  return map;
});

const stationsByProvinceName = computed(() => {
  const groups = new Map();
  for (const row of props.stations) {
    const province = props.normalizeProvinceName(props.provinceNames[row.province] || row.province);
    if (!groups.has(province)) groups.set(province, []);
    groups.get(province).push(row);
  }
  return groups;
});

const activeFeatures = computed(() => {
  const features = props.geoJson?.features || [];
  if (focusedProvince.value && drilldownFeatures.value?.length) return drilldownFeatures.value;
  if (!focusedProvince.value) return features;
  return features.filter((feature) => normalizeFeatureName(feature) === focusedProvince.value);
});

const focusedProvinceStationCount = computed(() => {
  if (!focusedProvince.value) return 0;
  const stations = stationsByProvinceName.value.get(focusedProvince.value) || [];
  return stations.length;
});

const normalizeFeatureName = (feature) => props.normalizeProvinceName(feature.properties?.name || "");

const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const collectCoordinates = (feature, points = []) => {
  const geometry = feature.geometry;
  if (!geometry) return points;
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates || [];
  polygons.forEach((polygon) => {
    polygon.forEach((ring) => {
      ring.forEach((point) => points.push(point));
    });
  });
  return points;
};

const makeProjection = (features) => {
  const center = focusedProvince.value
    ? getFeaturesCenter(features)
    : CHINA_CENTER;
  const targetSpan = focusedProvince.value ? profile.value.provinceSpan : profile.value.nationalSpan;
  const tempProjection = geoMercator().center(center).scale(1).translate([0, 0]);
  const points = features.flatMap((feature) => collectCoordinates(feature));

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  points.forEach(([lon, lat]) => {
    const projected = tempProjection([lon, lat]);
    if (!projected) return;
    const [x, y] = projected;
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  });

  const span = Math.max(maxX - minX, maxY - minY, 1);
  const scale = focusedProvince.value
    ? clamp(targetSpan / span, 80, 5200)
    : clamp(targetSpan / span, 70, 140);
  return geoMercator().center(center).scale(scale).translate([0, 0]);
};

const getFeatureCenter = (feature) => {
  const center = feature.properties?.centroid || feature.properties?.center || geoCentroid(feature);
  return Array.isArray(center) ? center : CHINA_CENTER;
};

const getFeaturesCenter = (features) => {
  if (features.length === 1) return getFeatureCenter(features[0]);
  const center = geoCentroid({ type: "FeatureCollection", features });
  return Array.isArray(center) ? center : CHINA_CENTER;
};

const lonLatToVector = (lon, lat, z = 0) => {
  const [x, y] = projection([Number(lon), Number(lat)]);
  return new THREE.Vector3(x, -y, z);
};

const disposeObject = (object) => {
  object.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose());
      else child.material.dispose();
    }
  });
};

const clearSceneObjects = () => {
  if (mapGroup) {
    scene.remove(mapGroup);
    disposeObject(mapGroup);
  }
  labelItems.forEach((item) => item.el.remove());
  labelItems = [];
  provinceMeshes = [];
  hoverMesh = null;
  pillarMaterial = null;
  flightMovers = [];
  hoverInfo.value = { visible: false, province: "", count: 0 };
};

const getActiveCityCount = (feature) => {
  if (!focusedProvinceAdcode) return 0;
  const cityStats = cityStatsByProvince.get(focusedProvinceAdcode);
  const cityName = normalizeFeatureName(feature);
  return Number(cityStats?.get(cityName) || 0);
};

/* choropleth 色带：省均 PVPI 低 → 高（与设计方案 §3.1 地图色带一致） */
const PVPI_STOPS = [0x0a2b52, 0x0e4b8f, 0x0f79c7, 0x00d4fe, 0x7df0ff].map((hex) => new THREE.Color(hex));
const NO_DATA_COLOR = new THREE.Color(0x0a2144);

const pvpiDomain = computed(() => {
  const values = Object.values(props.provincePvpi || {}).map(Number).filter(Number.isFinite);
  if (!values.length) return { min: 0, max: 1 };
  return { min: Math.min(...values), max: Math.max(...values) };
});

const colorForPvpi = (pvpi) => {
  if (!Number.isFinite(Number(pvpi))) return NO_DATA_COLOR.clone();
  const { min, max } = pvpiDomain.value;
  const t = clamp((Number(pvpi) - min) / (max - min || 1), 0, 1);
  const pos = t * (PVPI_STOPS.length - 1);
  const index = Math.min(PVPI_STOPS.length - 2, Math.floor(pos));
  return PVPI_STOPS[index].clone().lerp(PVPI_STOPS[index + 1], pos - index);
};

const getGeoBaseColor = (feature, tone = 0.45) => {
  const [lon, lat] = getFeatureCenter(feature);
  const west = clamp((108 - Number(lon || CHINA_CENTER[0])) / 34, 0, 1);
  const north = clamp((Number(lat || CHINA_CENTER[1]) - 40) / 13, 0, 1);
  const base = new THREE.Color(0x0e4f86);
  const deep = new THREE.Color(0x0a2c52);
  const plateau = new THREE.Color(0x3f6f8f);
  const cold = new THREE.Color(0x2d5570);
  const color = base.clone()
    .lerp(deep, north * 0.28)
    .lerp(plateau, west * 0.32)
    .lerp(cold, north * west * 0.18);
  return color.offsetHSL(0, 0.05, (tone - 0.45) * 0.09);
};

const createMaterials = (feature, tone = 0.45) => {
  // 全国视图按省均 PVPI choropleth 着色；省级/市级视图保留地形色变化
  const useChoropleth = !focusedProvince.value && props.provincePvpi && Object.keys(props.provincePvpi).length;
  const topColor = useChoropleth ? colorForPvpi(props.provincePvpi[normalizeFeatureName(feature)]) : getGeoBaseColor(feature, tone);
  return [
    new THREE.MeshStandardMaterial({
      color: topColor,
      emissive: new THREE.Color(0x07335c),
      emissiveIntensity: 0.2,
      roughness: 0.62,
      metalness: 0.08,
      transparent: true,
      opacity: 0.98
    }),
  new THREE.MeshStandardMaterial({
    color: 0x062038,
    emissive: 0x072c4e,
    emissiveIntensity: 0.16,
    roughness: 0.68,
    metalness: 0.06,
    transparent: true,
    opacity: 0.92
  })
  ];
};

const simplifyRing = (ring) => {
  const step = profile.value.sampleStep;
  if (!Array.isArray(ring) || ring.length < 80 || step <= 1) return ring;
  const sampled = ring.filter((_, index) => index % step === 0);
  const first = ring[0];
  const last = sampled[sampled.length - 1];
  if (first && last && (first[0] !== last[0] || first[1] !== last[1])) sampled.push(first);
  return sampled.length >= 4 ? sampled : ring;
};

const createShape = (ring) => {
  const points = simplifyRing(ring).map(([lon, lat]) => {
    const [x, y] = projection([lon, lat]);
    return new THREE.Vector2(x, -y);
  });
  return new THREE.Shape(points);
};

const addProvince = (feature) => {
  const name = normalizeFeatureName(feature);
  const provinceName = focusedProvince.value || name;
  const stat = statByName.value.get(provinceName);
  const depth = FLAT_MAP_DEPTH;
  const isCityFeature = Boolean(focusedProvince.value && drilldownFeatures.value?.length);
  const count = Number(stat?.Count || 0);
  const tone = isCityFeature ? 0.35 : 0.45; // 市级地图颜色稍浅
  const polygons = feature.geometry?.type === "Polygon"
    ? [feature.geometry.coordinates]
    : feature.geometry?.coordinates || [];
  const provinceGroup = new THREE.Group();
  provinceGroup.name = name;

  for (const polygon of polygons) {
    if (!polygon?.[0]?.length) continue;
    const shape = createShape(polygon[0]);
    for (const hole of polygon.slice(1)) {
      if (hole.length > 2) shape.holes.push(createShape(hole));
    }
    const geometry = new THREE.ExtrudeGeometry(shape, {
      depth,
      bevelEnabled: true,
      bevelThickness: 0.06,
      bevelSize: 0.06,
      bevelSegments: 1,
      curveSegments: 2
    });
    const mesh = new THREE.Mesh(geometry, createMaterials(feature, tone));
    mesh.userData = {
      province: provinceName,
      displayName: name,
      count,
      depth,
      feature,
      isCityFeature
    };
    provinceGroup.add(mesh);
    provinceMeshes.push(mesh);

    // 城市边界使用更明显的颜色
    const edgeColor = isCityFeature ? 0x4de5ff : 0x9cf8ff;
    const edgeOpacity = isCityFeature ? 0.6 : 0.26;
    const edges = new THREE.EdgesGeometry(geometry, 1);
    const line = new THREE.LineSegments(
      edges,
      new THREE.LineBasicMaterial({ color: edgeColor, transparent: true, opacity: edgeOpacity })
    );
    provinceGroup.add(line);
  }

  // 如果是城市级别，添加城市名称标签
  if (isCityFeature) {
    const center = getFeatureCenter(feature);
    // 直接保存经纬度和名称，不依赖3D空间位置
    if (labelLayerRef.value) {
      const el = document.createElement('div');
      el.className = 'map-city-label';
      el.textContent = name;
      el.style.cssText = `
        position: absolute;
        color: #76e5f3;
        font-size: 12px;
        font-weight: 500;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
        pointer-events: none;
        white-space: nowrap;
        z-index: 100;
        letter-spacing: 0.5px;
        transition: opacity 0.1s ease;
      `;
      labelLayerRef.value.appendChild(el);
      // 保存经纬度而不是3D向量
      labelItems.push({ el, lon: center[0], lat: center[1] });
    }
  }

  if (provinceGroup.children.length) mapGroup.add(provinceGroup);
};

const buildMap = (animated = true) => {
  if (!scene || !props.geoJson) return;
  const features = activeFeatures.value;
  if (!features.length) return;
  clearSceneObjects();
  projection = makeProjection(features);
  mapGroup = new THREE.Group();
  scene.add(mapGroup);

  for (const feature of features) {
    if (feature.properties?.name) addProvince(feature);
  }

  // 在省级视图下总是显示电站光柱
  if (focusedProvince.value) {
    addFallbackStationPillars();
  } else {
    addNationalPillars();
    addFlightLines();
  }

  fitCameraToMap(animated);
};

/* 全国视图：TOP 站点呼吸光柱（InstancedMesh 一次绘制，高度按 PVPI 映射） */
const addNationalPillars = () => {
  const ranked = props.stations
    .filter((row) => Number.isFinite(Number(row.lon)) && Number.isFinite(Number(row.lat)) && Number.isFinite(Number(row.PVPI)))
    .sort((a, b) => b.PVPI - a.PVPI)
    .slice(0, 600);
  if (!ranked.length) return;
  const maxPvpi = Number(ranked[0].PVPI) || 1;
  pillarMaterial = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: 0.55,
    depthWrite: false
  });
  const geometry = new THREE.CylinderGeometry(0.08, 0.16, 1, 8, 1, true);
  const mesh = new THREE.InstancedMesh(geometry, pillarMaterial, ranked.length);
  const dummy = new THREE.Object3D();
  const lowColor = new THREE.Color(0x00d4fe);
  const highColor = new THREE.Color(0x00ffa3);
  const instanceColor = new THREE.Color();
  ranked.forEach((row, index) => {
    const base = lonLatToVector(row.lon, row.lat, FLAT_MAP_DEPTH + 0.02);
    const height = 2.2 + (Number(row.PVPI) / maxPvpi) * 9;
    dummy.position.set(base.x, base.y, base.z + height / 2);
    dummy.rotation.set(Math.PI / 2, 0, 0);
    dummy.scale.set(1, height, 1);
    dummy.updateMatrix();
    mesh.setMatrixAt(index, dummy.matrix);
    mesh.setColorAt(index, instanceColor.copy(lowColor).lerp(highColor, Number(row.PVPI) / maxPvpi));
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  mapGroup.add(mesh);
};

/* 全国视图：PVPI TOP5 省域中心 → 全国最优站点的粒子飞线 */
const addFlightLines = () => {
  const entries = Object.entries(props.provincePvpi || {})
    .map(([name, value]) => ({ name, value: Number(value) }))
    .filter((row) => Number.isFinite(row.value))
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
  const hub = props.stations
    .filter((row) => Number.isFinite(Number(row.lon)) && Number.isFinite(Number(row.lat)) && Number.isFinite(Number(row.PVPI)))
    .sort((a, b) => b.PVPI - a.PVPI)[0];
  if (!entries.length || !hub) return;
  const hubPos = lonLatToVector(hub.lon, hub.lat, FLAT_MAP_DEPTH + 0.4);

  const featureByName = new Map();
  for (const feature of props.geoJson?.features || []) {
    featureByName.set(normalizeFeatureName(feature), feature);
  }
  for (const entry of entries) {
    const feature = featureByName.get(entry.name);
    if (!feature) continue;
    const [lon, lat] = getFeatureCenter(feature);
    const start = lonLatToVector(lon, lat, FLAT_MAP_DEPTH);
    if (start.distanceTo(hubPos) < 8) continue;
    const mid = start.clone().add(hubPos).multiplyScalar(0.5);
    mid.z += start.distanceTo(hubPos) * 0.35;
    const curve = new THREE.QuadraticBezierCurve3(start, mid, hubPos.clone());
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(curve.getPoints(60)),
      new THREE.LineBasicMaterial({ color: 0x00ffa3, transparent: true, opacity: 0.45 })
    );
    mapGroup.add(line);
    const mover = new THREE.Mesh(
      new THREE.SphereGeometry(0.42, 10, 10),
      new THREE.MeshBasicMaterial({ color: 0x7dffc0 })
    );
    mapGroup.add(mover);
    flightMovers.push({ curve, mover, t: Math.random(), speed: 0.22 + Math.random() * 0.14 });
  }
};

const loadCityFeatures = async (provinceFeature) => {
  const adcode = provinceFeature?.properties?.adcode;
  if (!adcode) return null;
  if (cityGeoCache.has(adcode)) return cityGeoCache.get(adcode);

  try {
    const response = await fetch(`https://geo.datav.aliyun.com/areas_v3/bound/${adcode}_full.json`);
    if (!response.ok) throw new Error(`city boundary ${adcode} load failed`);
    const geoJson = await response.json();
    const features = Array.isArray(geoJson?.features) ? geoJson.features : null;
    cityGeoCache.set(adcode, features);
    return features;
  } catch (error) {
    cityGeoCache.set(adcode, null);
    return null;
  }
};

const computeCityStats = (adcode, cityFeatures, provinceName) => {
  if (cityStatsByProvince.has(adcode)) return cityStatsByProvince.get(adcode);
  const cityStats = new Map();
  const provinceStations = stationsByProvinceName.value.get(provinceName) || [];

  for (const feature of cityFeatures) {
    cityStats.set(normalizeFeatureName(feature), 0);
  }

  for (const station of provinceStations) {
    const lon = Number(station.lon);
    const lat = Number(station.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    const city = cityFeatures.find((feature) => geoContains(feature, [lon, lat]));
    if (!city) continue;
    const cityName = normalizeFeatureName(city);
    cityStats.set(cityName, (cityStats.get(cityName) || 0) + 1);
  }

  cityStatsByProvince.set(adcode, cityStats);
  return cityStats;
};

const addFallbackStationPillars = () => {
  const provinceStations = stationsByProvinceName.value.get(focusedProvince.value) || [];
  const validStations = provinceStations
    .filter((row) => Number.isFinite(Number(row.lon)) && Number.isFinite(Number(row.lat)))
    .slice(0, 120); // 稍微增加一点数量
  if (!validStations.length) return;

  const material = new THREE.MeshBasicMaterial({
    color: 0x63f6ef,
    transparent: true,
    opacity: 0.55 // 恢复光柱透明度
  });

  for (const row of validStations) {
    const base = lonLatToVector(row.lon, row.lat, FLAT_MAP_DEPTH + 0.03);
    const pvpi = Number(row.PVPI || 0);
    const height = 3 + Math.min(9, Math.max(0, pvpi) / 16);
    
    // 使用 CylinderGeometry 恢复圆形光柱，更美观
    const pillar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.09, 0.16, height, 14, 1, true),
      material
    );
    
    // 圆柱默认沿Y轴，绕X轴旋转90度让它沿Z轴（垂直于地图）
    pillar.rotation.x = Math.PI / 2;
    pillar.position.set(base.x, base.y, base.z + height / 2);
    mapGroup.add(pillar);
  }
};

const initScene = () => {
  const root = rootRef.value;
  // 使用布局尺寸（clientWidth）而非 getBoundingClientRect，保证在 useFitScreen 缩放下渲染分辨率不受影响
  const width = root.clientWidth || 1;
  const height = root.clientHeight || 1;
  scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0a1730, 130, 280);
  camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 700);
  camera.up.set(0, 0, 1);
  camera.position.set(0, -92, 74);
  camera.lookAt(0, 0, 0);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(width, height);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  root.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enabled = profile.value.interactive;
  controls.enableDamping = true;
  controls.dampingFactor = 0.085;
  controls.rotateSpeed = 0.55;
  controls.zoomSpeed = 0.72;
  controls.enablePan = true; // 启用拖动/平移功能
  controls.keyPanSpeed = 40;
  controls.minDistance = 36;
  controls.maxDistance = 190;
  controls.minPolarAngle = 0.12;
  controls.maxPolarAngle = 1.28;
  controls.target.set(0, 0, 2);
  controls.update();

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();
  clock = new THREE.Clock();

  scene.add(new THREE.AmbientLight(0xcfe6ff, 1.0));
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.2);
  keyLight.position.set(22, -38, 78);
  scene.add(keyLight);
  const rimLight = new THREE.PointLight(0x9fd4ff, 1.45, 160);
  rimLight.position.set(-42, 28, 48);
  scene.add(rimLight);

  buildMap(false);

  if (profile.value.interactive) {
    root.addEventListener("pointerdown", handlePointerDown);
    root.addEventListener("pointermove", handlePointerMove);
    root.addEventListener("pointerup", handlePointerUp);
    root.addEventListener("pointerleave", handlePointerLeave);
    root.addEventListener("click", handleClick);
  }
  resizeObserver = new ResizeObserver(handleResize);
  resizeObserver.observe(root);
  animate();
};

const setPointer = (event) => {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
};

const intersectProvince = () => {
  raycaster.setFromCamera(pointer, camera);
  return raycaster.intersectObjects(provinceMeshes, false)[0] || null;
};

const setHover = (mesh) => {
  if (hoverMesh === mesh) return;
  if (hoverMesh) {
    hoverMesh.material[0].emissiveIntensity = hoverMesh.userData.originalEmissive ?? 0.2;
  }
  hoverMesh = mesh;
  if (hoverMesh) {
    hoverMesh.userData.originalEmissive = hoverMesh.material[0].emissiveIntensity;
    hoverMesh.material[0].emissiveIntensity = 0.62;
    const isCity = Boolean(hoverMesh.userData.isCityFeature);
    hoverInfo.value = {
      visible: true,
      province: hoverMesh.userData.displayName || hoverMesh.userData.province,
      count: Number(hoverMesh.userData.count || 0).toLocaleString("zh-CN"),
      isCity: isCity
    };
  } else {
    hoverInfo.value = { visible: false, province: "", count: 0, isCity: false };
  }
};

const handlePointerMove = (event) => {
  if (pointerDown) {
    const distance = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
    didDrag = didDrag || distance > 5;
    if (didDrag) {
      setHover(null);
      return;
    }
  }
  setPointer(event);
  const hit = intersectProvince();
  const mesh = hit?.object || null;
  setHover(mesh);
  if (hoverLabelRef.value && mesh) {
    const rect = rootRef.value.getBoundingClientRect();
    const scale = rect.width / (rootRef.value.clientWidth || 1) || 1;
    hoverLabelRef.value.style.left = `${(event.clientX - rect.left) / scale + 14}px`;
    hoverLabelRef.value.style.top = `${(event.clientY - rect.top) / scale - 8}px`;
  }
};

const handlePointerDown = (event) => {
  pointerDown = { x: event.clientX, y: event.clientY };
  didDrag = false;
};

const handlePointerUp = () => {
  pointerDown = null;
};

const handlePointerLeave = () => {
  pointerDown = null;
  setHover(null);
};

const emitPickFromHit = (hit, mesh) => {
  if (!hit?.point || !projection || !mapGroup) return;
  const localPoint = hit.point.clone();
  mapGroup.worldToLocal(localPoint);
  const inverted = projection.invert([localPoint.x, -localPoint.y]);
  if (!inverted) return;
  const [lon, lat] = inverted;
  if (lon >= LON_RANGE.west && lon <= LON_RANGE.east && lat >= LON_RANGE.south && lat <= LON_RANGE.north) {
    emit("map-pick", { lon, lat, province: mesh?.userData?.province || focusedProvince.value || "" });
  }
};

const handleClick = (event) => {
  if (didDrag) {
    didDrag = false;
    return;
  }
  // 如果用户启用了平移功能，额外检查是否有相机位置变化（防止误触点击）
  setPointer(event);
  const hit = intersectProvince();
  const mesh = hit?.object || null;
  if (!mesh) return;

  emitPickFromHit(hit, mesh);
  if (!focusedProvince.value || focusedProvince.value !== mesh.userData.province) {
    enterProvince(mesh);
  }
};

const enterProvince = async (mesh) => {
  const province = mesh.userData.province;
  const count = mesh.userData.count;
  const provinceFeature = mesh.userData.feature;
  const adcode = provinceFeature?.properties?.adcode || null;
  focusedProvince.value = province;
  focusedProvinceAdcode = adcode;
  drilldownFeatures.value = null;
  cityBoundaryFailed = false;
  emit("province-focus", { province, count });
  buildMap(true);
  const cityFeatures = await loadCityFeatures(provinceFeature);
  if (focusedProvince.value === province && cityFeatures?.length) {
    drilldownFeatures.value = cityFeatures;
    buildMap(true);
  }
};

const resetView = () => {
  focusedProvince.value = "";
  focusedProvinceAdcode = null;
  drilldownFeatures.value = null;
  cityBoundaryFailed = false;
  emit("province-focus", { province: "", count: 0 });
  buildMap(true);
};

const fitCameraToMap = (animated = true) => {
  if (!camera || !mapGroup || !controls) return;
  const box = new THREE.Box3().setFromObject(mapGroup);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, 1);
  
  // 统一省级地图显示大小，根据地图尺寸动态调整
  const isProvinceView = Boolean(focusedProvince.value);
  let distance;
  if (isProvinceView) {
    // 省级视图使用固定的相对大小
    distance = clamp(maxDim * 1.6, 40, 65);
  } else {
    // 全国视图保持原逻辑
    distance = clamp(maxDim * 0.84, 38, 112);
  }
  
  // 将地图向下移动一些，避免被标题遮挡
  const yOffset = isProvinceView ? 0 : 12;
  const target = new THREE.Vector3(center.x, center.y + yOffset, Math.max(1.8, center.z * 0.28));
  const position = new THREE.Vector3(center.x, center.y - distance * 0.42 + yOffset, target.z + distance);

  controls.minDistance = focusedProvince.value ? 16 : 28;
  controls.maxDistance = focusedProvince.value ? 120 : 168;

  if (!animated) {
    camera.position.copy(position);
    controls.target.copy(target);
    controls.update();
    return;
  }

  gsap.to(camera.position, {
    x: position.x,
    y: position.y,
    z: position.z,
    duration: 0.72,
    ease: "power3.out",
    onUpdate: () => controls.update()
  });
  gsap.to(controls.target, {
    x: target.x,
    y: target.y,
    z: target.z,
    duration: 0.72,
    ease: "power3.out",
    onUpdate: () => controls.update()
  });
};

const updateLabels = () => {
  if (!labelLayerRef.value || !rootRef.value || !projection || !camera) return;
  const width = rootRef.value.clientWidth;
  const height = rootRef.value.clientHeight;
  
  labelItems.forEach(({ el, lon, lat }) => {
    // 确保有有效的经纬度
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      el.style.opacity = "0";
      return;
    }
    
    // 步骤1：经纬度 -> 3D本地坐标
    const localPos = lonLatToVector(lon, lat, FLAT_MAP_DEPTH + 0.1);
    
    // 步骤2：本地坐标 -> 世界坐标
    const worldPos = localPos.clone();
    if (mapGroup) {
      mapGroup.localToWorld(worldPos);
    }
    
    // 步骤3：世界坐标 -> 标准化设备坐标(NDC)
    const ndcPos = worldPos.clone().project(camera);
    
    // 检查是否在视锥体内
    const inFrustum = ndcPos.z >= -1 && ndcPos.z <= 1 && 
                     ndcPos.x >= -1 && ndcPos.x <= 1 && 
                     ndcPos.y >= -1 && ndcPos.y <= 1;
    
    if (!inFrustum) {
      el.style.opacity = "0";
      return;
    }
    
    // 步骤4：NDC -> 屏幕像素坐标
    const screenX = (ndcPos.x * 0.5 + 0.5) * width;
    const screenY = (-ndcPos.y * 0.5 + 0.5) * height;
    
    // 边界检查（稍微放宽）
    const inBounds = screenX >= -100 && screenX <= width + 100 && 
                     screenY >= -100 && screenY <= height + 100;
    
    if (!inBounds) {
      el.style.opacity = "0";
      return;
    }
    
    // 更新标签
    el.style.opacity = "0.95";
    el.style.transform = `translate(${screenX}px, ${screenY}px) translate(-50%, -50%)`;
  });
};

const animate = () => {
  animationId = requestAnimationFrame(animate);
  const delta = clock.getDelta();
  const elapsed = clock.elapsedTime;
  if (pillarMaterial) pillarMaterial.opacity = 0.4 + Math.sin(elapsed * 2.1) * 0.18;
  for (const flight of flightMovers) {
    flight.t = (flight.t + delta * flight.speed) % 1;
    flight.mover.position.copy(flight.curve.getPoint(flight.t));
  }
  if (controls) controls.update();
  if (labelItems.length) updateLabels();
  renderer.render(scene, camera);
};

const handleResize = () => {
  if (!rootRef.value || !camera || !renderer) return;
  // 使用布局尺寸（clientWidth）：transform 缩放不改变布局尺寸，渲染分辨率保持稳定
  const width = rootRef.value.clientWidth || 1;
  const height = rootRef.value.clientHeight || 1;
  // 容器不可见（宽高为 0）时跳过，避免相机 aspect 变为 NaN
  if (width < 10 || height < 10) return;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
  fitCameraToMap(false);
};

watch(
  () => [props.geoJson, props.stats, props.stations, props.mode, props.provincePvpi],
  async () => {
    cityStatsByProvince.clear();
    await nextTick();
    if (scene && props.geoJson) buildMap(false);
  },
  { deep: false }
);

onMounted(() => {
  nextTick(initScene);
});

onBeforeUnmount(() => {
  cancelAnimationFrame(animationId);
  resizeObserver?.disconnect();
  if (profile.value.interactive) {
    rootRef.value?.removeEventListener("pointerdown", handlePointerDown);
    rootRef.value?.removeEventListener("pointermove", handlePointerMove);
    rootRef.value?.removeEventListener("pointerup", handlePointerUp);
    rootRef.value?.removeEventListener("pointerleave", handlePointerLeave);
    rootRef.value?.removeEventListener("click", handleClick);
  }
  clearSceneObjects();
  controls?.dispose();
  if (renderer) {
    renderer.dispose();
    renderer.domElement.remove();
  }
});

defineExpose({ resetView });
</script>
