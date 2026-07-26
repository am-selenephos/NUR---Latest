# UI test oracle correction — scroll containment

Ordered after the founder's finding that `scrollHeight > clientHeight` remains true under
`overflow: hidden` and therefore cannot prove scrollability. No CSS was changed until the
corrected tests were shown to fail on the old implementation and pass on the new one.

Audit: `docs/v9/TEST_ORACLE_AUDIT.csv` — 16 assertions, 8 `FALSE_POSITIVE_REPLACED`,
2 `BAD_ORACLE_REPLACED`, 2 `WEAK_ORACLE_REPLACED`, 2 `MEASUREMENT_ONLY`, 1 `VALID`,
1 `VALID_BUT_NARROW`.

## INVALIDATED_PASS_CLAIMS

Every one of these is withdrawn. None of them was ever evidence of anything.

1. **"the transcript scrolls inside itself"** — rested on `scrollHeight > clientHeight + 4`,
   which is true under `overflow: hidden`.
2. **"the page does not scroll"** — rested on `getComputedStyle(.nur-viewport).overflowY === 'hidden'`,
   a declaration on one element. A different ancestor scrolling satisfies it.
3. **"the composer stays visible"** — rested on a bounding-box comparison, which passes when the
   element is covered, `visibility: hidden`, `opacity: 0`, or clipped.
4. **"the journal draft scrolls inside itself"** — same defect as (1) on the textarea.
5. **"the transcript is big enough"** — `streamH > 400` measures size, never reachability.
6. **"the scroller is a scroller"** — `getComputedStyle(stream).overflowY === 'auto'` is a
   declaration, not a capability.
7. **Worse than all of the above: the readings did not describe the build.** The `vite preview`
   server had been reused across sessions and was serving a stale `dist`. The polish stylesheet in
   the served bundle contained neither the holographic section nor the scroll fix — verified by
   reading the injected `<style>` in the universe frame. So the earlier PASS claims were taken
   against code that was not present. **The scroll fix had never actually run in a browser when it
   was reported as working.**

## FALSE_POSITIVE_TESTS_FOUND

`e2e/v8-chatbox-scroll.spec.ts` — 6 of its 9 assertions were geometry-only or declaration-only.

Two further false positives were in **my own replacement tests**, and are recorded rather than
quietly fixed:

- the first draft proved end-reachability by assigning `scrollTop`, which works under
  `overflow: hidden` — it carried the exact defect it was written to remove;
- the journal `atEnd` check used an 8px tolerance where the browser legitimately stops one
  `padding-bottom` short (measured 6433 of 6456), so it failed a correct build.

`e2e/v8-cpu-budget.spec.ts` and `e2e/v8-star-brain-perf.spec.ts` remain **unreworked** — the
5-sample median/p95/worst requirement is not done. See OPEN_UI_REGRESSIONS.

## CORRECTED_TESTS

`apps/web/e2e/v8-chatbox-scroll.spec.ts`, rewritten. Every claim is now driven by a real gesture:

| Claim | How it is now proven |
| --- | --- |
| the scroller moves | `page.mouse.wheel()` ×8; `Control+End` for the draft; `Input.synthesizeScrollGesture` with `gestureSourceType: "touch"` on phone widths |
| the page does not move | `documentElement.scrollTop`, `body.scrollTop` and **every ancestor** of the scroller compared before and after |
| the end is reachable | wheel until motion stops, then require the true scroll bottom **and** the last message's bottom edge on screen |
| the action stays usable | `elementFromPoint` at the control's centre must hit-test back to it, plus `visibility`/`display`/`opacity`/above-the-fold checks |

Touch uses CDP rather than a hand-dispatched `TouchEvent`: a synthetic `TouchEvent` does not
scroll anything, so it would have been another false oracle.

Viewports: desktop 1440×900, short desktop 1280×640, mobile 390×844, mobile-keyboard 390×400.
Screenshots and video per viewport in `proof/v11-scroll-behaviour/{OLD,FIXED}/`.

## OLD_IMPLEMENTATION_RESULT

Old = the scroll section as it stood at `d6a9d1b` (`#talk-stream { max-height: calc(100vh - 600px) }`),
restored into the file, rebuilt from a clean `dist`.

**4 of 4 viewports FAIL.**

- desktop, short-desktop journal: `.nur-viewport` scrolled during the gesture — the page moved,
  which is the founder's original complaint
- mobile-keyboard talk: `scrollerDelta 0`, end not reachable, composer not hit-testable
- the journal field was 178px tall on a 900px window

## FIXED_IMPLEMENTATION_RESULT

**4 of 4 viewports PASS.** `pageDelta 0` and `ancestorsThatMoved []` everywhere.

| viewport | talk scroll | journal scroll | page moved | ancestors moved | end reachable | action hit-testable |
| --- | --- | --- | --- | --- | --- | --- |
| desktop 1440×900 | 1760px | 6200px | 0 | none | yes | yes |
| short desktop 1280×640 | 1760px | 6445px | 0 | none | yes | yes |
| mobile 390×844 | 1760px | 8401px | 0 | none | yes | yes |
| mobile-keyboard 390×400 | 1760px | 8424px | 0 | none | yes | yes |

### What the fix actually is

Three previous attempts subtracted a constant from `100dvh`. That could never work, and the
measurement says why: **the space above the layout is not a constant.** The block above it is
~135px on a 1440×900 desktop and **269px on a 390×844 phone**, because the heading wraps. So
`calc(100dvh - 318px)` was 35px too tall on a phone and the overflow simply moved up one
ancestor — the page scrollbar reappearing a level higher.

No constant is subtracted any more. `.nur-viewport` is the one box whose height the browser
already knows, and every box below it derives its size from that box:

- `.nur-viewport` → flex column, `overflow: hidden`
- `#page-*.active` and the layout → `flex: 1 1 0` (**not** `auto` — with `auto` the child's
  `height: 100%` fell back to content height, measured as a 429px chamber inside a 339px layout,
  putting the composer 90px under the fold)
- the layout → `grid-template-rows: minmax(0, 1fr)`, because canonical leaves the row implicit and
  it sized to max-content
- the chamber/pad → fill the row; the transcript and the textarea are the only scrollers
- `.nur-shell` / `.nur-main` → `min-height: 0`, which is what stops the collapse-to-38px failure
  from an earlier attempt

Phone-specific, all measured rather than guessed: the heading is capped at `13dvh`, and the
context rail gets its own bounded scroll region instead of overflowing the layout — the rail
overflowing is what let the browser scroll an ancestor to bring the caret into view.

## MANUAL_BROWSER_RESULT

Driven in a real Chromium against the real API and a live seeded owner, not mocks.

- Blue tint: the panel base was already neutral dark glass; the surviving blue was the sheen's
  midpoint stop, the fog's first radial, and canonical's `rgba(100,100,255,.14)` panel glow used
  8×. All three replaced — the spectrum now runs gold → rose → violet → teal → green → gold and
  never lands on blue.
- Send button: measured **56×46 before, 132×46 after**, with 26px horizontal padding and a 10px
  gap between the star and the word. My first attempt targeted `.composer-action--send`, which is
  not the control in use; the real one is `.thought-send-button.send-holo-pill`, confirmed by
  enumerating the buttons inside `.talk-composer`.
- Composer at 1280×640: bottom edge **730px → 585px** in a 640px window, and `elementFromPoint`
  now hit-tests back to it.

## OPEN_UI_REGRESSIONS

Honest and unclosed:

1. **Performance specs not reworked.** `v8-cpu-budget.spec.ts` and `v8-star-brain-perf.spec.ts`
   still take a single sample. The 5-run median/p95/worst/baseline requirement is **not done**.
2. **The context rail is hidden at mobile-keyboard sizes** (`max-height: 620px` and phone width).
   That is a real functional trade-off I made to keep the transcript usable in 340px of height,
   not a free win. It should become a disclosure rather than a hide.
3. **The heading is clipped to 13dvh on phones**, so long headings truncate.
4. **Chromium only.** WebKit and Firefox are unproven; `:has()` and `dvh` behave differently enough
   to matter.
5. **F001 still open (P0):** six Universe lenses still render effectively the same page.
6. **Target sizes unmeasured** against WCAG 2.2 SC 2.5.8 (24×24 AA, not the 44×44 in the earlier
   audit, which is Apple HIG).
7. The `mobile-keyboard` viewport is a proxy — a resized window, not a real on-screen keyboard.
