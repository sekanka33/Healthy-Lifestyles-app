/// <reference types="node" />
// Run with: npm test   (Node's built-in test runner; Node strips the TypeScript types)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  bubbleAt,
  countAt,
  fillFraction,
  glassPath,
  innerSpanAt,
  surfaceY,
  wavePath,
} from '../src/components/glass-math.ts';

const G = { aspect: 0.66, baseRatio: 0.67, rimRadiusRatio: 0.015, baseRadiusRatio: 0.09, markerRatio: 0.19, maxFill: 0.94 };

test('fill follows intake / goal and caps at maxFill', () => {
  assert.equal(fillFraction(0, 2000, G.maxFill), 0);
  assert.equal(fillFraction(1000, 2000, G.maxFill), 0.47);
  assert.equal(fillFraction(2000, 2000, G.maxFill), 0.94);
  assert.equal(fillFraction(9000, 2000, G.maxFill), 0.94); // over goal never overflows the rim
  assert.equal(fillFraction(-50, 2000, G.maxFill), 0);
  assert.equal(fillFraction(500, 0, G.maxFill), 0); // no goal yet -> no NaN
  assert.equal(fillFraction(Number.NaN, 2000, G.maxFill), 0);
});

test('surface sits at the right height', () => {
  assert.equal(surfaceY(300, 0), 300);
  assert.equal(surfaceY(300, 0.5), 150);
  assert.equal(surfaceY(300, 1.5), 0);
});

test('glass tapers from full rim to the measured base width', () => {
  const [l0, r0] = innerSpanAt(0, 200, 300, G.baseRatio);
  const [l1, r1] = innerSpanAt(300, 200, 300, G.baseRatio);
  assert.deepEqual([l0, r0], [0, 200]);
  assert.ok(Math.abs(r1 - l1 - 200 * G.baseRatio) < 1e-9);
  const d = glassPath(200, 300, G);
  assert.match(d, /^M/);
  assert.match(d, /Z$/);
  assert.equal((d.match(/Q/g) ?? []).length, 4); // four rounded corners
});

test('wave stays within its amplitude band and closes at the bottom', () => {
  for (const phase of [0, 1, 2.5, 6]) {
    const d = wavePath(200, 300, 150, 4, phase);
    const ys = [...d.matchAll(/L([\d.]+),([\d.]+)/g)].map((m) => Number(m[2])).filter((y) => y !== 300);
    assert.ok(ys.length > 20);
    for (const y of ys) assert.ok(y >= 150 - 4 * 1.35 - 1e-6 && y <= 150 + 4 * 1.35 + 1e-6, `y=${y}`);
    assert.match(d, /L200,300 Z$/);
  }
});

test('flat water when amplitude is zero (reduced motion)', () => {
  const ys = [...wavePath(100, 200, 80, 0, 3).matchAll(/L[\d.]+,([\d.]+)/g)].map((m) => Number(m[1]));
  assert.ok(ys.every((y) => y === 80 || y === 200));
});

test('bubbles rise from the base, fade, and never break the surface', () => {
  const start = bubbleAt(0, 290, 100, 4);
  const mid = bubbleAt(0.5, 290, 100, 4);
  const end = bubbleAt(0.999, 290, 100, 4);
  assert.equal(start.cy, 290);
  assert.equal(start.opacity, 0);
  assert.ok(mid.cy < 290 && mid.cy > 100 && mid.opacity > 0.8);
  assert.ok(end.cy >= 100 + 12 && end.opacity < 0.01);
  assert.equal(bubbleAt(0.5, 290, 285, 4).opacity, 0); // almost empty glass: no bubbles
});

test('count-up eases out and lands exactly on the target', () => {
  assert.equal(countAt(0, 250, 0), 0);
  assert.equal(countAt(0, 250, 1), 250);
  assert.ok(countAt(0, 250, 0.5) > 125); // ease-out: past halfway at half time
  assert.equal(countAt(500, 250, 1), 250); // also counts down (undo)
});
