# Video Studio

A ready-to-use workspace for making videos with code: HyperFrames for HTML and GSAP motion, Remotion for React-based video, and FFmpeg for encoding and editing. Each tool ships with a small working demo so you can start from something that already renders.

## Quick start

```bash
./scripts/setup.sh    # install or update everything (safe to re-run)
./scripts/verify.sh   # 37 end-to-end checks, outputs land in verify-output/
```

## What's inside

| Folder | Tool | What the demo does |
| --- | --- | --- |
| `hyperframes/` | HyperFrames 0.8.214, GSAP 3.14.2 (vendored in `assets/vendor/`) | 8 s, 1080p30 film in two scenes with a music bed. Headline and accent colour are variables. |
| `remotion/` | Remotion 4.0.539, React 19, TypeScript | The same film as React components, with spring animation, a slide transition, noise-driven particles and an audio fade. Comes in 16:9 (`Demo`) and 9:16 (`DemoVertical`). |
| `scripts/` | Bash + FFmpeg 6.1 | `setup.sh` installs, `verify.sh` tests every part of the chain, `cloud-env-setup.sh` is the version for Claude Code cloud environments. |

## Claude Code cloud sessions

Cloud containers start fresh each session, so global installs are lost. To have everything ready automatically, open the cloud environment menu in the session's title bar, choose Edit, and paste the contents of `scripts/cloud-env-setup.sh` into **Setup script**. New sessions will run it before starting.

Extra Remotion packages already installed: `@remotion/transitions`, `@remotion/media`, `@remotion/media-utils`, `@remotion/captions`, `@remotion/shapes`, `@remotion/noise`, and `@fontsource/inter` for offline fonts.

## Everyday commands

HyperFrames (run inside `hyperframes/`):

```bash
npx hyperframes preview --background   # Studio preview in the browser
npx hyperframes check                  # lint, runtime, layout and contrast in one pass
npx hyperframes snapshot --at 1,3,5    # PNG frames to eyeball before rendering
npx hyperframes render -o renders/film.mp4
npx hyperframes render --format mov    # ProRes 4444 with alpha
npx hyperframes render --variables '{"headline":"Launch day"}'
```

Remotion (run inside `remotion/`):

```bash
npm run dev                                          # Remotion Studio
npm run render                                       # out/demo.mp4
npx remotion render DemoVertical out/vertical.mp4    # 9:16 for Reels, Shorts, TikTok
npx remotion render Demo out/demo.mov --codec=prores --prores-profile=4444
npx remotion render Demo out/custom.mp4 --props='{"title":"Hello","accent":"#3b82f6"}'
```

FFmpeg recipes that `verify.sh` proves work on this machine: H.264, HEVC, VP9, AV1, ProRes 422 HQ and 4444 with alpha, GIF, trim and concat, crossfades, 16:9 to 9:16 reframing, text overlays, burned-in subtitles, picture in picture, speed ramps, music ducking under voice, loudness normalisation to -14 LUFS, colour grading, stabilisation and contact sheets. Copy the exact commands from `scripts/verify.sh`.

## Notes

- **Agent skills.** `setup.sh` installs the HyperFrames skills (`hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use`) into `~/.claude/skills`, so Claude Code knows the HyperFrames contract in later sessions. Remotion's own skills can be added with `npx skills add remotion-dev/skills`.
- **Offline-friendly rendering.** GSAP is loaded from `assets/vendor/` rather than a CDN, and Inter comes from `@fontsource`, so renders never depend on the network.
- **Browser for Remotion.** `remotion.config.ts` reuses a Chrome Headless Shell that is already on disk (Playwright's or HyperFrames' copy, or `REMOTION_BROWSER_EXECUTABLE`). Without one, Remotion downloads its own on first render as usual.
- **Optional AI extras** reported by `hyperframes doctor`: whisper.cpp for transcription, Kokoro for local text to speech and MusicGen for generated music. None are needed to create or render videos.
- **Licences.** Remotion is free for individuals and small teams but needs a company licence above that size; check [remotion.dev/license](https://www.remotion.dev/license). GSAP is free under its standard licence.
