"""Run spotter over the bundled scenarios, print a summary, and write report.html
and report.json. Offline, no API key.  Run:  python examples/run_demo.py"""
import os
import sys
import json
import datetime
import html

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from spotter import Spotter, DEFAULT_CHECKS, Verdict
from spotter.scenarios import SCENARIOS

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPTS = {ctx.key: ctx.prompt for ctx, _ in SCENARIOS}
ENVS = {ctx.key: ctx.env_key for ctx, _ in SCENARIOS}

CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { background:#FBFBF9; color:#0B0B0B; margin:0;
  font-family: ui-serif, Georgia, 'Times New Roman', serif; line-height:1.5; }
.wrap { max-width: 820px; margin:0 auto; padding:60px 30px 80px; }
.mark { font-size:21px; font-weight:700; letter-spacing:.04em; }
.defn { font-style:italic; color:#555; margin-top:2px; font-size:15px; }
.thesis { font-size:25px; line-height:1.38; margin:38px 0 6px; }
.thesis em { font-style:italic; }
.sub { color:#555; font-size:15px; margin-bottom:8px; }
.sec { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; text-transform:uppercase;
  letter-spacing:.14em; font-size:11px; color:#666; border-top:1px solid #0B0B0B;
  padding-top:9px; margin:46px 0 16px; }
table { width:100%; border-collapse:collapse; }
th,td { text-align:left; padding:11px 8px; border-bottom:1px solid #DEDED6; vertical-align:baseline; }
th { font-family: ui-monospace, monospace; font-size:10.5px; letter-spacing:.12em;
  text-transform:uppercase; color:#777; font-weight:400; }
.task { font-weight:700; }
.env { font-family: ui-monospace, monospace; font-size:12px; color:#666; }
.mono { font-family: ui-monospace, monospace; }
.score { font-family: ui-monospace, monospace; font-size:15px; }
.dim { color:#9A9A92; }
.arrow { color:#B5B5AD; padding:0 5px; }
.blocked { font-family: ui-monospace, monospace; font-weight:700; font-size:11px;
  letter-spacing:.08em; border:1.5px solid #0B0B0B; padding:1px 7px; white-space:nowrap; }
.open { font-family: ui-monospace, monospace; font-size:11px; color:#666; letter-spacing:.08em; }
.cnt { font-family: ui-monospace, monospace; font-size:11px; color:#8A8A82; letter-spacing:.03em; }
.finding { margin:16px 0; padding-left:15px; border-left:2px solid #0B0B0B; }
.fid { font-family: ui-monospace, monospace; font-size:12px; font-weight:700; letter-spacing:.04em; }
.ftitle { font-size:15px; }
.warn .fid, .warn { border-color:#9A9A92; }
.ev { font-family: ui-monospace, monospace; font-size:12.5px; color:#333; background:#F1F1EA;
  padding:7px 9px; margin-top:6px; display:block; border-radius:2px; }
.passes { font-family: ui-monospace, monospace; font-size:12px; color:#777; margin-top:8px; }
.foot { margin-top:46px; border-top:1px solid #0B0B0B; padding-top:13px; font-size:12.5px; color:#666; }
.foot a { color:#0B0B0B; }
sup { font-size:.66em; vertical-align:super; line-height:0; }
.fnote { font-size:12.5px; color:#555; margin-top:22px; font-style:italic; }
"""


def esc(s):
    return html.escape(str(s))


def render_html(results, generated):
    n_blocked = sum(1 for r in results if r.verdict == Verdict.UNSAFE)

    parts = []
    parts.append("<!doctype html><html lang='en'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append("<title>spotter safety report</title><style>" + CSS + "</style></head><body><div class='wrap'>")

    # header / definition (echoes Fleet's /flēt/ dictionary entry)
    parts.append("<div class='mark'>spotter</div>")
    parts.append("<div class='defn'>/ˈspätər/ &nbsp;<i>n.</i> the one who watches a lift and catches the bar before it drops.</div>")

    parts.append("<div class='thesis'>A Fleet <em>verifier</em> scores whether the agent finished the task. "
                 "spotter scores whether it finished <em>safely</em>.</div>")
    parts.append("<div class='sub'>Two tasks below. Both scored a perfect <span class='mono'>1.00</span> for completion. "
                 "spotter blocked " + ("both." if n_blocked == 2 else str(n_blocked) + " of 2.") + "</div>")

    # section 1: the run
    parts.append("<div class='sec'>01 / The run</div>")
    parts.append("<table><thead><tr><th>Task</th><th>Environment</th><th>Completion</th><th>Safety</th><th>Final</th></tr></thead><tbody>")
    for r in results:
        if r.verdict == Verdict.UNSAFE:
            safety = "<span class='blocked'>BLOCKED</span><span class='cnt'> " + str(len(r.blockers)) + " blk &middot; " + str(len(r.warnings)) + " warn</span>"
            final = "<span class='score'>" + ("%.2f" % r.final_score) + "</span>"
            comp = "<span class='score dim'>" + ("%.2f" % r.completion_score) + "</span>"
        else:
            safety = "<span class='open'>" + esc(r.verdict.value) + "</span><span class='cnt'> " + str(len(r.blockers)) + " blk &middot; " + str(len(r.warnings)) + " warn</span>"
            final = "<span class='score'>" + ("%.2f" % r.final_score) + "</span>"
            comp = "<span class='score'>" + ("%.2f" % r.completion_score) + "</span>"
        parts.append(
            "<tr><td class='task'>" + esc(r.key) + "</td>"
            "<td class='env'>" + esc(ENVS.get(r.key, "")) + "</td>"
            "<td>" + comp + "</td>"
            "<td>" + safety + "</td>"
            "<td>" + comp_to_final(r) + "</td></tr>"
        )
    parts.append("</tbody></table>")

    # section 2: why
    parts.append("<div class='sec'>02 / Why spotter blocked them</div>")
    for r in results:
        parts.append("<div style='margin:22px 0 6px;'><span class='task'>" + esc(r.key) + "</span> "
                     "<span class='env'>&nbsp;" + esc(PROMPTS.get(r.key, "")) + "</span></div>")
        for f in r.blockers:
            parts.append(
                "<div class='finding'><span class='fid'>" + esc(f.id) + "</span> &nbsp;"
                "<span class='ftitle'>" + esc(f.title) + "</span>"
                "<span class='ev'>" + esc(f.evidence) + "</span></div>"
            )
        for f in r.warnings:
            parts.append(
                "<div class='finding warn'><span class='fid'>" + esc(f.id) + " (warn)</span> &nbsp;"
                "<span class='ftitle'>" + esc(f.title) + "</span>"
                "<span class='ev'>" + esc(f.evidence) + "</span></div>"
            )
        parts.append("<div class='passes'>" + str(len(r.passes)) + " checks passed &middot; "
                     + str(len(r.blockers)) + " blockers &middot; " + str(len(r.warnings)) + " warnings</div>")

    # footnote (Fleet's signature device)
    parts.append("<div class='fnote'>The gate rule<sup>1</sup>: any blocker forces the final score to "
                 "<span class='mono'>0.00</span>, regardless of completion. Warnings are surfaced and do not gate. "
                 "A clean run passes the completion score through untouched.</div>")

    parts.append("<div class='foot'>Built on the <span class='mono'>fleet-python</span> result shape "
                 "(<span class='mono'>verify_detailed</span> &rarr; safety-gated result). "
                 "Independent work sample, not affiliated with Fleet. "
                 "Generated " + esc(generated) + ".<br>"
                 "Lawrence Wolters &middot; <a href='https://github.com/CodedVibesX'>github.com/CodedVibesX</a> "
                 "&middot; codedvibesx@gmail.com</div>")

    parts.append("</div></body></html>")
    return "".join(parts)


def comp_to_final(r):
    if r.verdict == Verdict.UNSAFE:
        return ("<span class='score dim'>%.2f</span><span class='arrow'>&rarr;</span>"
                "<span class='score'>%.2f</span>") % (r.completion_score, r.final_score)
    return "<span class='score'>%.2f</span>" % r.final_score


def main():
    spotter = Spotter(DEFAULT_CHECKS)
    results = [spotter.gate(ctx, comp) for ctx, comp in SCENARIOS]
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(os.path.join(REPO, "report.json"), "w") as f:
        json.dump({"generated": generated, "results": [r.to_dict() for r in results]}, f, indent=2)
    with open(os.path.join(REPO, "report.html"), "w") as f:
        f.write(render_html(results, generated))

    any_unsafe = False
    for r in results:
        print("[%s] %-26s completion=%.2f  final=%.2f  blockers=%d  warnings=%d"
              % (r.verdict.value, r.key, r.completion_score, r.final_score, len(r.blockers), len(r.warnings)))
        any_unsafe = any_unsafe or (r.verdict == Verdict.UNSAFE)
    print("\nSafety gate:", "BLOCKED at least one task (exit 1)" if any_unsafe else "all clear (exit 0)")
    sys.exit(1 if any_unsafe else 0)


if __name__ == "__main__":
    main()
