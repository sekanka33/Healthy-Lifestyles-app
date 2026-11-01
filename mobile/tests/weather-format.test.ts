/// <reference types="node" />
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { coarse, conditionGlyph, formatTemp, formatWind, outdoorVerdict } from '../src/lib/weather-format.ts';

test('temperature and wind follow the unit setting', () => {
  assert.equal(formatTemp(21.6), '22°C');
  assert.equal(formatTemp(0, 'imperial'), '32°F');
  assert.equal(formatTemp(null), '—');
  assert.equal(formatWind(5), '18 km/h');
  assert.equal(formatWind(5, 'imperial'), '11 mph');
});

test('condition glyphs', () => {
  assert.equal(conditionGlyph(211), '⛈️');
  assert.equal(conditionGlyph(500), '🌧️');
  assert.equal(conditionGlyph(800, false), '🌙');
  assert.equal(conditionGlyph(804), '☁️');
});

test('verdicts and coordinate coarsening', () => {
  assert.match(outdoorVerdict('poor'), /indoors/);
  assert.equal(coarse(-26.204103), -26.2);
  assert.equal(coarse(28.047305), 28.05);
});
