/// <reference types="node" />
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { formatDistance, formatDuration, formatPace, haversineM, projectRoute, routeDistanceM, type Fix } from '../src/lib/geo.ts';

const M_PER_DEG = (2 * Math.PI * 6_371_008.8) / 360;

function walk(n: number, stepM: number, dtS: number, segment = 0, seq0 = 0, lat0 = -26.2): Fix[] {
  return Array.from({ length: n }, (_, i) => ({
    seq: seq0 + i, segment, t: 1_700_000_000_000 + dtS * 1000 * i, lat: lat0 + (stepM * i) / M_PER_DEG, lon: 28.04, accuracy: 5,
  }));
}

test('haversine matches the backend (1° of latitude)', () => {
  assert.ok(Math.abs(haversineM(0, 0, 1, 0) - M_PER_DEG) < 1);
});

test('same filtering as the server: accuracy, jumps, jitter', () => {
  const fixes = walk(11, 7, 5); // 70 m
  fixes[3].accuracy = 80;
  fixes[6].lat += 0.01;
  fixes.push({ seq: 99, segment: 0, t: fixes[10].t + 10_000, lat: fixes[10].lat + 0.5 / M_PER_DEG, lon: 28.04, accuracy: 5 });
  assert.ok(Math.abs(routeDistanceM(fixes, 'walking') - 70) < 0.5);
});

test('pauses never add distance', () => {
  const total = routeDistanceM([...walk(5, 7, 5), ...walk(5, 7, 5, 1, 5, -26.19)], 'walking');
  assert.ok(Math.abs(total - 56) < 0.5);
});

test('formatting', () => {
  assert.equal(formatPace(1000, 342), '5:42 /km');
  assert.equal(formatPace(5, 100), null);
  assert.equal(formatDuration(59), '0:59');
  assert.equal(formatDuration(3725), '1:02:05');
  assert.equal(formatDistance(850), '850 m');
  assert.equal(formatDistance(5234), '5.23 km');
  assert.equal(formatDistance(1609.344, 'imperial'), '1.00 mi');
});

test('route projection fits the box and splits segments', () => {
  const pts = [...walk(5, 50, 5), ...walk(5, 50, 5, 1, 5, -26.19)].map((f) => ({ lat: f.lat, lon: f.lon + f.seq * 1e-4, segment: f.segment }));
  const lines = projectRoute(pts, 300, 200);
  assert.equal(lines.length, 2);
  for (const xy of lines.join(' ').split(' ')) {
    const [x, y] = xy.split(',').map(Number);
    assert.ok(x >= 0 && x <= 300 && y >= 0 && y <= 200, xy);
  }
});
