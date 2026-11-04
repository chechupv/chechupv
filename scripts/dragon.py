#!/usr/bin/env python3
"""Draw an animated silver ice dragon (SVG) from a GitHub account's activity.

* The dragon's length grows with the contributions of the last year.
* It swims faster when the last 7 days were busy, and the pearl glows brighter.

Only the standard library is used, so it runs as-is on a GitHub runner.

    python3 scripts/dragon.py --login chechupv --out dist/dragon.svg
    python3 scripts/dragon.py --total 600 --week 12 --out dragon.svg   # offline
"""
import argparse
import json
import math
import os
import random
import urllib.request

W, H = 900, 300
CY = 150
FRAMES = 24

# Palette: silver body, white mane, dark talons and horns, blue glow.
OUTLINE = "#1c2233"
BODY_TOP, BODY_BOTTOM = "#ffffff", "#8e9ab0"
FAR = "#7c889e"
SCALE = "#6b7a92"
BELLY = "#e4e9f1"
BELLY_LINE = "#8a97ad"
MANE = "#f6f8ff"
MANE_EDGE = "#9fb0c9"
HORN, HORN_HI = "#2f3650", "#7f9be6"
TALON = "#14151b"
GLOW, GLOW_DEEP = "#8fd8ff", "#3f6fe0"
FIN_DARK, FIN_LIGHT = "#222d4a", "#6f8fe8"


# ---------------------------------------------------------------- data ----
def fetch_activity(login, token):
    query = """query($login: String!) { user(login: $login) {
      contributionsCollection { contributionCalendar {
        totalContributions weeks { contributionDays { date contributionCount } }
      } } } }"""
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "dragon-readme",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if data.get("errors"):
        raise SystemExit(f"GitHub API error: {data['errors']}")
    calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = sorted(
        (d for w in calendar["weeks"] for d in w["contributionDays"]),
        key=lambda d: d["date"],
    )
    return calendar["totalContributions"], sum(d["contributionCount"] for d in days[-7:])


# ------------------------------------------------------------ geometry ----
def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def mul(a, k):
    return (a[0] * k, a[1] * k)


def rot(v, ang):
    c, s = math.cos(ang), math.sin(ang)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def unit(v):
    n = math.hypot(*v) or 1.0
    return (v[0] / n, v[1] / n)


def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def num(v):
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return "0" if s == "-0" else s


def pt(p):
    return f"{num(p[0])},{num(p[1])}"


def curve(points, closed=False):
    """Smooth path through points (Catmull-Rom converted to cubic Béziers)."""
    out = [f"M{pt(points[0])}"]
    n = len(points)
    for i in range(n - 1):
        p0, p1 = points[max(i - 1, 0)], points[i]
        p2, p3 = points[i + 1], points[min(i + 2, n - 1)]
        c1 = add(p1, mul(sub(p2, p0), 1 / 6))
        c2 = sub(p2, mul(sub(p3, p1), 1 / 6))
        out.append(f"C{pt(c1)} {pt(c2)} {pt(p2)}")
    return "".join(out) + ("Z" if closed else "")


def poly(points):
    return "M" + "L".join(pt(p) for p in points) + "Z"


def leaf(base1, base2, tip, bulge):
    """A tapered strand from two base points to a tip, bulging sideways."""
    mid = mul(add(add(base1, base2), mul(tip, 2)), 0.25)
    return f"M{pt(base1)}Q{pt(add(mid, bulge))} {pt(tip)}Q{pt(sub(mid, mul(bulge, 0.3)))} {pt(base2)}Z"


# -------------------------------------------------------------- dragon ----
class Dragon:
    def __init__(self, total, week):
        self.L = 380 + 280 * min(1.0, total / 900)  # body length grows with the year
        span = self.L + 200  # body + head + pearl
        self.xh = (W - span) / 2 + self.L + 10
        self.dur = round(5.0 - 2.0 * min(1.0, week / 25), 2)  # busier week -> faster
        self.glow = 0.35 + 0.55 * min(1.0, week / 25)

    # spine ---------------------------------------------------------------
    def spine(self, s, ph):
        amp = 7 + 38 * smoothstep(0.0, 0.45, s)
        x = self.xh - s * self.L
        y = CY + amp * math.sin(2 * math.pi * 1.55 * s - ph)
        return (x, y)

    def frame_at(self, s, ph):
        """Centre point, tail-ward tangent and dorsal (upward) normal at s."""
        s = min(1.0, max(0.0, s))
        e = 0.003
        a = self.spine(max(0.0, s - e), ph)
        b = self.spine(min(1.0, s + e), ph)
        t = unit(sub(b, a))
        n = (t[1], -t[0])
        if n[1] > 0:  # make sure the normal points to the back (up-ish)
            n = (-n[0], -n[1])
        return self.spine(s, ph), t, n

    @staticmethod
    def hw(s):
        """Half-width of the body."""
        return (13 + 6 * smoothstep(0.0, 0.14, s)) * (1 - 0.84 * smoothstep(0.32, 1.0, s))

    def steps(self, start, end, k):
        """Positions along the body spaced proportionally to its width."""
        out, s = [], start
        while s < end:
            out.append(s)
            s += k * max(self.hw(s), 3) / self.L
        return out

    # parts ---------------------------------------------------------------
    def body(self, ph):
        upper, lower = [], []
        for i in range(48):
            s = i / 47
            c, _, n = self.frame_at(s, ph)
            w = self.hw(s)
            upper.append(add(c, mul(n, w)))
            lower.append(sub(c, mul(n, w)))
        return curve(upper + lower[::-1], closed=True)

    def strip(self, ph, a, b, s0, s1, count=30):
        """A band along the body between lateral offsets a and b (in half-widths)."""
        one, two = [], []
        for i in range(count):
            s = s0 + (s1 - s0) * i / (count - 1)
            c, _, n = self.frame_at(s, ph)
            w = self.hw(s)
            one.append(add(c, mul(n, a * w)))
            two.append(add(c, mul(n, b * w)))
        return curve(one + two[::-1], closed=True)

    def belly_lines(self, ph):
        out = []
        for s in self.steps(0.03, 0.97, 0.5):
            c, t, n = self.frame_at(s, ph)
            w = self.hw(s)
            a = add(c, mul(n, -0.25 * w))
            b = add(c, mul(n, -0.95 * w))
            q = add(add(c, mul(n, -0.6 * w)), mul(t, 0.3 * w))
            out.append(f"M{pt(a)}Q{pt(q)} {pt(b)}")
        return "".join(out)

    def scales(self, ph):
        out = []
        for offset, shift in ((0.66, 0.0), (0.2, 0.5)):
            for s in self.steps(0.04 + shift * 0.012, 0.95, 0.55):
                c, t, n = self.frame_at(s, ph)
                w = self.hw(s)
                r = 0.27 * w
                p = add(c, mul(n, offset * w))
                a = add(p, mul(n, r))
                b = sub(p, mul(n, r))
                q = add(p, mul(t, 1.6 * r))
                out.append(f"M{pt(a)}Q{pt(q)} {pt(b)}")
        return "".join(out)

    def mane(self, ph, back):
        """Long white strands flowing from the neck and the front of the back."""
        out = []
        ss = self.steps(0.0, 0.62, 0.75)
        for k, s in enumerate(ss):
            if (k % 2 == 0) != back:
                continue
            c, t, n = self.frame_at(s, ph)
            w = self.hw(s)
            length = (10 + 50 * (1 - s / 0.62) ** 1.2) * (1.1 if back else 0.8)
            sway = 0.28 * math.sin(ph * 1.5 - s * 9 + k)
            d = unit(rot(add(mul(n, 0.42), mul(t, 0.9)), -sway))
            b1 = add(c, mul(n, 0.55 * w))
            b2 = add(self.frame_at(s + 0.05, ph)[0], mul(n, 0.55 * w))
            tip = add(add(b1, mul(d, length + w)), mul(n, -0.12 * length))
            out.append(leaf(b1, b2, tip, mul(rot(d, -math.pi / 2), 0.38 * length)))
        return "".join(out)

    def ridge(self, ph):
        """Small silver spikes on the rear half of the back."""
        ss = self.steps(0.56, 0.94, 0.9)
        pts = []
        for k, s in enumerate(ss):
            c, _, n = self.frame_at(s, ph)
            w = self.hw(s)
            pts.append(add(c, mul(n, 0.6 * w)))
            gap = (ss[k + 1] - s) if k + 1 < len(ss) else 0.01
            ct, _, nt = self.frame_at(s + 0.75 * gap, ph)
            pts.append(add(ct, mul(nt, self.hw(s + 0.75 * gap) + 3 + 5 * (1 - s))))
        for s in reversed(ss):
            pts.append(self.frame_at(s, ph)[0])
        return poly(pts)

    def tail_fan(self, ph):
        """Fan-shaped tail fin: (fin outline, rib lines)."""
        c, t, n = self.frame_at(0.985, ph)
        flap = 0.25 * math.sin(ph - 1.2)
        angles = [-1.15 + 2.3 * i / 8 + flap for i in range(9)]
        tips = []
        for i, ang in enumerate(angles):
            length = 34 + 14 * math.cos(ang * 1.2) + 4 * math.sin(ph * 2 + i)
            tips.append(add(c, mul(rot(t, ang), length)))
        d = f"M{pt(c)}L{pt(tips[0])}"
        for a, b in zip(tips, tips[1:]):
            q = add(mul(add(a, b), 0.5), mul(sub(c, mul(add(a, b), 0.5)), 0.22))
            d += f"Q{pt(q)} {pt(b)}"
        d += "Z"
        ribs = "".join(f"M{pt(c)}L{pt(add(c, mul(sub(p, c), 0.9)))}" for p in tips[1:-1])
        return d, ribs

    def leg(self, ph, s, front, far):
        """Returns (limb path, talons path, elbow wisp path)."""
        c, t, n = self.frame_at(s, ph)
        fwd, down = mul(t, -1), mul(n, -1)
        hip = add(c, mul(n, -0.35 * self.hw(s)))
        swing = 0.45 * math.sin(ph + (0 if front else math.pi) + (0.6 if far else 0))
        if front:
            a = 0.55 + swing
            knee = add(hip, mul(add(mul(down, math.cos(a)), mul(fwd, -math.sin(a))), 22))
            fore = unit(add(mul(down, 0.55), mul(fwd, 0.85)))
        else:
            a = 0.65 + swing
            knee = add(hip, mul(add(mul(down, math.cos(a)), mul(fwd, math.sin(a))), 22))
            fore = unit(add(mul(down, 0.75), mul(fwd, -0.65)))
        foot = add(knee, mul(fore, 16))
        limb = f"M{pt(hip)}L{pt(knee)}L{pt(foot)}"
        talons = []
        for ang in (-0.75, -0.25, 0.25, 0.75):
            d = rot(fore, ang)
            hook = rot(d, math.pi / 2)
            tip = add(add(foot, mul(d, 11)), mul(hook, 4))
            q = add(foot, mul(d, 8))
            talons.append(f"M{pt(foot)}Q{pt(q)} {pt(tip)}")
        back = mul(fwd, -1)
        wisp = leaf(
            add(knee, mul(down, 3)), add(knee, mul(n, 3)),
            add(knee, mul(rot(back, -0.4 + 0.15 * math.sin(ph * 2)), 20)), mul(n, 3),
        )
        return limb, "".join(talons), wisp

    def head_pose(self, ph):
        c, t, _ = self.frame_at(0.0, ph)
        ang = math.degrees(math.atan2(-t[1], -t[0]))
        return f"{num(c[0])} {num(c[1])}", num(ang)

    @staticmethod
    def head_mane(ph):
        """Flowing white hair from the back of the head (local head coords)."""
        out = []
        roots = ((8, -17, -2.55), (4, -12, -2.75), (1, -6, -2.9), (0, 0, -3.05), (2, 6, -3.2), (6, 11, -3.35))
        for k, (x, y, ang) in enumerate(roots):
            length = 66 - abs(k - 2) * 7
            ang += 0.14 * math.sin(ph * 1.5 + k * 0.9)
            d = (math.cos(ang), math.sin(ang))
            tip = (x + d[0] * length, y + d[1] * length)
            out.append(leaf((x, y - 3), (x + 2, y + 4), tip, mul(rot(d, math.pi / 2), 15 + 4 * math.sin(ph + k))))
        return "".join(out)

    @staticmethod
    def whiskers(ph):
        s1, s2 = math.sin(ph), math.sin(ph + 1.1)
        return (
            f"M58,4C70,18 {num(40 + 5 * s1)},{num(30 + 4 * s1)} {num(4 + 10 * s1)},{num(40 + 7 * s2)}"
            f"M60,-4C74,-20 {num(44 + 5 * s2)},{num(-36 - 4 * s1)} {num(8 + 10 * s2)},{num(-46 - 6 * s1)}"
        )

    def pearl_pos(self, ph):
        return f"{num(self.xh + 150)} {num(CY - 16 + 7 * math.sin(ph))}"


# ----------------------------------------------------------------- svg ----
HEAD = f"""
<g stroke-linecap="round" fill="none">
  <path d="M10,-14C0,-32 -18,-40 -40,-46M-8,-32C-6,-44 -14,-50 -22,-58M-24,-40C-28,-50 -36,-54 -46,-56" stroke="{OUTLINE}" stroke-width="6.5"/>
  <path d="M10,-14C0,-32 -18,-40 -40,-46M-8,-32C-6,-44 -14,-50 -22,-58M-24,-40C-28,-50 -36,-54 -46,-56" stroke="#4a5270" stroke-width="4"/>
  <path d="M15,-12C5,-30 -12,-37 -34,-41M-3,-29C-1,-41 -8,-48 -15,-55M-19,-36C-22,-46 -30,-50 -40,-52" stroke="{OUTLINE}" stroke-width="7.5"/>
  <path d="M15,-12C5,-30 -12,-37 -34,-41M-3,-29C-1,-41 -8,-48 -15,-55M-19,-36C-22,-46 -30,-50 -40,-52" stroke="{HORN}" stroke-width="5"/>
  <path d="M13,-15C4,-30 -12,-36 -32,-40" stroke="{HORN_HI}" stroke-width="1.4" stroke-opacity="0.8"/>
</g>
<path d="M2,8C20,10 38,12 54,12C57,16 53,21 46,21C30,23 14,22 0,18Z" fill="#c3cbd9" stroke="{OUTLINE}" stroke-width="1.4"/>
<path d="M14,6C30,8 44,8 57,6L55,13C40,13 26,12 14,10Z" fill="#23172b"/>
<path d="M50,13l2,-6l2.2,6ZM40,13l1.6,-4.5l1.8,4.5ZM46,7l1.5,5l1.7,-5Z" fill="#ffffff"/>
<path d="M-6,-12C0,-20 10,-22 18,-19C26,-16 34,-15 44,-13C52,-12 58,-14 63,-10C68,-6 68,2 62,5C56,7 50,6 44,6C32,6 20,5 12,8C6,10 0,14 -6,14C-11,8 -11,-6 -6,-12Z" fill="url(#headGrad)" stroke="{OUTLINE}" stroke-width="1.5" stroke-linejoin="round"/>
<path d="M40,-12Q46,-8 52,-11M30,-14Q36,-10 42,-13M50,-8Q55,-4 60,-8M4,-6Q9,-2 14,-5M6,2Q11,6 16,3" stroke="{SCALE}" stroke-width="1" fill="none"/>
<path d="M4,6C-4,14 -10,24 -22,30C-8,28 0,22 6,16C4,24 0,32 -6,40C6,34 12,24 14,12Z" fill="{MANE}" stroke="{MANE_EDGE}" stroke-width="1"/>
<path d="M22,20C22,30 14,42 0,52C18,46 28,34 31,21Z" fill="{MANE}" stroke="{MANE_EDGE}" stroke-width="1"/>
<path d="M14,-16C8,-23 1,-25 -8,-25C1,-20 5,-16 10,-13ZM14,-16C20,-23 31,-21 35,-15C29,-16 22,-15 18,-12Z" fill="#dfe5f0" stroke="{OUTLINE}" stroke-width="1.2" stroke-linejoin="round"/>
<circle cx="26" cy="-10" r="9" fill="url(#eyeGlow)"/>
<ellipse cx="26" cy="-10" rx="5.2" ry="3.7" fill="{GLOW}" stroke="{OUTLINE}" stroke-width="1.3"/>
<ellipse cx="27" cy="-10" rx="1.3" ry="3.1" fill="#0b1020"/>
<circle cx="25.2" cy="-11.4" r="0.9" fill="#fff"/>
<path d="M60,-6c3,-2 5,1 3,3c-2,1 -3,-1 -1,-2" stroke="{OUTLINE}" stroke-width="1.2" fill="none"/>
"""

CLOUD = """<g fill="currentColor" fill-opacity="0.07" stroke="currentColor" stroke-opacity="0.3" stroke-width="2" stroke-linecap="round">
<path d="M-44,12Q-46,-6 -26,-8Q-22,-26 -2,-23Q12,-36 30,-22Q50,-24 50,-4Q62,2 54,12Z"/>
<path d="M-26,-8q8,10 18,3q6,-7 -1,-10q-6,-1 -6,5M30,-22q-6,12 4,16q8,2 8,-6q-1,-5 -6,-3" fill="none"/>
</g>"""


def animated(tag_attrs, frames, dur, attr="d"):
    values = ";".join(frames + [frames[0]])
    return (
        f'<path {attr}="{frames[0]}" {tag_attrs}>'
        f'<animate attributeName="{attr}" dur="{dur}s" repeatCount="indefinite" values="{values}"/></path>'
    )


def transform_anim(kind, frames, dur):
    values = ";".join(frames + [frames[0]])
    return (
        f'<animateTransform attributeName="transform" type="{kind}" dur="{dur}s" '
        f'repeatCount="indefinite" values="{values}"/>'
    )


def snow():
    rng = random.Random(7)
    flakes = []
    for _ in range(22):
        x, r = rng.uniform(0, W + 200), rng.uniform(0.8, 2.2)
        dur, begin = rng.uniform(7, 13), -rng.uniform(0, 13)
        flakes.append(
            f'<circle r="{r:.1f}"><animateTransform attributeName="transform" type="translate" '
            f'from="{x:.0f} -10" to="{x - 160:.0f} {H + 10}" dur="{dur:.1f}s" begin="{begin:.1f}s" '
            f'repeatCount="indefinite"/></circle>'
        )
    return f'<g fill="#a9c4e8" fill-opacity="0.75">{"".join(flakes)}</g>'


def render(total, week, login=""):
    d = Dragon(total, week)
    phases = [2 * math.pi * k / FRAMES for k in range(FRAMES)]
    dur = d.dur

    def frames(fn):
        return [fn(ph) for ph in phases]

    legs = {}
    for name, s, front, far in (
        ("ff", 0.21, True, True), ("bf", 0.63, False, True),
        ("fn", 0.17, True, False), ("bn", 0.59, False, False),
    ):
        per = [d.leg(ph, s, front, far) for ph in phases]
        legs[name] = ([p[0] for p in per], [p[1] for p in per], [p[2] for p in per])

    def draw_leg(name, color):
        limb, talons, wisp = legs[name]
        return "".join([
            animated(f'fill="{MANE}" stroke="{MANE_EDGE}" stroke-width="0.9"', wisp, dur),
            animated(f'fill="none" stroke="{OUTLINE}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"', limb, dur),
            animated(f'fill="none" stroke="{color}" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"', limb, dur),
            animated(f'fill="none" stroke="{TALON}" stroke-width="2.8" stroke-linecap="round"', talons, dur),
        ])

    clouds = []
    for y, scale, offset in ((55, 1.0, 0), (240, 0.8, -7), (110, 0.65, -13), (265, 1.1, -19)):
        clouds.append(
            f'<g transform="translate({W + 80} {y})">'
            f'<animateTransform attributeName="transform" type="translate" from="{W + 80} {y}" to="-90 {y}" '
            f'dur="26s" begin="{offset}s" repeatCount="indefinite"/>'
            f'<g transform="scale({scale})">{CLOUD}</g></g>'
        )

    fan = frames(d.tail_fan)
    pose = frames(d.head_pose)
    title = f"Dragon of {login}: {total} contributions this year, {week} in the last 7 days" if login else "Dragon"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" color="#8b949e">',
        f"<title>{title}</title>",
        "<defs>",
        f'<linearGradient id="bodyGrad" gradientUnits="userSpaceOnUse" x1="0" y1="{CY - 50}" x2="0" y2="{CY + 50}">'
        f'<stop offset="0" stop-color="{BODY_TOP}"/><stop offset="1" stop-color="{BODY_BOTTOM}"/></linearGradient>',
        f'<linearGradient id="headGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BODY_TOP}"/>'
        f'<stop offset="1" stop-color="#a7b2c5"/></linearGradient>',
        f'<radialGradient id="fin" cx="0" cy="0.5" r="1"><stop offset="0" stop-color="{FIN_DARK}"/>'
        f'<stop offset="0.75" stop-color="#3b4f8c"/><stop offset="1" stop-color="{FIN_LIGHT}"/></radialGradient>',
        f'<radialGradient id="eyeGlow"><stop offset="0" stop-color="{GLOW}" stop-opacity="0.9"/>'
        f'<stop offset="1" stop-color="{GLOW_DEEP}" stop-opacity="0"/></radialGradient>',
        f'<radialGradient id="pearl" cx="0.38" cy="0.35" r="0.7"><stop offset="0" stop-color="#ffffff"/>'
        f'<stop offset="0.5" stop-color="#cdeeff"/><stop offset="1" stop-color="{GLOW_DEEP}"/></radialGradient>',
        f'<radialGradient id="glow"><stop offset="0" stop-color="{GLOW}" stop-opacity="0.9"/>'
        f'<stop offset="1" stop-color="{GLOW_DEEP}" stop-opacity="0"/></radialGradient>',
        '<filter id="shadow" x="-10%" y="-20%" width="120%" height="140%">'
        '<feDropShadow dx="0" dy="4" stdDeviation="3" flood-color="#0b1020" flood-opacity="0.3"/></filter>',
        "</defs>",
        *clouds,
        snow(),
        '<g filter="url(#shadow)">',
        draw_leg("ff", FAR),
        draw_leg("bf", FAR),
        animated(f'fill="{MANE}" stroke="{MANE_EDGE}" stroke-width="1"', frames(lambda ph: d.mane(ph, True)), dur),
        animated(f'fill="#c9d2e0" stroke="{OUTLINE}" stroke-width="1.1" stroke-linejoin="round"', frames(d.ridge), dur),
        animated(f'fill="url(#fin)" stroke="{OUTLINE}" stroke-width="1.3" stroke-linejoin="round"', [f[0] for f in fan], dur),
        animated(f'fill="none" stroke="{GLOW}" stroke-width="1" stroke-opacity="0.7"', [f[1] for f in fan], dur),
        animated(f'fill="url(#bodyGrad)" stroke="{OUTLINE}" stroke-width="1.8" stroke-linejoin="round"', frames(d.body), dur),
        animated('fill="#ffffff" fill-opacity="0.35"', frames(lambda ph: d.strip(ph, 0.3, 0.78, 0.03, 0.9)), dur),
        animated(f'fill="{BELLY}" stroke="{BELLY_LINE}" stroke-width="0.8"', frames(lambda ph: d.strip(ph, -0.22, -0.97, 0.02, 0.97)), dur),
        animated(f'fill="none" stroke="{BELLY_LINE}" stroke-width="1"', frames(d.belly_lines), dur),
        animated(f'fill="none" stroke="{SCALE}" stroke-width="1.1" stroke-opacity="0.85"', frames(d.scales), dur),
        animated(f'fill="{MANE}" stroke="{MANE_EDGE}" stroke-width="1"', frames(lambda ph: d.mane(ph, False)), dur),
        draw_leg("fn", "url(#bodyGrad)"),
        draw_leg("bn", "url(#bodyGrad)"),
        # head
        f'<g transform="translate({pose[0][0]})">{transform_anim("translate", [p[0] for p in pose], dur)}',
        f'<g transform="rotate({pose[0][1]})">{transform_anim("rotate", [p[1] for p in pose], dur)}',
        '<g transform="scale(1.35)">',
        animated(f'fill="{MANE}" stroke="{MANE_EDGE}" stroke-width="0.9"', frames(d.head_mane), dur),
        animated(f'fill="none" stroke="{OUTLINE}" stroke-width="2.4" stroke-linecap="round"', frames(d.whiskers), dur),
        animated(f'fill="none" stroke="{MANE}" stroke-width="1.3" stroke-linecap="round"', frames(d.whiskers), dur),
        HEAD,
        "</g></g></g>",
        "</g>",
        # ice pearl
        f'<g transform="translate({d.pearl_pos(0)})">{transform_anim("translate", frames(d.pearl_pos), dur)}',
        f'<circle r="30" fill="url(#glow)" opacity="{d.glow:.2f}">'
        '<animate attributeName="r" values="26;34;26" dur="2.4s" repeatCount="indefinite"/></circle>',
        '<g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="6s" repeatCount="indefinite"/>',
        "".join(
            f'<path transform="rotate({a})" d="M0,-11C7,-16 6,-24 0,-28C9,-24 12,-14 6,-9Z" fill="{GLOW}" fill-opacity="0.75"/>'
            for a in range(0, 360, 60)
        ),
        "</g>",
        f'<circle r="11" fill="url(#pearl)" stroke="{GLOW_DEEP}" stroke-width="1"/>',
        "</g>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--login", default=os.environ.get("GITHUB_REPOSITORY_OWNER", ""))
    parser.add_argument("--total", type=int, help="contributions in the last year (skips the API)")
    parser.add_argument("--week", type=int, help="contributions in the last 7 days (skips the API)")
    parser.add_argument("--out", default="dragon.svg")
    args = parser.parse_args()

    total, week = args.total, args.week
    if total is None or week is None:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not (args.login and token):
            raise SystemExit("Need --login and GITHUB_TOKEN, or pass --total and --week.")
        fetched_total, fetched_week = fetch_activity(args.login, token)
        total = fetched_total if total is None else total
        week = fetched_week if week is None else week

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render(total, week, args.login))
    print(f"{args.out}: {total} contributions this year, {week} this week")


if __name__ == "__main__":
    main()
