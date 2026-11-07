# Refit film studio — recording and truth guide

A standalone, browser-recordable motion sequence for the Vultr Agent Rush submission. It is an **editorial visualization built from documented Refit runs**, not a simulation of the live application. It does not invoke models or modify production data.

## Start and record

From the repository root:

```bash
cd web
python3 -m http.server 3000
# open http://localhost:3000/film/
```

For a clean screen recording:
1. Set browser/OS capture to **1920 × 1080**, 30 fps, full screen.
2. Open `/film/`. Press **F** for fullscreen; **H** to hide the recording console; **R** to replay from zero. Press **Space** to pause/resume.
3. The sequence is exactly **02:45**. Use **C** to toggle captioned narration if desired. Without captions, record your own voiceover separately; the page contains the script in each `data-narration` attribute.
4. **1–9** jumps to the corresponding shot; **←/→** moves between shots. Use these to record clean pickups.
5. You can record without hitting record at the exact millisecond: press Space after starting capture, and trim lead/tail silence in the editor. The progress controls are outside the fixed 1600×900 film canvas and disappear in clean mode.

No audio is bundled. Add licensed or original sound in the editor. Do not use another company's trailer or unlicensed score.

## Shot plan (timed sequence)

| Film time | Shot | Evidence / truth condition | Pickup? |
| --- | --- | --- | --- |
| 00:00–00:12 | Failed required lookup | Real Nov 6 DeepSeek→Muse refund replay. Missing `get_order`, not invented dialogue. | Capture real case/trace from recorded report |
| 00:12–00:26 | Core product question | Refit's purpose | Intro film |
| 00:26–00:48 | Agent→Refit→model | **Illustrative diagram**, not a recorded agent import | Replace/overlay with authentic browser import steps |
| 00:48–01:12 | Baseline 8/8 vs unchanged replacement 5/8 | Training cases for run #42193722623 | Actual run evidence zoom |
| 01:12–01:36 | Instruction adaptation | **Editorial summary**; does not pretend to quote unseen patch bytes | Actual patch diff/replay artifact |
| 01:36–01:56 | Repaired training 8/8; independent validation 8/8 | Recorded accepted repair; the reused task families limit broad reliability claims | Actual verifier and context |
| 01:56–02:15 | Rejected candidate 8/8 train, 7/8 validation | **Different** historical run #42192866064, with export withheld | Separate source screenshot/receipt |
| 02:15–02:34 | 24/24 gVisor cleanup | **Different** archived Vultr-host frozen-patch run, not proof of arbitrary hostile containment by itself | Real restricted-action denial / cleanup capture |
| 02:34–02:45 | Closing claim + URL | Public guest preview /app and GitHub repo | Actual app URL and export view |

### Additional real-footage captures required for a strong entry

**A — 20–30 seconds: public Refit workspace.**
Open https://80.240.30.92/app in a private browser tab. Record guest overview → Agents → recorded sample → configuration → review → Evidence and verified export. Guest exploration is an archived recorded run; **don't call it live inference**. Capture a signed-in import with an authorized test account only if it works; don't spend inference purely for footage without an explicit budget. Show genuine behavior and stay within current supported runtime.

**B — 15–25 seconds: actual failed tool behavior.**
Show the underlying run's source-vs-target evidence or its trace artifact. Zoom or highlight the absent `get_order` step. Do **not** fabricate a support reply or database mutation. Actual documented experiment: https://github.com/Davemafy/refit/actions/runs/42193722623.

**C — 10–15 seconds: actual validation and rejected patch.**
Display genuine pass/fail lines and the reason a proposed change did not qualify. The rejected historical run is https://github.com/Davemafy/refit/actions/runs/42192866064.

**D — 10–15 seconds: live containment demonstration.**
The hackathon requires a containment moment. Record a *controlled*, non-sensitive blocked operation inside gVisor (for example, a worker trying to access a network destination, with the resulting denied connection and verified cleanup) on the authorized test host. Keep the host and sandbox clearly labeled. Do not use a fabricated UI badge as a substitute. If you cannot capture the denial, do not describe this film as complete.

**E — 8–12 seconds: final verifiable receipt.**
Use the current public Refit app or recorded artifact endpoint, showing run ID, verified check and download. The self-service app's public Python example is a **different compatible-no-repair run** from the successful synthetic refund repair. Don't cut them together as if they are the same migration.

## Editing strategy

This page supplies a *single polished visual grammar*. For the strongest final edit:
- Use scene footage as visual transitions/opening/closing, and real app/terminal evidence as the main demonstration.
- Prefer hard cuts on real actions. Use controlled short morphs for comparison and annotation; do not transition every shot.
- Never change a pass count, response, source revision, timestamp or model identity for visual convenience.
- Call out the distinct provenance when jumping between different runs.
- Use a quiet, deliberate original soundtrack or none; the demo should remain understandable muted.
- Export H.264, 1920×1080, 30 fps, at a readable bitrate. Watch the exported file at real size on a phone and on a desktop before submission.
- Record a second 30-second social cut after the judge version is complete.

## Real references

- Accepted repair, real Vultr requests: https://github.com/Davemafy/refit/blob/main/docs/live-evidence-2026-11-06.md
- Historical rejected candidate: https://github.com/Davemafy/refit/actions/runs/42192866064
- Host fixed-patch 24/24 cleanup: https://github.com/Davemafy/refit/blob/main/docs/vultr-frozen-patch-recovery-2026-11-06.md
- Post-hoc repair ablation / caveat: https://github.com/Davemafy/refit/blob/main/docs/causal-ablation-evidence-2026-11-06.md
- Real public browser workflow: https://github.com/Davemafy/refit/blob/main/docs/bring-your-agent.md

## Scope

The animated presentation is separate from the Refit production application. No production route, migration engine, API, CI job, authentication handler or inference budget is changed. The demo intentionally avoids adding a new workflow to Refit's sidebar.
