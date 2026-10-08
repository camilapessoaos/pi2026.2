/**
 * Métricas climáticas exibidas pelo front.
 *
 * O canal ThingSpeak 3499301 tem apenas dois campos ativos e o backend Java só persiste estes:
 *   field1 -> temperatura (°C)
 *   field2 -> umidade (%)
 * Qualquer outra métrica que chegue da API é ignorada pelas telas.
 */
export const CLIMATE_METRICS = Object.freeze({
  temperature: Object.freeze({
    key: 'temperature',
    label: 'Temperatura',
    unit: '°C',
    field: 'field1',
    aliases: Object.freeze(['temperature', 'temperaturec', 'tempc', 'temp']),
  }),
  humidity: Object.freeze({
    key: 'humidity',
    label: 'Umidade',
    unit: '%',
    field: 'field2',
    aliases: Object.freeze(['humidity', 'relativehumidity', 'airhumidity']),
  }),
});

export const CLIMATE_METRIC_KEYS = Object.freeze(Object.keys(CLIMATE_METRICS));

const normalizeName = (value) => String(value ?? '').toLowerCase().replaceAll('_', '');

/** Converte um nome vindo da API (ex.: "Temperature_C") na chave canônica, ou null se não for suportado. */
export function resolveMetricKey(name) {
  const normalized = normalizeName(name);
  return CLIMATE_METRIC_KEYS.find((key) => CLIMATE_METRICS[key].aliases.includes(normalized)) || null;
}

/** Rótulo de coluna/legenda, por exemplo "Temperatura (°C)". */
export function measurementLabel(key) {
  const metric = CLIMATE_METRICS[key];
  return metric ? `${metric.label} (${metric.unit})` : String(key);
}

/** [nomeNaAPI, metric] para a métrica canônica, ou null. */
export function climateMetricEntry(climate, key) {
  return Object.entries(climate?.metrics || {}).find(([name]) => resolveMetricKey(name) === key) || null;
}

export function climateMetric(climate, key) {
  return climateMetricEntry(climate, key)?.[1] || null;
}

/** Métricas suportadas presentes na resposta, em ordem canônica: [{ key, label, metric }]. */
export function climateMetricRows(climate) {
  return CLIMATE_METRIC_KEYS
    .map((key) => ({ key, label: CLIMATE_METRICS[key].label, metric: climateMetric(climate, key) }))
    .filter((row) => row.metric);
}

/** Série temporal de uma métrica canônica: { values, labels }, sempre com arrays (vazios se não houver dados). */
export function climateSeries(climate, key) {
  const entry = climateMetricEntry(climate, key);
  if (!entry) return { values: [], labels: [] };
  const [name] = entry;
  const values = [];
  const labels = [];
  (Array.isArray(climate?.series) ? climate.series : []).forEach((point) => {
    const raw = point.values?.[name];
    if (raw === null || raw === undefined || !Number.isFinite(Number(raw))) return;
    values.push(Number(raw));
    const date = new Date(point.timestamp);
    labels.push(Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(date));
  });
  return { values, labels };
}

/** Valor bruto de uma métrica canônica dentro de um ponto da série, ou null. */
export function climatePointValue(point, key) {
  const entry = Object.entries(point?.values || {}).find(([name]) => resolveMetricKey(name) === key);
  return entry ? entry[1] : null;
}
