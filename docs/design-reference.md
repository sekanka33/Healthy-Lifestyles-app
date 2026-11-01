# Design Reference — Hydration Screen

Source: `picture/69188.png` (852 × 1846 px, iPhone-class device, ≈ 2.17 px per pt).
This is the **only** reference image in the repository. Every screen in the app
reuses the tokens below so the product looks like one system.

Colours were sampled programmatically from the image (Pillow), not guessed.

## Colour tokens

| Token | Hex | Where it was sampled |
|---|---|---|
| `background` | `#FEFEFE` | Page background (effectively white) |
| `surface` | `#FFFFFF` | Close button, nav bar |
| `glassBody` | `#E8ECEC` | Empty part of the glass |
| `glassBodyEdge` | `#EAEDED` | Glass near rim |
| `water` | `#04C4D1` | Water body (mid + bottom identical → flat fill, no vertical gradient) |
| `waterBubble` | `#16CDD8` | Bubbles inside water (slightly lighter than water) |
| `waterMarker` | `#C6FAFD` | Circle that sits on the water surface |
| `navy` | `#0B1E37` | "160" numeral, drop icon (`#0B213C`), close X (`#091730`) |
| `navySoft` | `#293555` | "Pure hydration" caption |
| `navyMuted` | `#202D48` | Inactive tab icons/labels |
| `chip` | `#EEF0F2` | Volume chips background |
| `primary` | `#04C3D5` → `#02BED6` | + WATER button (very subtle horizontal gradient) |
| `primaryGlow` | `#04C4D1` @ ~30 % | Soft cyan shadow under + WATER button |
| `accentSoft` | `#D2FBFD` | "•••" overflow button background |
| `accentWash` | `#F4FEFE` | Small glass shortcut background |
| `accentIcon` | `#09CFDD` | Small glass icon |
| `tabActive` | `#06AAD6` | Active tab icon/label |
| `tabIndicator` | `#0499D2` | Active tab underline |

## Typography

Rounded geometric sans-serif. **Nunito** is the closest freely licensed match
(open "1", round bowls on "6"/"0").

| Role | Size (pt) | Weight |
|---|---|---|
| Intake numeral ("160") | ~64 | 800 |
| Unit ("ml") | ~28 | 800 |
| Caption ("Pure hydration") | ~18 | 600, `navySoft` |
| Chip label | ~17 | 700, `navy` |
| Button label ("+ WATER") | ~24 | 800, white, letter-spacing ~0.5 |
| Tab label | ~13 | 600 |

## Glass geometry (normalised, top-left origin)

Measured from row scans of the glass silhouette:

- Bounding box ≈ 385 × 582 px → aspect **0.66 : 1** (w : h).
- Rim width = 100 %; base width ≈ **67 %** of rim (tapered tumbler).
- Rim corners: small radius (~1.5 % of width).
- Base corners: large radius (~9 % of width) — soft rounded bottom.
- Water in the reference sits at **43 %** of glass height for 160 ml.
- A circular marker (`waterMarker` fill, navy drop glyph) rides on the water
  surface at horizontal centre; diameter ≈ 19 % of glass width.
- Water surface is a gentle, low-amplitude wave; 2 faint bubbles visible.
- No outline stroke: the glass is a flat filled shape, the water is clipped to it.

## Layout (pt, 393-pt-wide phone)

- Close/back button: 42 pt white circle, top-right, soft shadow.
- Glass: ~178 pt wide, centred, ~45 % of the content height.
- Volume chips: 75 × 36 pt pills, 15 pt gap, centred row.
- Action row: 48 pt circle (glass shortcut) · 180 × 62 pt pill (+ WATER) · 48 pt circle (•••).
- Tab bar: white, large top radius (~28 pt), active tab has 3 pt rounded underline.

## Motion (implemented in code, not in the static reference)

Implemented in `mobile/src/components/water-glass.tsx` (Reanimated, UI thread), with the pure
maths in `glass-math.ts` and unit tests in `mobile/tests/`. With the OS "reduce motion" setting on,
the level jumps straight to its value, the water is flat, and there are no bubbles or count-up.

- Water rises/falls with a spring (damping 16, stiffness 70) toward `min(intake / goal, 1) × maxFill`.
- Continuous low-amplitude surface ripple (two summed sines, 3.2 s period); a larger wave on each add (splash, decays over 1.2 s). The marker bobs with the surface.
- Three bubbles on staggered loops rise from the base and fade out before reaching the surface; none when the glass is nearly empty.
- Numeral counts up (or down on undo) with an ease-out over 550 ms, using tabular digits.
- Button scales to ~0.96 on press.
