# Marbles — Technical Documentation

> Kid-friendly overview is in [README.md](README.md). This file is the full
> reference for grown-ups, developers, and code review.

A calm, offline **screen-time bank and timer** for one child.

The child earns **physical marbles** at home for chores (this stays offline, by
design — the marble is the reward). The app handles the *spending* side: one
marble buys a block of game time, unspent marbles are banked toward bigger
rewards, and grown-ups manage rates behind a PIN.

- **One file.** `index.html` is the entire app — no build step, no runtime
  dependencies, no external fetches, no accounts, no tracking.
- **Offline.** Everything runs in the browser; all state lives in `localStorage`.
- **Installable.** Ships as a PWA and can be packaged into an Android `.apk`.

---

## Table of contents

- [Quick start](#quick-start)
- [How it works (for parents)](#how-it-works-for-parents)
- [Deploying & installing](#deploying--installing)
  - [Option A — home-screen PWA](#option-a--home-screen-pwa-easiest)
  - [Option B — real .apk](#option-b--real-apk)
- [Data & persistence](#data--persistence)
- [Architecture](#architecture)
- [Data model](#data-model)
- [Design decisions](#design-decisions)
- [Testing](#testing)
- [Known constraints & gotchas](#known-constraints--gotchas)
- [File manifest](#file-manifest)

---

## Quick start

Open `index.html` (or `marbles.html`) in any modern browser. That's it.

Default grown-ups **PIN is `1234`** — change it first thing in
**Grown-ups → PIN, backup & reset**.

For durable storage and a home-screen icon, host it and install it — see
[Deploying & installing](#deploying--installing).

---

## How it works (for parents)

The app has four tabs along the bottom.

**Home** — the child's main screen. Shows how many marbles she has, a big
**Spend a marble** button, and the live countdown when time is running.

**Bank** — savings goals (e.g. "Movie night = 5 marbles"). She can move spare
marbles into a goal herself; when a goal fills, a **Claim** button appears.

**Usage** *(PIN-locked)* — a 14-day chart of minutes played per day, plus
earned-vs-spent totals. This is a parenting tool, deliberately descriptive only:
no scores, no targets, nothing the child should optimise against. Use the
earned/spent ratio as a health check — if earned keeps outrunning spent, marbles
inflate and lose meaning; if she's always at zero, the rates are too steep.

**Grown-ups** *(PIN-locked)* — add marbles she earned offline, edit activities
and their minute rates, edit savings goals, change the PIN, back up / restore,
toggle timer sounds, and reset.

### The spend flow

1. Child taps **Spend a marble** and picks an activity (e.g. Games · 20 min).
2. One marble is deducted; a wall-clock countdown starts.
3. A soft warning sounds at 1 minute and 10 seconds; a chime + buzz at zero.
4. The timer **survives reload and screen-lock** — closing the app or locking
   the phone does not cheat the clock in either direction.

---

## Deploying & installing

### Option A — home-screen PWA (easiest)

1. Unzip `marbles-site.zip`. The files must sit at the **root** of what you
   deploy (`index.html`, `manifest.webmanifest`, etc. — not nested in a
   subfolder).
2. Drag the folder onto **[Netlify Drop](https://app.netlify.com/drop)** (free).
   You get an HTTPS URL.
3. On the phone, open that URL in Chrome → menu → **Install app** /
   **Add to home screen**.

You get a marble icon, a fullscreen app with no browser bar, offline use, and —
importantly — **persistent storage** the OS won't auto-evict.

### Option B — real .apk

<a name="make-an-android-apk"></a>

1. Do Option A first (PWABuilder needs a live HTTPS URL).
2. Go to **[PWABuilder](https://www.pwabuilder.com/)**, enter the URL, hit test.
   You should see the app name, the marble icon, and green checks.
3. **Package For Stores → Android → Generate.** Download the zip; it contains
   the signed `.apk` plus a **`signing.keystore`** and its passwords.
4. Install the APK on the phone (allow "install from unknown sources" once).

> **Keep that keystore.** To ship an *update* later, redeploy to Netlify and
> regenerate the APK **with the same signing key**. Same key → the update
> installs over the old app and keeps her marbles. A different key → Android
> forces an uninstall/reinstall, which wipes `localStorage`. Back the keystore
> up somewhere safe.

---

## Data & persistence

All state is a single JSON object in `localStorage` under the key `marbles.v1`.

**It survives:** closing the tab/app, rebooting the phone, and app updates
(when signed with the same key).

**It can be lost by:** clearing browser data, an OS storage-pressure eviction of
a *non-installed* tab, or — the subtle one — **opening the app from a different
origin** (a loose `file://` open gets a different storage bucket than the hosted
URL). Installing the PWA/APK pins it to one origin and upgrades storage to
persistent, which removes both risks.

**Backup is the seatbelt.** Grown-ups → *Copy backup code* produces a base64
string of the entire state; *Restore from code* re-imports it. Do this once
after setup, and any time before a risky change.

---

## Architecture

Single file, but internally split into small modules with clear
responsibilities (SOLID in spirit — each piece owns one thing and the view is
rebuilt from state rather than mutated ad hoc):

```
┌───────────────────────────────────────────────────────────┐
│                        index.html                          │
│                                                            │
│  ┌─────────┐   reads/writes   ┌──────────────────────────┐ │
│  │  Store  │◄────────────────►│  localStorage(marbles.v1)│ │
│  │         │                  └──────────────────────────┘ │
│  │ • state (single source of truth)                        │
│  │ • load / save / migrate                                 │
│  └────┬────┘                                               │
│       │ get / update                                       │
│       ▼                                                    │
│  ┌─────────┐   fires cues    ┌─────────┐                   │
│  │  Timer  │────────────────►│  Sound  │ (Web Audio, synth)│
│  │ wall-clock countdown      └─────────┘                   │
│  │ survives reload/lock │                                  │
│  └────┬────┘                                               │
│       │ ticks → re-render                                  │
│       ▼                                                    │
│  ┌───────────────────────────────────────────────┐        │
│  │  render()  — pure-ish view built from state    │        │
│  │  routes on TAB: Home / Bank / Usage            │        │
│  │  ┌──────────┬──────────┬──────────┬─────────┐  │        │
│  │  │ renderHome│renderBank│renderUsage│ tabbar │  │        │
│  │  └──────────┴──────────┴──────────┴─────────┘  │        │
│  └───────────────────────────────────────────────┘        │
│       ▲                                                    │
│       │ mutate then re-render                              │
│  ┌────┴─────────────────────────────────────────┐         │
│  │  actions: spendMarble, addToBank, claimGoal,  │         │
│  │           grantMarbles, removeMarbles         │         │
│  └───────────────────────────────────────────────┘        │
│                                                            │
│  PWA layer: static manifest + persistent-storage request  │
│             + optional sibling sw.js (offline page load)   │
└───────────────────────────────────────────────────────────┘
```

**Data flow is one-directional:** an action mutates `Store`, then calls
`render()`, which rebuilds the DOM from the current state. There is no scattered
DOM mutation — the screen is always a function of state, so a reload reproduces
the exact same UI.

### Module responsibilities

| Module | Owns | Notes |
| --- | --- | --- |
| `Store` | State + persistence | Single source of truth. `load/save/migrate`, versioned key `marbles.v1`. |
| `Timer` | The countdown | **Wall-clock based** (`endTs`), not a tick counter, so lock/reload can't drift it. Fires sound cues on threshold *crossings* only. |
| `Sound` | Audio + haptics | Tones synthesised with Web Audio (no audio files). Unlocked by the spend tap. Muteable; off = silent. |
| `render()` + `renderX` | The view | Rebuilds DOM from state. Tab router. No business logic. |
| actions | State transitions | `spendMarble`, `addToBank`, `claimGoal`, `grantMarbles`, `removeMarbles`. Each mutates then re-renders. |
| PWA layer | Install/offline | Static manifest, persistent-storage request, optional `sw.js`. Degrades silently on `file://`. |

---

## Data model

`localStorage["marbles.v1"]`:

```jsonc
{
  "v": 1,
  "marbles": 4,                 // spendable now
  "pin": "1234",
  "minutesPerMarble": 20,       // fallback rate
  "soundOn": true,
  "activities": [               // what one marble buys
    { "id": "game", "name": "Games", "minutes": 20 },
    { "id": "tv",   "name": "TV",    "minutes": 30 }
  ],
  "goals": [                    // savings goals
    { "id": "movie", "name": "Movie night", "cost": 5, "saved": 3 }
  ],
  "history": [                  // newest first, capped at 200
    { "id": "ab12", "type": "spend", "text": "…", "ts": 0, "minutes": 20, "delta": -1 }
  ],
  "session": null               // live timer, or {label,endTs,totalSec,running,pausedLeft}
}
```

`history` event `type`s: `earn`, `spend`, `save`, `claim`, `adjust`. `minutes`
(on spends) and `delta` (marble change) power the Usage chart.

### Migration

`Store.migrate()` runs on every load. It shallow-merges new default keys onto
old saves, and **back-fills** `minutes`/`delta` on pre-chart history by parsing
the event text (e.g. `"→ 20 min"` → `minutes: 20`) so the Usage timeline
populates from existing data instead of showing zeros.

---

## Design decisions

- **Earning stays physical.** The app never mints marbles for chores; a grown-up
  adds what was earned offline. The marble is the reward; the app is the ledger
  and clock.
- **No borrowing.** You can only spend marbles you actually have. No debt against
  future chores — that turns the system into resentment.
- **Wall-clock timer.** Time left is `endTs - now`, not a decremented counter, so
  locking the screen or reloading can't add or remove time.
- **Sounds fire once, on crossing.** No per-second ticking; a cue triggers only as
  the clock passes 60s / 10s / 0s downward, and never re-fires.
- **Usage is descriptive, PIN-locked.** Real numbers, no score or target, kept
  away from the child so it can't become a thing to game or feel judged by.
- **Amber is the only warm colour.** On the silver-black scheme, the marble
  gradient is the single accent — it's the app's identity.

---

## Testing

Behaviour was verified in real Chromium (Playwright) across the build. Coverage:

- **Core:** grant, spend (decrements + logs minutes), bank, claim cycle.
- **Timer:** starts at correct duration, pause freezes, resume continues, stop
  clears, **survives reload** (wall-clock), sound cues fire once on each
  threshold crossing and not above them.
- **Guards:** cannot spend at zero marbles.
- **Persistence:** state survives reload; backup code round-trips.
- **Migration:** old history missing `minutes`/`delta` is repaired on load; the
  Usage buckets sum per day and exclude anything older than 14 days.
- **PWA:** static manifest present in raw HTML, valid JSON, 192+512+maskable
  icons, correct MIME types, service worker registers over HTTPS, and everything
  degrades without error on `file://`.

There is no framework harness in this single-file build; the checks are
Playwright scripts run against the file. When the Vite/React/TypeScript source
version is built, that repo carries the formal Vitest suite.

---

## Known constraints & gotchas

- **Service workers can't be inlined.** Browsers reject SWs registered from
  `blob:` URLs, so guaranteed-offline page load needs the real sibling `sw.js`.
  The app still installs and works offline without it (via HTTP cache +
  `localStorage`); `sw.js` only bulletproofs the offline *page load*.
- **Manifest must be a static file.** PWABuilder and stores read the raw HTML
  without running JS. A JS-injected manifest shows up as "Missing Name". The
  hosted build therefore uses a real `manifest.webmanifest`; the runtime
  injection remains only as a fallback for lone-file `file://` use.
- **iOS Safari won't vibrate** from the web; Android does. Sounds work on both
  (after the first user tap, per browser autoplay rules).
- **Signing key = update path.** See the warning under
  [Option B](#option-b--real-apk).

---

## File manifest

| File | Purpose |
| --- | --- |
| `index.html` / `marbles.html` | The entire app. Deploy as `index.html`. |
| `manifest.webmanifest` | Static PWA manifest (name, icons, colours). Required for APK. |
| `icon-192.png`, `icon-512.png` | App icons (512 also used as maskable). |
| `sw.js` | *Optional* service worker for guaranteed offline page load. |
| `_headers` | Netlify: correct MIME type for the manifest and `sw.js`. |
| `marbles-site.zip` | The above, bundled for one-drag Netlify deploy. |

---

*Built static-first: a single HTML file, no runtime dependencies, no external
requests, everything on-device.*
