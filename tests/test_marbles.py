"""Behaviour tests for Marbles (index.html) in real Chromium.

Run:
    pip install pytest playwright && python -m playwright install chromium
    pytest tests -q
"""
import json
import pathlib

import pytest
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parent.parent / "index.html").as_uri()
SRC = (pathlib.Path(__file__).resolve().parent.parent / "index.html").read_text()
PIN = "4321"
GAMES = {"id": "game", "name": "Games", "minutes": 20}
BASE = {
    "v": 2, "setupDone": True, "pin": PIN, "marbles": 0, "soundOn": True,
    "activities": [GAMES, {"id": "tv", "name": "TV", "minutes": 30}],
    "goals": [{"id": "movie", "name": "Movie night", "cost": 5, "saved": 0}],
    "history": [], "session": None,
}


# ----------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    yield pg
    ctx.close()
    assert not pg.errors, pg.errors


def boot(pg, raw=None, **over):
    """Load the app with a given saved state (goes through migrate())."""
    state = raw if raw is not None else {**BASE, **over}
    pg.goto(APP)
    pg.evaluate("s => localStorage.setItem('marbles.v1', JSON.stringify(s))", state)
    pg.reload()
    pg.wait_for_timeout(80)
    return pg


def st(pg, path="s"):
    return pg.evaluate(f"(() => {{ const s = __marbles.Store.get(); return {path}; }})()")


def dialog(pg):
    return pg.locator("dialog[open]")


def type_pin(pg, pin):
    for d in pin:
        dialog(pg).get_by_role("button", name=d, exact=True).click()


def unlock(pg, pin=PIN):
    pg.get_by_role("button", name="Grown-ups").click()
    type_pin(pg, pin)


def spy_sounds(pg):
    pg.evaluate("""() => { window.__calls = []; const S = __marbles.Sound;
        ['warn','lastCall','end'].forEach(k => { S[k] = () => window.__calls.push(k); }); }""")


# ----------------------------------------------------------------- PIN & setup
def test_fresh_install_forces_pin_setup_and_rejects_1234(page):
    page.goto(APP)
    page.evaluate("localStorage.clear()")
    page.reload()
    assert dialog(page).locator("h2").inner_text() == "Welcome to Marbles"
    page.keyboard.press("Escape")
    assert dialog(page).count() == 1, "setup must not be dismissible"
    dialog(page).get_by_role("button", name="Set PIN").click()
    type_pin(page, "1234")
    assert "too easy" in dialog(page).locator(".pin-err").inner_text()
    type_pin(page, "5678")
    type_pin(page, "5678")
    assert st(page, "s.pin") == "5678" and st(page, "s.setupDone") is True
    assert dialog(page).locator("h2").inner_text() == "Grown-ups"


def test_existing_install_with_default_pin_must_change_it(page):
    boot(page, raw={"marbles": 3, "pin": "1234", "history": []})   # v1 save
    assert dialog(page).count() == 0, "existing installs skip the welcome"
    unlock(page, "1234")
    assert dialog(page).locator("h2").inner_text() == "Set your own PIN"


def test_pin_lockout_persists_and_expires(page):
    boot(page)
    page.get_by_role("button", name="Grown-ups").click()
    for _ in range(5):
        type_pin(page, "9999")
    assert "Too many wrong tries" in dialog(page).locator(".pin-err").inner_text()
    assert dialog(page).get_by_role("button", name="1", exact=True).is_disabled()
    page.reload()
    assert st(page, "s.lockUntil > Date.now()")
    page.get_by_role("button", name="Grown-ups").click()
    assert dialog(page).get_by_role("button", name="4", exact=True).is_disabled()
    page.evaluate("__marbles.Store.update(s => { s.lockUntil = Date.now() - 1; })")
    page.wait_for_timeout(1100)
    type_pin(page, PIN)
    assert dialog(page).locator("h2").inner_text() == "Grown-ups"


def test_pin_grace_window_skips_second_prompt(page):
    boot(page)
    unlock(page)
    dialog(page).get_by_role("button", name="Done").click()
    page.get_by_role("button", name="Usage").click()
    assert dialog(page).count() == 0
    assert page.locator(".view-title").inner_text() == "Usage"


# ----------------------------------------------------------------- spending
def test_spend_ui_multi_marble(page):
    boot(page, marbles=4)
    page.get_by_role("button", name="Spend marbles").click()
    plus = dialog(page).get_by_role("button", name="10 minutes more")
    plus.click(); plus.click()
    assert dialog(page).locator(".step-mins").inner_text() == "40"
    assert "Costs 2 marbles" in dialog(page).locator(".cost-line").inner_text()
    dialog(page).get_by_role("button", name="Start 40 min").click()
    assert st(page, "s.marbles") == 2
    assert 2390 < page.evaluate("__marbles.Timer.secondsLeft()") <= 2400


def test_rates_snap_to_10_minutes(page):
    boot(page, marbles=3, activities=[{"id": "r", "name": "Reading", "minutes": 15}])
    assert st(page, "s.activities[0].minutes") == 20
    page.get_by_role("button", name="Spend marbles").click()
    assert dialog(page).locator(".step-mins").inner_text() == "20"
    dialog(page).get_by_role("button", name="Start 20 min").click()
    assert 1190 < page.evaluate("__marbles.Timer.secondsLeft()") <= 1200
    page.evaluate("__marbles.applyActivities([{id:'x',name:'Lego',minutes:25}])")
    assert st(page, "s.activities[0].minutes") == 30


def test_spare_time_offer_uses_paid_minutes(page):
    boot(page, marbles=4)
    page.get_by_role("button", name="Spend marbles").click()
    dialog(page).get_by_role("button", name="10 minutes more").click()          # 30 min = 2 marbles
    spare = dialog(page).locator(".spare-btn")
    assert spare.is_visible() and "40 min" in spare.inner_text()
    spare.click()
    assert dialog(page).locator(".step-mins").inner_text() == "40"
    assert not spare.is_visible()


def test_api_refuses_overspend_and_double_session(page):
    boot(page, marbles=2)
    assert page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)}, 100)") is False
    assert st(page, "s.marbles") == 2 and st(page, "s.session") is None
    assert page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)}, 20)") is True
    assert page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)}, 20)") is False
    assert st(page, "s.marbles") == 1


# ----------------------------------------------------------------- timer
def test_pause_has_5_minute_budget_then_restarts_itself(page):
    boot(page, marbles=1)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)})")
    assert page.evaluate("__marbles.Timer.pause()") is True
    page.evaluate("__marbles.Store.update(s => { s.session.pauseStart -= 301000; s.session.endTs -= 301000; })")
    page.evaluate("__marbles.Timer.tick()")
    assert page.evaluate("__marbles.Timer.isPaused()") is False
    assert page.evaluate("__marbles.Timer.pauseRemaining()") == 0
    assert page.locator(".timer-card .tbtn", has_text="Pause").is_disabled()
    assert page.evaluate("__marbles.Timer.pause()") is False
    assert 1190 < page.evaluate("__marbles.Timer.secondsLeft()") <= 1200     # clock stood still during the pause


def test_manual_resume_spends_part_of_budget(page):
    boot(page, marbles=1)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)})")
    page.evaluate("__marbles.Timer.pause()")
    page.evaluate("__marbles.Store.update(s => { s.session.pauseStart -= 120000; })")
    page.evaluate("__marbles.Timer.resume()")
    assert 178 <= page.evaluate("__marbles.Timer.pauseRemaining()") <= 181


def test_background_catchup_plays_one_cue_once(page):
    boot(page, marbles=1)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)})")
    spy_sounds(page)
    page.evaluate("__marbles.Store.update(s => { s.session.endTs = Date.now() - 5000; })")
    page.evaluate("__marbles.Timer.tick(); __marbles.Timer.tick()")
    assert page.evaluate("window.__calls") == ["end"]


def test_cues_fire_in_order_when_foreground(page):
    boot(page, marbles=1)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)})")
    spy_sounds(page)
    for left in (59, 9, 0):
        page.evaluate(f"__marbles.Store.update(s => {{ s.session.endTs = Date.now() + {left}*1000; }}); __marbles.Timer.tick()")
    assert page.evaluate("window.__calls") == ["warn", "lastCall", "end"]


def test_timer_tick_does_not_rebuild_page(page):
    boot(page, marbles=5)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)})")
    page.evaluate("window.__m = document.querySelector('.marble'); window.__r = document.querySelector('.ring-fg')")
    page.wait_for_timeout(1300)
    assert page.evaluate("document.body.contains(window.__m) && document.body.contains(window.__r)")
    page.evaluate("TAB='usage'; render(); document.querySelector('details.history').open = true")
    page.wait_for_timeout(1300)
    assert page.evaluate("document.querySelector('details.history').open")


def test_timer_survives_reload(page):
    boot(page, marbles=2)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)}, 30)")
    page.wait_for_timeout(1200)
    page.reload()
    assert 1780 < page.evaluate("__marbles.Timer.secondsLeft()") < 1800


def test_done_asks_first_and_refunds_whole_unused_marbles(page):
    boot(page, marbles=3)
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)}, 60)")
    page.evaluate("__marbles.Store.update(s => { s.session.endTs = Date.now() + 50*60000; })")  # 10 min played
    page.locator(".timer-card .tbtn.stop").click()
    assert "Stop now?" in dialog(page).inner_text() and "2 marbles back" in dialog(page).inner_text()
    dialog(page).get_by_role("button", name="Keep playing").click()
    assert st(page, "s.session") is not None
    page.locator(".timer-card .tbtn.stop").click()
    dialog(page).get_by_role("button", name="Stop now").click()
    assert st(page, "s.marbles") == 2 and st(page, "s.session") is None
    assert st(page, "s.history.find(h => h.type==='spend').played") == 10
    assert page.evaluate("__marbles.dailyBuckets(__marbles.Store.get().history).at(-1).spent") == 1


# ----------------------------------------------------------------- bank
def test_goal_delete_and_price_cut_return_marbles(page):
    boot(page, goals=[{"id": "a", "name": "Movie", "cost": 5, "saved": 4},
                      {"id": "b", "name": "Lego", "cost": 10, "saved": 3}])
    refund = page.evaluate("__marbles.applyGoals([{id:'b',name:'Lego',cost:2,saved:3}])")
    assert refund == 5 and st(page, "s.marbles") == 5
    assert st(page, "s.goals") == [{"id": "b", "name": "Lego", "cost": 2, "saved": 2}]


def test_bank_add_withdraw_claim(page):
    boot(page, marbles=2, goals=[{"id": "g", "name": "Movie", "cost": 2, "saved": 0}])
    page.get_by_role("button", name="Bank", exact=True).click()
    page.get_by_role("button", name="Add a marble").click()
    page.get_by_role("button", name="Take one marble back from Movie").click()
    assert st(page, "s.marbles") == 2 and st(page, "s.goals[0].saved") == 0
    page.get_by_role("button", name="Add a marble").click()
    page.get_by_role("button", name="Add a marble").click()
    page.get_by_role("button", name="Claim Movie").click()
    assert st(page, "s.goals[0].saved") == 0 and st(page, "s.marbles") == 0


# ----------------------------------------------------------------- usage data
def test_usage_counts_marbles_and_played_minutes(page):
    boot(page)
    page.evaluate("__marbles.grantMarbles(3)")
    page.evaluate(f"__marbles.spendMarble({json.dumps(GAMES)}, 60)")
    page.evaluate("__marbles.Store.update(s => { s.session.endTs = Date.now() + 20*60000; }); __marbles.endSession()")
    b = page.evaluate("__marbles.dailyBuckets(__marbles.Store.get().history).at(-1)")
    assert (b["earned"], b["spent"], b["minutes"]) == (3, 2, 40)
    page.evaluate("TAB='usage'; render()")
    assert page.locator(".stat .n").nth(2).inner_text() == "3/2"


def test_chart_tap_targets_are_finger_sized(page):
    boot(page)
    page.evaluate("TAB='usage'; render()")
    w = page.evaluate("document.querySelector('.chart-hit').getBoundingClientRect().width")
    h = page.evaluate("document.querySelector('.chart-hit').getBoundingClientRect().height")
    assert w >= 20 and h >= 100
    page.locator(".chart-hit").last.click()
    assert page.locator(".chart-tip").count() == 1


# ----------------------------------------------------------------- grown-ups & backup
def test_grownups_panel_shows_balance_and_toast_is_on_top(page):
    boot(page, marbles=7)
    unlock(page)
    assert dialog(page).locator(".balance-n").inner_text() == "7"
    dialog(page).get_by_role("button", name="Add 2 marbles").click()
    assert dialog(page).locator(".balance-n").inner_text() == "9"
    top = page.evaluate("""() => { const t = document.querySelector('.toast'); const r = t.getBoundingClientRect();
        return document.elementFromPoint(r.x + r.width/2, r.y + r.height/2) === t; }""")
    assert top, "toast must render above the open dialog"
    assert page.evaluate("document.querySelector('.toast').getBoundingClientRect().height") < 60, "toast must not squeeze into a column"


def test_backup_excludes_pin_and_restore_keeps_it(page):
    boot(page, marbles=4)
    code = page.evaluate("__marbles.backupCode()")
    data = json.loads(page.evaluate("c => __marbles.b64dec(c)", code))
    assert "pin" not in data and "lockUntil" not in data and data["marbles"] == 4
    data["marbles"] = 11
    page.evaluate("d => __marbles.applyRestore(d)", data)
    assert st(page, "s.marbles") == 11 and st(page, "s.pin") == PIN
    assert page.evaluate("__marbles.parseBackup('garbage!!').ok") is False


def test_old_style_backup_code_still_restores(page):
    boot(page)
    legacy = page.evaluate("btoa(unescape(encodeURIComponent(JSON.stringify({v:1,marbles:6,pin:'0000'}))))")
    r = page.evaluate("c => __marbles.parseBackup(c)", legacy)
    assert r["ok"] and r["data"]["marbles"] == 6


# ----------------------------------------------------------------- migration
def test_v1_state_migrates(page):
    now = page.evaluate("Date.now()") if False else None
    boot(page, raw={
        "v": 1, "marbles": 2, "pin": "2468",
        "activities": [{"id": "g", "name": "Games", "minutes": 25}],
        "history": [{"id": "a", "type": "spend", "text": "Spent 1 marble → 20 min of Games", "ts": 1},
                    {"id": "b", "type": "earn", "text": "Added 3 marbles", "ts": 1}],
        "session": {"label": "Games", "totalSec": 1200, "endTs": 0, "running": False, "pausedLeft": 300},
    })
    s = st(page)
    assert s["v"] == 2 and s["setupDone"] is True and s["activities"][0]["minutes"] == 30
    assert s["history"][0]["minutes"] == 20 and s["history"][0]["delta"] == -1 and s["history"][1]["delta"] == 3
    assert s["session"]["pauseStart"] is not None and 295 <= page.evaluate("__marbles.Timer.secondsLeft()") <= 300


# ----------------------------------------------------------------- layout & a11y
def test_zoom_allowed(page):
    boot(page)
    vp = page.evaluate("document.querySelector('meta[name=viewport]').content")
    assert "user-scalable=no" not in vp and "maximum-scale" not in vp


def test_controls_are_real_buttons(page):
    boot(page, marbles=2)
    page.get_by_role("button", name="Spend marbles").click()
    chips = dialog(page).locator(".act-chip")
    assert chips.first.evaluate("e => e.tagName") == "BUTTON"
    assert chips.first.get_attribute("aria-pressed") == "true"
    chips.nth(1).click()
    assert chips.nth(1).get_attribute("aria-pressed") == "true" and chips.first.get_attribute("aria-pressed") == "false"
    page.keyboard.press("Escape")
    assert dialog(page).count() == 0
    assert page.get_by_role("button", name="Home").get_attribute("aria-current") == "page"


@pytest.mark.parametrize("scale", [1, 2, 3])
def test_320px_has_no_overflow_or_wrapping(browser, scale):
    ctx = browser.new_context(viewport={"width": 320, "height": 640}, device_scale_factor=scale)
    page = ctx.new_page()
    boot(page, marbles=15, goals=[{"id": "m", "name": "Movie night", "cost": 5, "saved": 3},
                                  {"id": "l", "name": "Lego set", "cost": 4, "saved": 4}])
    page.evaluate("__marbles.Store.update(s => { s.history=[{id:'x',type:'earn',delta:12,ts:Date.now()}]; }); TAB='usage'; render()")
    assert page.evaluate("document.documentElement.scrollWidth") <= 320
    clipped = page.evaluate("""[...document.querySelectorAll('.tab-label, .stat .k, .stat .n')]
        .filter(e => e.scrollWidth > e.clientWidth).map(e => e.textContent)""")
    page.evaluate("TAB='bank'; render()")
    wrapped = page.evaluate("""[...document.querySelectorAll('.goal-actions button')]
        .filter(e => { const r = e.getBoundingClientRect(), c = e.closest('.bank').getBoundingClientRect();
                       return r.height > 50 || r.right > c.right - 10 || r.left < c.left; }).map(e => e.textContent)""")
    ctx.close()
    assert clipped == [] and wrapped == []


def test_more_than_12_marbles_shows_count_pill(page):
    boot(page, marbles=15)
    assert page.locator(".marble").count() == 12
    assert page.locator(".marble-more").inner_text() == "+3"


def test_old_purple_theme_is_gone():
    assert "#3a2a6a" not in SRC and "rgba(8,5,18" not in SRC


# ----------------------------------------------------------------- standalone build
def test_standalone_file_is_self_contained_and_in_sync(browser):
    root = pathlib.Path(__file__).resolve().parent.parent
    standalone = (root / "marbles.html").read_text()
    assert "manifest.webmanifest" not in standalone and 'href="icon-' not in standalone and "'sw.js'" not in standalone
    strip = lambda s: s.split("<script>", 1)[1].replace("navigator.serviceWorker.register('sw.js')", "Promise.reject()")
    assert strip(SRC) == strip(standalone), "marbles.html is stale: run python3 build_standalone.py"
    ctx = browser.new_context()
    pg = ctx.new_page()
    errors, requests = [], []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("request", lambda r: requests.append(r.url))
    pg.goto((root / "marbles.html").as_uri())
    assert pg.locator("dialog[open] h2").inner_text() == "Welcome to Marbles"
    ctx.close()
    assert not errors and all(u.startswith(("file:", "data:")) for u in requests)
