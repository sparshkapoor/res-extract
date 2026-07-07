---
version: 1.1
name: res-extract-dark
description: A from-scratch dark design system built on two ideas held in tension. Chrome (nav, filter chips, search, progress, buttons) is Linear-style engineered precision — flat near-black surfaces, hairline borders, monospace for every number, tight negative tracking on headlines. Recipe cards and the recipe hero are genuine Apple-style liquid glass — frosted translucent panels over food photography, because glass only earns its shadow and blur when there's a photo behind it worth revealing. Headlines carry a third voice — Fraunces, an editorial serif (NYT Cooking / Food & Wine register) — held in the same tension: precision chrome stays Inter/mono, storytelling headlines go serif. One accent color, warm amber, used constantly and deliberately.

colors:
  canvas: "#0a0a0b"
  surface-1: "#141416"
  surface-2: "#1c1c1f"
  surface-3: "#242428"
  hairline: "rgba(255,255,255,0.08)"
  hairline-strong: "rgba(255,255,255,0.14)"
  text: "#f2f2f0"
  text-muted: "#98989d"
  text-faint: "#5c5c60"
  accent: "#f5a623"
  accent-strong: "#d9860a"
  accent-on: "#1a1006"
  glass-tint: "rgba(255,255,255,0.08)"
  glass-border-top: "rgba(255,255,255,0.25)"
  glass-border: "rgba(255,255,255,0.12)"
  glass-scrim: "rgba(0,0,0,0.55)"
  danger: "#e5484d"

typography:
  headline-display:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: 40px
    fontWeight: 700
    fontStyle: normal
    lineHeight: 1.05
    letterSpacing: -0.01em
  headline-display-sm:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: 24px
    fontWeight: 600
    fontStyle: normal
    lineHeight: 1.15
    letterSpacing: -0.005em
  headline-section-italic:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: 21px
    fontWeight: 600
    fontStyle: italic
    lineHeight: 1.2
    letterSpacing: 0em
  display-xl:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "clamp(44px, 12vw, 60px)"
    fontWeight: 700
    fontStyle: normal
    lineHeight: 0.98
    letterSpacing: -0.01em
    fontOpticalSizing: auto
  headline-xl:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 32px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: -0.025em
  headline-md:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 19px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.02em
  eyebrow:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 11px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: 0.08em
    textTransform: uppercase
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0
  body-strong:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: 0
  caption:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0
  data-lg:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: -0.01em
  data-sm:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0

rounded:
  xs: 6px
  sm: 10px
  md: 14px
  lg: 20px
  pill: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px

motion:
  spring: "{--ease-spring} = cubic-bezier(0.32, 0.72, 0, 1) — Apple's 'sheet' curve; drives press-scale, fade-in-up, scale-in, and every retuned component transition. GSAP call sites (hero-load-reveal) mirror this exact curve as a JS string, since GSAP eases aren't read from CSS custom properties — keep both in sync if this ever changes."
  fade-in-up: "opacity 0->1, translateY 12px->0, 550ms {motion.spring}"
  scale-in: "opacity 0->1, scale 0.92->1, 350ms {motion.spring} — sheet-like phase transitions (submit-button spinner morph, ProgressView checkmark pop); pair with a `key` change so React remounts and the animation replays"
  stagger-step: "60ms per sibling via --stagger-index"
  hover-lift: "translateY(-4px) scale(1.015), 200ms {motion.spring}"
  shimmer: "background-position sweep, 1.6s linear infinite"
  ambient-blobs: "two blurred (70px) amber/accent-strong radial blobs ({components.ambient-glow}) that translate+scale across independent 16s/20s ease-in-out loops, app-wide — not a subtle background-position drift, an actually-moving gradient; still one hue family (amber), not a second accent color"
  hero-load-reveal: "load-triggered (img.decode()/load event, not scroll) — hero image filter:blur(8px)->0 + scale(1.12)->1.0 over 900ms {motion.spring}, glass panel translateY/opacity settle 700ms {motion.spring} delayed 100ms. Plays once per mount regardless of scroll position — replaces hero-focus-pull, which stayed fully blurred at scroll position 0 (the reported 'thumbnail missing' bug)."
  hero-parallax: "GSAP ScrollTrigger scrub, created only after hero-load-reveal completes — hero image translateY 0->-8% + scale 1.0->1.06 as the hero exits the viewport. Never touches `filter`, so scrolling can't re-blur the image; neutral (matches hero-load-reveal's end state) at scroll progress 0."
  scroll-reveal: "GSAP ScrollTrigger — fade+rise as an element enters the viewport, recipe-detail ingredient rows and step cards only"
  reduced-motion: "single global @media (prefers-reduced-motion: reduce) rule disables all CSS animation/transition; GSAP call sites separately guard via lib/gsap.ts's prefersReducedMotion() since JS-driven tweens aren't reached by the CSS rule"

components:
  button-primary:
    backgroundColor: "{colors.accent-strong}"
    textColor: "#ffffff"
    typography: "{typography.body-strong}"
    rounded: "{rounded.pill}"
    padding: 11px 22px
  button-secondary:
    backgroundColor: transparent
    textColor: "{colors.accent}"
    border: "1px solid {colors.hairline-strong}"
    rounded: "{rounded.pill}"
    padding: 11px 22px
  glass-tile:
    backdropFilter: "blur(22px) saturate(165%)"
    backgroundColor: "{colors.glass-tint}"
    border: "1px solid {colors.glass-border}, top edge {colors.glass-border-top}"
    shadow: "0 20px 40px -12px rgba(0,0,0,0.45)"
    rounded: "{rounded.lg}"
  glass-tile-hover:
    backdropFilter: "blur(26px) saturate(180%)"
    transform: "translateY(-4px) scale(1.015)"
  glass-vibrant:
    backdropFilter: "blur(28px) saturate(190%) — {.vibrancy} utility class"
    backgroundColor: "rgba(255,255,255,0.1)"
    usage: "GlassCard variant=\"vibrant\" — a surface that wants more presence than glass-tile; still only over real photography/imagery per the glass-only-over-photos rule"
  recipe-thumbnail-tile:
    usage: "Shared glass-thumbnail tile component (RecipeThumbnailTile) behind both SavedRecipesList's grid and RecentStrip's horizontal rail — same photo + glass-caption treatment as glass-tile, two size presets (\"grid\" ~170px, \"strip\" ~80px square) tuned via caption font-size/padding only"
  precision-input:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.pill}"
    padding: 12px 18px
  filter-chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-muted}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.pill}"
    padding: 8px 16px
  filter-chip-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-on}"
    border: "1px solid {colors.accent}"
  ingredient-row:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    border-bottom: "1px solid {colors.hairline}"
    padding: 12px 16px
    note: "a small muted Ingredient.note (e.g. a unit-conversion aside, an 'optional' flag) renders inline after the name at {typography.caption} size, {colors.text-faint} — only when the backend actually sends one; never a placeholder"
  url-pill:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    border: "1px solid {colors.hairline}"
    rounded: "{rounded.pill}"
    padding: 16px 24px
    height: 56px
    focusGlow: "border -> {colors.accent}, plus 4px {colors.accent} ring at 15% opacity, 200ms {motion.spring}"
    usage: "UrlSubmitForm's URL field — the single highest-intent input on the landing screen, larger than {component.precision-input} to read as the primary action"
  skeleton:
    backgroundColor: "{colors.surface-2}"
    shimmerColor: "{colors.surface-3}"
    rounded: "{rounded.md}"
  metadata-icon-value:
    iconColor: "{colors.accent} on highlight, {colors.text-muted} otherwise"
    iconSize: 15px
    typography: "{typography.data-lg}"
    gap: 6px
  ambient-glow:
    layers: "two blurred circular blobs (::before/::after on .ambient-glow), amber (rgba(245,166,35,0.32)) and accent-strong (rgba(217,134,10,0.28)), 65vw/55vw, blur(70px)"
    animation: "{motion.ambient-blobs} — independent transform+scale keyframes per blob, not a shared one"
    containment: ".ambient-glow sets position:relative + isolation:isolate + overflow:hidden so blobs (z-index:-1) can drift past their own footprint without affecting page scroll size or floating above real content"
    usage: "applied via the `.ambient-glow` class app-wide, not hand-copied per screen"
---

## Overview

Two systems, one screen, never mixed on the same surface. **Precision mode** governs
every piece of chrome that doesn't sit on a photo: the URL-submit bar, the filter
chip row, the search input, the progress tracker, buttons, and any future settings
surface. It is flat — a three-step surface ladder (`{colors.surface-1}` →
`{colors.surface-2}` → `{colors.surface-3}`) plus hairline borders, no shadow, no
blur. **Glass mode** governs anything sitting directly over recipe photography: the
recipe grid tiles and the recipe-detail hero panel. It is the only place in the
system that uses `backdrop-filter`, translucency, and shadow — because a frosted
panel only reads as "glass" when there's something worth blurring behind it. A glass
treatment on a flat color panel is a `Do Not` in this system, not a style choice.

Warm amber (`{colors.accent}` — #f5a623) is the single interactive color: active
filter chips, focus rings, links, the one data highlight per screen (usually the
`cook_time_minutes` or the CTA). Numbers are never set in the prose typeface —
`cook_time_minutes`, `servings`, `calories`, `oven_temp_f`, and step indices always
render in `{typography.data-lg}` / `{typography.data-sm}` (JetBrains Mono). Headlines
carry negative tracking (`-0.02em` to `-0.03em`) at every size ≥ 19px — flat tracking
on a large headline is the single fastest AI-slop tell, and this system never does it.

**Key characteristics:**
- Near-black canvas (`{colors.canvas}` — #0a0a0b), never pure black — pure black
  flattens the glass blur's visual interest.
- One accent, used constantly: amber for active/interactive, never a second color.
- Precision chrome is flat and hairline-bordered; glass is reserved for photo-backed
  cards only — this boundary is the entire point of the system.
- Every number is monospace. Every headline is tight-tracked. Every eyebrow label is
  uppercase Inter 700 at 11px/0.08em — the only navigational typographic structure.
- Motion is never subtle to the point of invisibility: 12px translateY entrances,
  staggered by 60ms per sibling, real hover lift, shimmer skeletons, one global
  `prefers-reduced-motion` kill-switch.

## Colors

### Canvas & Surface Ladder (precision mode only)
- **Canvas** (`{colors.canvas}` — #0a0a0b): page background in every screen/phase.
- **Surface 1** (`{colors.surface-1}` — #141416): the first lift step — sticky
  header bar, the filter-chip row's containing strip.
- **Surface 2** (`{colors.surface-2}` — #1c1c1f): input fields, inactive filter
  chips, ingredient rows, step cards.
- **Surface 3** (`{colors.surface-3}` — #242428): hover/active state for anything
  living on Surface 2 (chip hover, pressed input).
- Depth between these three steps comes from the hex step itself plus a hairline
  border — never a shadow. Shadows are reserved for glass.

### Hairlines
- **Hairline** (`{colors.hairline}` — rgba(255,255,255,0.08)): default border on
  every precision-mode element — inputs, chips, ingredient-row dividers, card
  outlines in flat contexts.
- **Hairline Strong** (`{colors.hairline-strong}` — rgba(255,255,255,0.14)): used on
  `button-secondary`'s border and any hairline that needs to read against Surface 1.

### Text
- **Text** (`{colors.text}` — #f2f2f0): primary copy, headlines. Off-white, not pure
  white — softer against the near-black canvas.
- **Text Muted** (`{colors.text-muted}` — #98989d): secondary copy, inactive chip
  labels, captions, platform tags.
- **Text Faint** (`{colors.text-faint}` — #5c5c60): placeholder text, disabled
  states, the faintest tier.

### Accent — the one color
- **Accent** (`{colors.accent}` — #f5a623): active filter chip fill (paired with
  `{colors.accent-on}` text), focus rings, inline links, step-index numerals, the
  one data highlight per screen. Bright enough to read directly on `{colors.canvas}`
  with no contrast issue.
- **Accent Strong** (`{colors.accent-strong}` — #d9860a): solid CTA button fill.
  `{colors.accent}` itself is too light for white button text to clear AA contrast,
  so the button grammar deepens one step. Never used for anything but button fills.
- **Accent On** (`{colors.accent-on}` — #1a1006): near-black text used on top of any
  amber fill (active chips, accent-colored badges).

### Glass (photo-backed surfaces only)
- **Glass Tint** (`{colors.glass-tint}` — rgba(255,255,255,0.08)): the translucent
  white fill over the blurred photo. Never a dark scrim — a dark fill kills the
  "glass" read and turns the panel into an ordinary dark card with a blur filter
  wasted behind it.
- **Glass Border Top / Glass Border** (rgba(255,255,255,0.25) / rgba(255,255,255,0.12)):
  fakes the refracted highlight edge real glass has — brighter on the top edge,
  dimmer on the other three sides.
- **Glass Scrim** (`{colors.glass-scrim}` — rgba(0,0,0,0.55)): NOT part of the glass
  layer itself. Sits between the photo and the blur, as a `linear-gradient(to top, …,
  transparent 60%)`, only when the photo is bright enough to threaten text
  legibility. The glass panel stays translucent; the photo gets darkened, not the
  glass.

## Typography

### Font Families
- **Editorial**: Fraunces (400/500/600/700, italic + normal), loaded via Google
  Fonts. The storytelling voice — every headline that names a recipe or a section:
  the `res-extract` app title, grid-tile captions, the recipe-detail title, and the
  "Ingredients"/"Steps" section heads. Never used for functional chrome (buttons,
  inputs, eyebrow labels) — that boundary is what keeps the precision/editorial
  tension legible instead of muddled.
- **Prose**: Inter (400/500/600/700), loaded via Google Fonts. Body copy, captions,
  eyebrow labels, button labels — everything functional that isn't a number.
- **Data**: JetBrains Mono (400/600), loaded via Google Fonts. Every number that is
  data, full stop: `cook_time_minutes`, `servings`, `calories`, `oven_temp_f`, step
  index badges. Ingredient quantities stay in Inter (they're prose fragments like
  "1/2 cup", not standalone data values) — only the metadata row and step numerals
  are monospace.

### Scale

| Token | Size | Weight | Tracking | Use |
|---|---|---|---|---|
| `{typography.display-xl}` | clamp(44px, 12vw, 60px) | 700 serif, `opsz` auto | -0.01em | Landing hero headline only ("Reels in. / Recipes out.") |
| `{typography.headline-display}` | 40px | 700 serif | -0.01em | Recipe title on the detail hero |
| `{typography.headline-display-sm}` | 24px | 600 serif | -0.005em | `res-extract` app title, grid-tile captions |
| `{typography.headline-section-italic}` | 21px | 600 serif italic | 0em | Section heads: "Ingredients", "Steps" |
| `{typography.headline-xl}` | 32px | 700 | -0.03em | Reserved for future functional (non-editorial) large headings — currently unused now that the title moved to `headline-display` |
| `{typography.headline-lg}` | 24px | 700 | -0.025em | Reserved for future functional large sans headings |
| `{typography.headline-md}` | 19px | 600 | -0.02em | Reserved for future functional sans section heads |
| `{typography.eyebrow}` | 11px | 700 | 0.08em, uppercase | "Step N", "YouTube"/"Instagram" tag, any label-as-navigation |
| `{typography.body}` | 15px | 400 | 0 | Paragraph copy, instructions, ingredient names |
| `{typography.body-strong}` | 15px | 600 | 0 | Button labels, emphasized inline copy |
| `{typography.caption}` | 13px | 400 | 0 | Secondary metadata, timestamps, helper text |
| `{typography.data-lg}` | 15px | 600 | -0.01em | Metadata row on the recipe hero (time/servings/calories/oven temp) |
| `{typography.data-sm}` | 12px | 500 | 0 | Step-index badges, compact inline numbers |

### Principles
- **Editorial vs. precision is a typeface boundary, not a vibe.** If it names a
  recipe or a section ("Caramelized Onion One Tray Baked Pasta", "Ingredients"), it's
  Fraunces. If it's functional (a button label, an eyebrow tag, a data value), it's
  Inter or JetBrains Mono. Never mix a serif into chrome or a sans headline into
  storytelling copy — that's what keeps two typefaces reading as one coherent system
  instead of two unrelated ones stapled together.
- **Fraunces headlines don't use the sans tight-tracking rule.** Editorial serifs
  read better at looser (or even 0) tracking — `headline-display` sits at only
  `-0.01em`, `headline-section-italic` at `0em`. The `-0.02em`-to`-0.03em` rule below
  is specific to `{typography.headline-xl}`/`headline-lg`/`headline-md` (Inter).
- **Negative tracking is mandatory at ≥19px, forbidden below 13px** (Inter headline
  tokens only — see above). Flat tracking on a sans headline-sized element is the
  fastest tell this system exists to avoid.
- **Numbers are never Inter.** The instant a value is "data" (a count, a duration, a
  temperature), it moves to `{typography.data-lg}` or `{typography.data-sm}`.
- **Uppercase eyebrow labels are the only navigational structure.** No breadcrumbs,
  no tab underlines — a `{typography.eyebrow}` label ("Step 3", "YOUTUBE") is how
  the system marks position and category.
- Inter loads at 400/500/600/700 only — no 300 (too light to hold up on a near-black
  canvas at body sizes) and no 800+ (headlines get weight from tracking, not heft).

## Layout

- **Base unit:** 4px. Spacing snaps to `{spacing.xxs}` (4px) through `{spacing.xxl}`
  (48px).
- **Content width:** single column, `max-w-[560px]`, centered — this is a phone-width
  PWA (existing safe-area-inset handling, no horizontal scroll). The recipe grid is
  the one place layout goes multi-column: 2-up below 480px, up to 3-up above ~700px
  for the rare desktop-browser preview during development.
- **Card padding:** `{spacing.md}` (16px) inside glass tiles and ingredient rows;
  `{spacing.lg}` (24px) inside the detail-view section stack.
- **Gutters:** `{spacing.sm}` (12px) between grid tiles; `{spacing.xs}` (8px) between
  filter chips.

## Landing Composition

The idle/submitting/error phases render `LandingHero`, not a generic form-on-a-page —
a single vertical composition, top to bottom:

1. **Eyebrow** — `res-extract`, `{typography.eyebrow}`, stagger index 0.
2. **Headline** — `{typography.display-xl}`, two lines ("Reels in." / "Recipes
   out."), each line its own `fade-in-up` span (stagger indices 1-2) so they reveal
   one after the other, not as one block. This per-line reveal is plain CSS
   (`animate-fade-in-up` per span), so it's automatically reduced-motion-safe via
   the one global kill-switch — no extra JS guard needed.
3. **Support line** — one sentence, `{typography.body}` muted, stagger index 3.
4. **URL form** — `UrlSubmitForm`, using `{component.url-pill}` (56px, focus glow),
   stagger index 4.
5. **"View saved recipes" link** — stagger index 5.
6. **`RecentStrip`** (stagger index 6, then +0.5 per tile) — a horizontal rail of
   up to 8 most-recent extractions using `{component.recipe-thumbnail-tile}` at
   `size="strip"`, fetched from the same `GET /api/recipes` `SavedRecipesList`
   already uses. **Renders nothing at all** — no heading, no empty state — when
   there's no saved history yet; an empty rail with a label reads as broken, not
   "no recipes yet."

`processing`/`saved` phases keep the original small `res-extract` header
(`{typography.headline-display-sm}`) instead of the full hero — the hero's
purpose is specifically "convince a new/returning visitor to paste a URL," which
doesn't apply once they're mid-flow or browsing their own saved list.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| Flat | No shadow, no blur, hairline border only | Nav/header strip, filter chips, search input, progress tracker, ingredient rows, step cards |
| Surface step | Hex value change (`surface-1` → `surface-2` → `surface-3`) | The only "elevation" precision mode is allowed to use |
| Glass | `backdrop-filter: blur(22px) saturate(165%)` + translucent tint + gradient highlight border + `shadow-black/40`-territory drop shadow | Recipe grid tiles, recipe-detail hero panel — photo-backed surfaces only |
| Glass hover | Blur/saturate intensify (26px/180%), lift `-translateY(4px) scale(1.015)`, shadow deepens | Interactive glass tiles in the grid (not the static hero panel) |
| Glass vibrant | `backdrop-filter: blur(28px) saturate(190%)` (`{component.glass-vibrant}` / `GlassCard variant="vibrant"`) | A surface that wants more presence than standard glass-tile — still only over real photography/imagery, same rule as above |

**The rule, stated once so it can't drift:** if a panel isn't sitting over a photo,
it doesn't get blur or shadow. Depth on flat surfaces comes only from the surface
ladder and hairlines. Breaking this rule anywhere — a blurred settings panel, a
shadowed search bar — makes glass stop meaning anything as a signal.

## Shapes

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 6px | Step-index badges, small inline chips |
| `{rounded.sm}` | 10px | Step-card thumbnails, compact inputs |
| `{rounded.md}` | 14px | Skeleton blocks, ingredient-row group container |
| `{rounded.lg}` | 20px | Glass tiles (grid cards, hero panel) |
| `{rounded.pill}` | 9999px | All buttons, search input, filter chips — the "interactive" shape grammar |

## Components

**`button-primary`** — `{colors.accent-strong}` fill, white text, `{typography.body-strong}`,
`{rounded.pill}`, 11×22px padding. Press state: `scale(0.96)`, 150ms.

**`button-secondary`** — Transparent fill, `{colors.accent}` text, 1px
`{colors.hairline-strong}` border, `{rounded.pill}`. Used for "Back" / non-primary
actions.

**`glass-tile`** — The recipe-grid card and the recipe-hero panel. Photo fills the
container; the glass layer sits over the lower portion (grid tile) or lower third
(hero) containing title + metadata. `interactive` tiles (grid only) get
`glass-tile-hover` on `:hover`/`:focus-visible`.

**`precision-input`** — Search bar and URL-submit field. `{colors.surface-2}` fill,
`{colors.hairline}` border that upgrades to `{colors.accent}` on focus,
`{rounded.pill}`, 12×18px padding. Never blurred.

**`filter-chip`** — Platform/search filter row. Inactive: `{colors.surface-2}` fill,
`{colors.text-muted}` text, hairline border. Active: `{colors.accent}` fill,
`{colors.accent-on}` text, no border needed (fill provides contrast).

**`ingredient-row`** — Flat row, not a card-per-item. `{colors.surface-2}` background
across the whole list container, `{colors.hairline}` divider between rows (not
around each one). Ingredient name in `{typography.body}`; quantity/unit in
`{typography.body}` muted, right-aligned; a leading `~` marks `is_estimated`. If
`Ingredient.note` is present (a free-text aside relocated here by the backend's
normalizer — a unit conversion, an "optional" flag, "for the pan" — never a
placeholder), it renders inline right after the name at `{typography.caption}`
size, `{colors.text-faint}`. Omit the note span entirely when null; never render
an empty one.

**`step-card`** — Thumbnail (76×76px, `{rounded.sm}`) + text side by side on
`{colors.surface-2}`, flat, hairline border. Step index as an `{typography.eyebrow}`
label in `{colors.accent}` — not monospace at this size since it's a label
("Step 3"), not a standalone numeral; a standalone numeral badge (no "Step" word)
would use `{typography.data-sm}`.

**`skeleton`** — `{colors.surface-2}` block with a `{colors.surface-3}` gradient
sweeping left-to-right on a 1.6s linear infinite loop (`shimmer` keyframe). Sized to
match the exact dimensions of what it's replacing (grid tile, ingredient row).
Never a flat opacity pulse.

## Motion

- **Spring, everywhere a duration exists.** `{motion.spring}` (`--ease-spring`,
  Apple's "sheet" curve `cubic-bezier(0.32, 0.72, 0, 1)`) replaced plain `ease`/
  `ease-out` on `press-scale`, `fade-in-up`, hover-lift, and every input/chip
  focus transition. A linear or default-easeout timing function on an
  interactive element is a regression, not a style choice — this system stopped
  using them everywhere on purpose.
- **Entrance:** every card/section fades in and rises 12px (`fade-in-up`, 550ms
  `{motion.spring}`) on mount. Siblings stagger by 60ms via an inline
  `--stagger-index` custom property multiplied in the animation-delay — set once
  per list, not hand-tuned per component.
- **Phase transitions (`scale-in`):** a small pop-in (opacity + scale
  0.92->1, 350ms `{motion.spring}`) for content that *replaces* other content in
  place rather than mounting into empty space — the submit button's spinner
  morph, a `ProgressView` milestone's checkmark landing. Pair with a `key`
  change (or rely on a ternary already swapping element type, which remounts
  automatically) so the animation actually replays each time.
- **Hover (glass tiles only):** `translateY(-4px) scale(1.015)`, 200ms
  `{motion.spring}`, paired with the blur/saturate intensify above.
- **Press (buttons, chips):** `scale(0.96)`, 200ms `{motion.spring}` — same
  grammar everywhere an element is tapped.
- **Hero (recipe detail):** two separate mechanisms, not one — see
  `{motion.hero-load-reveal}` (load-triggered, plays once per mount regardless
  of scroll position) and `{motion.hero-parallax}` (scroll-driven, created only
  after the reveal completes, never touches `filter`). These used to be a
  single scroll-scrubbed timeline (`hero-focus-pull`, retired this version) that
  left the hero fully blurred at scroll position 0 on every fresh page load —
  the reported "thumbnail missing" bug. If you're tempted to merge these back
  into one timeline, don't: the split is what fixes the bug.
- **Loading:** shimmer sweep only. No spinners for content loading (spinners remain
  fine for the async progress-tracker milestones, which represent a real pipeline
  stage, not a generic content fetch).
- **Reduced motion:** one rule, in `index.css`, nowhere else —
  `@media (prefers-reduced-motion: reduce) { * { animation: none !important;
  transition: none !important; } }`. No component ever checks this itself.

## Do's and Don'ts

### Do
- Reserve `backdrop-filter` and shadow entirely for photo-backed glass tiles.
- Set every duration/count/temperature value in `{typography.data-lg}` or
  `{typography.data-sm}` — never Inter.
- Track headlines negative at -0.02em to -0.03em, every time, at ≥19px.
- Use `{colors.accent}` for every interactive/active signal and nothing else.
- Add the scrim-behind-glass gradient when a specific photo is bright enough to
  threaten legibility — check per-image, don't pre-emptively darken every hero.
- Stagger list entrances by 60ms; make sure the 12px translateY is actually visible
  on screen, not tuned down to feel "subtle."

### Don't
- Don't blur or shadow a flat-color panel — glass only over photography.
- Don't use a dark scrim as the glass tint — translucent white only
  (`{colors.glass-tint}`); a dark fill reads as an ordinary card, not glass.
- Don't introduce a second accent color for "just this one badge."
- Don't set body copy below 15px or drop headline tracking to 0 — both are
  generic-AI tells this system explicitly avoids.
- Don't build per-component `prefers-reduced-motion` checks — the one global rule
  in `index.css` is the only place this is handled.
- Don't render a metadata field that's null — omit it from the row entirely rather
  than showing a placeholder/em-dash.

## Responsive Behavior

| Context | Width | Behavior |
|---|---|---|
| Phone (primary target) | ≤ 480px | Single column throughout; recipe grid is 2-up; filter chips scroll horizontally if they overflow. |
| Large phone / small tablet | 481–700px | Recipe grid stays 2-up; content column widens toward `max-w-[560px]`. |
| Desktop browser (dev preview) | > 700px | Recipe grid may go 3-up inside the centered `max-w-[560px]`-plus-grid container; everything else stays single-column centered — this app doesn't get a desktop-specific layout, it's a PWA. |

### Touch Targets
- Minimum 44×44px on every tappable element (buttons, chips, grid tiles, back
  button) — inherited from the existing `press-scale`/safe-area conventions already
  in this codebase.

## Iteration Guide

1. Change one component at a time; reference its `{component.*}` key directly.
2. Before shipping a component, check it against the Do/Don't list above — glass
   bleeding onto flat chrome is the single most likely regression.
3. New data fields (anything numeric describing the recipe) default to
   `{typography.data-sm}` unless they're the hero metadata row, which uses
   `{typography.data-lg}`.
4. If a new screen needs "more chrome," reach for the surface ladder
   (`surface-1` → `surface-2` → `surface-3`) before reaching for a shadow.

## Known Gaps

- No light-mode variant exists or is planned — this system is dark-only per the
  product brief.
- Accounts/profile chrome is not designed yet; the header region is left visually
  simple enough to accept a future profile affordance without restructuring, but no
  placeholder UI exists for it.
- Filter chips only cover platform (YouTube/Instagram) + text search today, because
  that's the only real filterable data `GET /api/recipes` returns — cuisine/category
  tagging would need a backend change this pass didn't include.
- `cook_time_minutes` / `servings` / `calories` / `oven_temp_f` are newly-added
  optional backend fields; existing cached recipes extracted before this change will
  have all four as `null` until re-extracted, so the hero metadata row will be empty
  for older saved recipes by design (see Do's and Don'ts: omit, don't placeholder).
