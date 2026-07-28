# Resolution sweep and Entry frame-budget finding — 2026-07-28

Measured on the built bundle, headed Chromium, one commit. Frame rate is
compositor-presented frames via CDP `Page.screencastFrame`, not a rAF counter:
rAF inside the stage iframe is throttled by Chromium and reported 7–12 Hz on
desktop against 36–70 Hz on mobile, an inversion that is a measurement artifact
rather than a product fact.

## Density now holds across every resolution

Star density per unit area is the thing that was broken — a fixed particle count
spread over a large screen produced an empty sky. After scaling density with
viewport area, lit-pixel density per 100k canvas pixels is flat across the range:

| viewport | dpr | particles | lit/100k px |
| --- | --- | --- | --- |
| 3840×2160 | 1 | 3790 | — |
| 2560×1440 | 1 | 3811 | 70,335 |
| 2552×1412 | 1 | 3898 | 72,695 |
| 1920×1080 | 1 | 2308 | 78,733 |
| 1600×1000 | 1.46 | 1752 | 66,910 |
| 1440×900 | 1.5 | 1860 | 74,536 |
| 1366×768 | 1 | 1752 | 75,562 |
| 1280×720 | 1 | 1752 | 78,958 |
| 1024×1366 | 1.5 | 1773 | 73,248 |
| 834×1112 | 1.5 | 1860 | 82,048 |
| 430×932 | 1.5 | 982 | 67,397 |
| 393×852 | 1.5 | 982 | 70,520 |
| 360×640 | 1.5 | 982 | 77,276 |

67k–82k across a 30× area range. No viewport loses the field, and the wordmark
does not overlap the hero copy at any of them.

## Entry frame rate is the open defect

| viewport | presented FPS |
| --- | --- |
| 3840×2160 | 8.2 |
| 2560×1440 | 7.6 |
| 1920×1080 | 9.6 |
| 1440×900 | 8.0 |
| 393×852 | 39.4 |

Desktop sits at 8–10 FPS against a ≥55 target. Mobile is fine, because phone
widths are bounded at 33ms and carry 982 particles.

### It is not the canvases

A/B at 1920×1080, hiding one canvas at a time:

```
baseline (all three)   8.7 FPS
brain hidden           7.7 FPS
galaxy hidden          8.2 FPS
```

Removing either canvas changes nothing. The frame budget is not going to canvas
rendering, which also rules out particle count as the primary cause — density
scaling did not create this.

### It is CSS blur

```
total elements       576
running animations    22
star-seal hosts       12
svg nodes              0
elements with blur() 127
```

The DOM is small and the animation count is low — neither matches the earlier
report of ~2,777 running animations and ~6,357 elements, so that particular
finding does not reproduce here. **127 elements carrying a `blur()` filter** is
the outlier. Each blurred element forces its own offscreen render pass, and at
1920×1080 that is enough to explain an 8 FPS ceiling on its own.

This is repair item 7 in the founder's own order — "excessive DPR/particles/
blur/filter/shadow" — and it is the next thing to fix. It is recorded rather
than patched because reducing blur changes the material identity of the glass
surfaces, and that is a founder visual decision, not a silent optimisation.

### Not reproduced

The 4K run errored once with a closed target during the first sweep and
completed normally at 8.2 FPS on the second. Treated as harness flake, not a
product crash, until it reproduces.
