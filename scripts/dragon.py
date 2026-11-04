#!/usr/bin/env python3
"""Draw an animated Chinese dragon (SVG) from a GitHub account's activity.

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
import urllib.request

W, H = 900, 270
CY = 140
FRAMES = 24

# Palette
OUTLINE = "#2b0508"
RED_TOP, RED_BOTTOM = "#ef3b3b", "#9a0a1f"
RED_FAR = "#7e0a1b"
SCALE = "#7a0717"
GOLD = "#f7bd34"
GOLD_DARK = "#c98a1b"
CREAM = "#ffe0a0"
FIRE = "#ff7a1a"
HORN = "#f3dcab"


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
        amp = 7 + 36 * smoothstep(0.0, 0.45, s)
        x = self.xh - s * self.L
        y = CY + amp * math.sin(2 * math.pi * 1.55 * s - ph)
        return (x, y)

    def frame_at(self, s, ph):
        """Centre point, tail-ward tangent and dorsal (upward) normal at s."""
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
        return (14 + 6 * smoothstep(0.0, 0.14, s)) * (1 - 0.86 * smoothstep(0.32, 1.0, s))

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
        c, t, _ = self.frame_at(1.0, ph)
        tip = add(c, mul(t, 5))
        return curve(upper + [tip] + lower[::-1], closed=True)

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
        for s in self.steps(0.03, 0.95, 0.55):
            c, t, n = self.frame_at(s, ph)
            w = self.hw(s)
            a = add(c, mul(n, -0.25 * w))
            b = add(c, mul(n, -0.95 * w))
            q = add(add(c, mul(n, -0.6 * w)), mul(t, 0.3 * w))
            out.append(f"M{pt(a)}Q{pt(q)} {pt(b)}")
        return "".join(out)

    def scales(self, ph):
        out = []
        for row, (offset, shift) in enumerate(((0.62, 0.0), (0.12, 0.5))):
            for s in self.steps(0.04 + shift * 0.012, 0.93, 0.62):
                c, t, n = self.frame_at(s, ph)
                w = self.hw(s)
                r = 0.3 * w
                p = add(c, mul(n, offset * w))
                a = add(p, mul(n, r))
                b = sub(p, mul(n, r))
                q = add(p, mul(t, 1.5 * r))
                out.append(f"M{pt(a)}Q{pt(q)} {pt(b)}")
        return "".join(out)

    def dorsal(self, ph):
        ss = self.steps(0.02, 0.9, 0.95)
        pts = []
        for k, s in enumerate(ss):
            c, _, n = self.frame_at(s, ph)
            w = self.hw(s)
            pts.append(add(c, mul(n, 0.6 * w)))
            gap = (ss[k + 1] - s) if k + 1 < len(ss) else 0.01
            ct, _, nt = self.frame_at(min(1.0, s + 0.75 * gap), ph)
            h = 4 + 9 * (1 - s) + 1.5 * math.sin(ph * 2 + k)
            pts.append(add(ct, mul(nt, self.hw(s + 0.75 * gap) + h)))
        for s in reversed(ss):
            pts.append(self.frame_at(s, ph)[0])
        return poly(pts)

    def tail_fire(self, ph, inner):
        c, t, _ = self.frame_at(1.0, ph)
        out = []
        for k, ang in enumerate((-0.85, -0.42, 0.0, 0.42, 0.85)):
            length = (26 + 16 * math.cos(ang)) * (0.62 if inner else 1.0)
            d = rot(t, ang + 0.18 * math.sin(ph * 2 + k * 1.3))
            p = rot(d, math.pi / 2)
            base_w = 3.5 if inner else 5
            mid = add(c, mul(d, length * 0.55))
            tip = add(add(c, mul(d, length)), mul(p, 5 * math.sin(ph + k)))
            out.append(
                f"M{pt(add(c, mul(p, base_w)))}Q{pt(add(mid, mul(p, base_w * 1.6)))} {pt(tip)}"
                f"Q{pt(add(mid, mul(p, -base_w * 0.4)))} {pt(sub(c, mul(p, base_w)))}Z"
            )
        return "".join(out)

    def leg(self, ph, s, front, far):
        """Returns (limb path, claws path, elbow tuft path)."""
        c, t, n = self.frame_at(s, ph)
        fwd, down = mul(t, -1), mul(n, -1)
        hip = add(c, mul(n, -0.35 * self.hw(s)))
        swing = 0.45 * math.sin(ph + (0 if front else math.pi) + (0.6 if far else 0))
        if front:
            a = 0.55 + swing
            knee = add(hip, mul(add(mul(down, math.cos(a)), mul(fwd, -math.sin(a))), 21))
            fore = unit(add(mul(down, 0.55), mul(fwd, 0.85)))
        else:
            a = 0.65 + swing
            knee = add(hip, mul(add(mul(down, math.cos(a)), mul(fwd, math.sin(a))), 21))
            fore = unit(add(mul(down, 0.75), mul(fwd, -0.65)))
        foot = add(knee, mul(fore, 16))
        limb = f"M{pt(hip)}L{pt(knee)}L{pt(foot)}"
        claws = []
        for ang in (-0.6, 0.0, 0.6):
            d = rot(fore, ang)
            tip = add(foot, mul(d, 8))
            q = add(add(foot, mul(d, 4)), mul(rot(d, math.pi / 2), 1.8))
            claws.append(f"M{pt(foot)}Q{pt(q)} {pt(tip)}")
        back = mul(fwd, -1)
        tuft = poly([
            add(knee, mul(rot(back, 0.5), 2)),
            add(knee, mul(rot(back, -0.35), 13)),
            add(knee, mul(rot(back, -0.9), 3)),
            add(knee, mul(rot(back, -1.1), 10)),
            add(knee, mul(down, 2)),
        ])
        return limb, "".join(claws), tuft

    def head_pose(self, ph):
        c, t, _ = self.frame_at(0.0, ph)
        ang = math.degrees(math.atan2(-t[1], -t[0]))
        return f"{num(c[0])} {num(c[1])}", num(ang)

    @staticmethod
    def whiskers(ph):
        sway = math.sin(ph)
        sway2 = math.sin(ph + 1.1)
        return (
            f"M58,4C68,14 {num(52 + 3 * sway)},{num(26 + 3 * sway)} {num(22 + 6 * sway)},{num(32 + 5 * sway2)}"
            f"M60,-4C70,-16 {num(54 + 3 * sway2)},{num(-30 - 3 * sway)} {num(26 + 6 * sway2)},{num(-36 - 4 * sway)}"
        )

    def pearl_pos(self, ph):
        return f"{num(self.xh + 150)} {num(CY - 14 + 7 * math.sin(ph))}"


# ----------------------------------------------------------------- svg ----
HEAD = f"""
<path d="M6,-14Q-22,-28 -40,-28Q-22,-14 -2,-6Z" fill="{FIRE}" stroke="{OUTLINE}" stroke-width="1.3" stroke-linejoin="round"/>
<path d="M4,8Q-16,18 -30,30Q-10,26 8,14Z" fill="{FIRE}" stroke="{OUTLINE}" stroke-width="1.3" stroke-linejoin="round"/>
<path d="M4,-10Q-28,-14 -50,-12Q-26,-2 0,0Z" fill="{GOLD}" stroke="{OUTLINE}" stroke-width="1.3" stroke-linejoin="round"/>
<path d="M2,2Q-26,10 -44,18Q-22,20 4,12Z" fill="{GOLD}" stroke="{OUTLINE}" stroke-width="1.3" stroke-linejoin="round"/>
<path d="M2,-4Q-30,-2 -52,4Q-28,10 2,8Z" fill="{FIRE}" stroke="{OUTLINE}" stroke-width="1.3" stroke-linejoin="round"/>
<g stroke-linecap="round" fill="none">
  <path d="M10,-14C0,-30 -14,-36 -30,-42M-6,-30C-4,-40 -10,-46 -16,-52" stroke="{OUTLINE}" stroke-width="7"/>
  <path d="M10,-14C0,-30 -14,-36 -30,-42M-6,-30C-4,-40 -10,-46 -16,-52" stroke="#b8996a" stroke-width="4.5"/>
  <path d="M15,-12C5,-28 -9,-34 -25,-38M-1,-27C1,-38 -3,-44 -9,-50" stroke="{OUTLINE}" stroke-width="7.5"/>
  <path d="M15,-12C5,-28 -9,-34 -25,-38M-1,-27C1,-38 -3,-44 -9,-50" stroke="{HORN}" stroke-width="5"/>
</g>
<path d="M2,8C20,10 38,12 54,12C57,16 53,21 46,21C30,23 14,22 0,18Z" fill="#b30c25" stroke="{OUTLINE}" stroke-width="1.4"/>
<path d="M14,6C30,8 44,8 57,6L55,13C40,13 26,12 14,10Z" fill="#3d0610"/>
<path d="M30,10C40,10 47,11 52,15C55,19 59,19 61,15M57,18C59,21 62,21 64,19" stroke="#ff6b81" stroke-width="2.2" fill="none" stroke-linecap="round"/>
<path d="M50,13l2,-6l2.2,6ZM40,13l1.6,-4.5l1.8,4.5Z" fill="#fff8e7"/>
<path d="M-6,-12C0,-20 10,-22 18,-19C26,-16 34,-15 44,-13C52,-12 58,-14 63,-10C68,-6 68,2 62,5C56,7 50,6 44,6C32,6 20,5 12,8C6,10 0,14 -6,14C-11,8 -11,-6 -6,-12Z" fill="url(#headGrad)" stroke="{OUTLINE}" stroke-width="1.5" stroke-linejoin="round"/>
<path d="M40,-12Q46,-8 52,-11M30,-14Q36,-10 42,-13M50,-8Q55,-4 60,-8" stroke="{SCALE}" stroke-width="1" fill="none"/>
<path d="M2,6L-9,20L4,14L-1,27L10,16L12,25L18,10Z" fill="{GOLD}" stroke="{OUTLINE}" stroke-width="1.2" stroke-linejoin="round"/>
<path d="M22,20C22,28 18,36 9,43C22,39 29,30 31,21Z" fill="{GOLD}" stroke="{OUTLINE}" stroke-width="1.2"/>
<path d="M14,-16C8,-23 1,-25 -8,-25C1,-20 5,-16 10,-13ZM14,-16C20,-23 31,-21 35,-15C29,-16 22,-15 18,-12Z" fill="{GOLD}" stroke="{OUTLINE}" stroke-width="1.2" stroke-linejoin="round"/>
<ellipse cx="26" cy="-10" rx="5.2" ry="3.7" fill="#ffe066" stroke="{OUTLINE}" stroke-width="1.3"/>
<ellipse cx="27" cy="-10" rx="1.4" ry="3.1" fill="#140303"/>
<circle cx="25.2" cy="-11.4" r="0.9" fill="#fff"/>
<path d="M60,-6c3,-2 5,1 3,3c-2,1 -3,-1 -1,-2" stroke="{OUTLINE}" stroke-width="1.2" fill="none"/>
"""

CLOUD = """<g fill="currentColor" fill-opacity="0.08" stroke="currentColor" stroke-opacity="0.32" stroke-width="2" stroke-linecap="round">
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
        limb, claws, tuft = legs[name]
        return "".join([
            animated(f'fill="{FIRE}" stroke="{OUTLINE}" stroke-width="1.1" stroke-linejoin="round"', tuft, dur),
            animated(f'fill="none" stroke="{OUTLINE}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"', limb, dur),
            animated(f'fill="none" stroke="{color}" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"', limb, dur),
            animated(f'fill="none" stroke="{OUTLINE}" stroke-width="4" stroke-linecap="round"', claws, dur),
            animated(f'fill="none" stroke="{GOLD}" stroke-width="2.2" stroke-linecap="round"', claws, dur),
        ])

    clouds = []
    for i, (y, scale, offset) in enumerate(((60, 1.0, 0), (215, 0.8, -7), (110, 0.65, -13), (235, 1.1, -19))):
        clouds.append(
            f'<g transform="translate({W + 80} {y})">'
            f'<animateTransform attributeName="transform" type="translate" from="{W + 80} {y}" to="-90 {y}" '
            f'dur="26s" begin="{offset}s" repeatCount="indefinite"/>'
            f'<g transform="scale({scale})">{CLOUD}</g></g>'
        )

    pose = frames(d.head_pose)
    title = f"Dragon of {login}: {total} contributions this year, {week} in the last 7 days" if login else "Dragon"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" color="#8b949e">',
        f"<title>{title}</title>",
        "<defs>",
        f'<linearGradient id="bodyGrad" gradientUnits="userSpaceOnUse" x1="0" y1="{CY - 50}" x2="0" y2="{CY + 50}">'
        f'<stop offset="0" stop-color="{RED_TOP}"/><stop offset="1" stop-color="{RED_BOTTOM}"/></linearGradient>',
        f'<linearGradient id="headGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{RED_TOP}"/>'
        f'<stop offset="1" stop-color="#b30c25"/></linearGradient>',
        f'<linearGradient id="fire" x1="1" y1="0" x2="0" y2="0"><stop offset="0" stop-color="{GOLD}"/>'
        f'<stop offset="1" stop-color="{FIRE}"/></linearGradient>',
        '<radialGradient id="pearl" cx="0.38" cy="0.35" r="0.7"><stop offset="0" stop-color="#ffffff"/>'
        '<stop offset="0.45" stop-color="#fff1c2"/><stop offset="1" stop-color="#ffb21a"/></radialGradient>',
        '<radialGradient id="glow"><stop offset="0" stop-color="#ffcf4d" stop-opacity="0.9"/>'
        '<stop offset="1" stop-color="#ff7a1a" stop-opacity="0"/></radialGradient>',
        '<filter id="shadow" x="-10%" y="-20%" width="120%" height="140%">'
        '<feDropShadow dx="0" dy="4" stdDeviation="3" flood-color="#000" flood-opacity="0.25"/></filter>',
        "</defs>",
        *clouds,
        '<g filter="url(#shadow)">',
        draw_leg("ff", RED_FAR),
        draw_leg("bf", RED_FAR),
        animated(f'fill="url(#fire)" stroke="{OUTLINE}" stroke-width="1.2" stroke-linejoin="round"', frames(d.dorsal), dur),
        animated(f'fill="{FIRE}" stroke="{OUTLINE}" stroke-width="1.2"', frames(lambda ph: d.tail_fire(ph, False)), dur),
        animated(f'fill="{GOLD}"', frames(lambda ph: d.tail_fire(ph, True)), dur),
        animated(f'fill="url(#bodyGrad)" stroke="{OUTLINE}" stroke-width="1.8" stroke-linejoin="round"', frames(d.body), dur),
        animated('fill="#ffffff" fill-opacity="0.16"', frames(lambda ph: d.strip(ph, 0.3, 0.78, 0.03, 0.9)), dur),
        animated(f'fill="{CREAM}" stroke="{GOLD_DARK}" stroke-width="0.8"', frames(lambda ph: d.strip(ph, -0.22, -0.97, 0.02, 0.96)), dur),
        animated(f'fill="none" stroke="{GOLD_DARK}" stroke-width="1.1"', frames(d.belly_lines), dur),
        animated(f'fill="none" stroke="{SCALE}" stroke-width="1.15" stroke-opacity="0.85"', frames(d.scales), dur),
        draw_leg("fn", "url(#bodyGrad)"),
        draw_leg("bn", "url(#bodyGrad)"),
        # head
        f'<g transform="translate({pose[0][0]})">{transform_anim("translate", [p[0] for p in pose], dur)}',
        f'<g transform="rotate({pose[0][1]})">{transform_anim("rotate", [p[1] for p in pose], dur)}',
        '<g transform="scale(1.35)">',
        animated(f'fill="none" stroke="{OUTLINE}" stroke-width="2.6" stroke-linecap="round"', frames(d.whiskers), dur),
        animated(f'fill="none" stroke="{GOLD}" stroke-width="1.3" stroke-linecap="round"', frames(d.whiskers), dur),
        HEAD,
        "</g></g></g>",
        "</g>",
        # flaming pearl
        f'<g transform="translate({d.pearl_pos(0)})">{transform_anim("translate", frames(d.pearl_pos), dur)}',
        f'<circle r="30" fill="url(#glow)" opacity="{d.glow:.2f}">'
        '<animate attributeName="r" values="26;33;26" dur="2.4s" repeatCount="indefinite"/></circle>',
        '<g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="6s" repeatCount="indefinite"/>',
        "".join(
            f'<path transform="rotate({a})" d="M0,-11C7,-16 6,-24 0,-28C9,-24 12,-14 6,-9Z" fill="{FIRE}" fill-opacity="0.85"/>'
            for a in range(0, 360, 60)
        ),
        "</g>",
        f'<circle r="11" fill="url(#pearl)" stroke="{GOLD_DARK}" stroke-width="1"/>',
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
