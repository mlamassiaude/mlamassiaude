#!/usr/bin/env bash
# End-to-end check of the video toolchain: FFmpeg codecs and edit operations,
# a HyperFrames render and a Remotion render, each validated with ffprobe.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/verify-output"
rm -rf "$OUT" && mkdir -p "$OUT"
LOG="$OUT/verify.log"
: >"$LOG"

PASS=0
FAIL=0
FAILED=()

run() {
  local name="$1"
  shift
  if "$@" >>"$LOG" 2>&1; then
    printf '  \033[32mPASS\033[0m  %s\n' "$name"
    PASS=$((PASS + 1))
  else
    printf '  \033[31mFAIL\033[0m  %s\n' "$name"
    FAIL=$((FAIL + 1))
    FAILED+=("$name")
  fi
}

ff() { ffmpeg -hide_banner -loglevel error -y "$@"; }

# probe FILE FIELD EXPECTED: one ffprobe field of the first video stream must match.
probe() {
  local got
  got="$(ffprobe -v error -select_streams v:0 -show_entries "stream=$2" -of csv=p=0 "$1" | sed 's/,*$//')"
  [ "$got" = "$3" ] || { echo "$1: $2 is '$got', expected '$3'"; return 1; }
}

has_audio() { [ -n "$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$1")" ]; }

# duration_near FILE SECONDS: container duration within 0.1 s.
duration_near() {
  local d
  d="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$1")"
  awk -v d="$d" -v t="$2" 'BEGIN { exit !(d > t - 0.1 && d < t + 0.1) }' || { echo "$1: duration $d, expected $2"; return 1; }
}

echo
echo "Toolchain"
run "node $(node -v)" node -e 'process.exit(+process.versions.node.split(".")[0] >= 22 ? 0 : 1)'
run "$(ffmpeg -version | head -1 | cut -d' ' -f1-3)" ffmpeg -version
run "ffprobe" ffprobe -version
run "hyperframes $(hyperframes --version 2>/dev/null)" hyperframes --version
run "remotion $(cd "$ROOT/remotion" && node -p 'require("remotion/package.json").version' 2>/dev/null)" bash -c "cd '$ROOT/remotion' && npx remotion versions"

echo
echo "FFmpeg encoders"
SRC="$OUT/src.mkv"
run "generate test source (1080p30 + stereo tone)" \
  ff -f lavfi -i testsrc2=size=1920x1080:rate=30:duration=3 -f lavfi -i sine=frequency=440:duration=3:sample_rate=48000 \
  -ac 2 -c:v ffv1 -c:a pcm_s16le "$SRC"
run "H.264 + AAC (mp4)" bash -c "$(declare -f ff probe); ff -i '$SRC' -c:v libx264 -preset fast -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart '$OUT/h264.mp4' && probe '$OUT/h264.mp4' codec_name h264"
run "H.265 / HEVC (mp4)" bash -c "$(declare -f ff probe); ff -i '$SRC' -c:v libx265 -preset fast -crf 22 -tag:v hvc1 -x265-params log-level=error -c:a aac '$OUT/hevc.mp4' && probe '$OUT/hevc.mp4' codec_name hevc"
run "VP9 + Opus (webm)" bash -c "$(declare -f ff probe); ff -i '$SRC' -c:v libvpx-vp9 -b:v 0 -crf 32 -deadline realtime -cpu-used 8 -c:a libopus '$OUT/vp9.webm' && probe '$OUT/vp9.webm' codec_name vp9"
run "AV1 SVT (mp4)" bash -c "$(declare -f ff probe); ff -i '$SRC' -c:v libsvtav1 -preset 10 -crf 35 -c:a aac '$OUT/av1.mp4' && probe '$OUT/av1.mp4' codec_name av1"
run "ProRes 422 HQ (mov)" bash -c "$(declare -f ff probe); ff -i '$SRC' -c:v prores_ks -profile:v 3 -c:a pcm_s16le '$OUT/prores.mov' && probe '$OUT/prores.mov' codec_name prores"
run "ProRes 4444 with alpha (mov)" bash -c "$(declare -f ff probe); ff -f lavfi -i 'color=c=red@0.5:s=640x360:d=1,format=yuva444p10le' -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le '$OUT/alpha.mov' && probe '$OUT/alpha.mov' pix_fmt yuva444p12le"
run "MP3 audio" bash -c "$(declare -f ff); ff -i '$SRC' -vn -c:a libmp3lame -q:a 2 '$OUT/audio.mp3'"
run "Animated GIF (palette)" bash -c "$(declare -f ff); ff -i '$SRC' -vf 'fps=15,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse' '$OUT/clip.gif'"

echo
echo "FFmpeg editing"
H264="$OUT/h264.mp4"
run "trim and concat (2 x 1 s = 2 s)" bash -c "$(declare -f ff duration_near); ff -i '$H264' -filter_complex \
  '[0:v]trim=0:1,setpts=PTS-STARTPTS[v0];[0:a]atrim=0:1,asetpts=PTS-STARTPTS[a0];[0:v]trim=2:3,setpts=PTS-STARTPTS[v1];[0:a]atrim=2:3,asetpts=PTS-STARTPTS[a1];[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]' \
  -map '[v]' -map '[a]' -c:v libx264 -c:a aac '$OUT/concat.mp4' && duration_near '$OUT/concat.mp4' 2"
run "crossfade transition (xfade + acrossfade)" bash -c "$(declare -f ff duration_near); ff -i '$H264' -i '$H264' -filter_complex \
  '[0:v][1:v]xfade=transition=fade:duration=1:offset=2[v];[0:a][1:a]acrossfade=d=1[a]' -map '[v]' -map '[a]' -c:v libx264 -c:a aac '$OUT/xfade.mp4' && duration_near '$OUT/xfade.mp4' 5"
run "reframe 16:9 to 9:16 (crop + scale)" bash -c "$(declare -f ff probe); ff -i '$H264' -vf 'crop=ih*9/16:ih,scale=1080:1920' -c:v libx264 -c:a copy '$OUT/vertical.mp4' && probe '$OUT/vertical.mp4' width,height '1080,1920'"
run "text overlay (drawtext + fontconfig)" bash -c "$(declare -f ff); ff -i '$H264' -vf \"drawtext=font=DejaVu Sans:text='Lower third':fontcolor=white:fontsize=64:box=1:boxcolor=black@0.6:boxborderw=20:x=80:y=h-180\" -c:v libx264 -c:a copy '$OUT/drawtext.mp4'"
printf '1\n00:00:00,000 --> 00:00:02,500\nBurned-in subtitle\n' >"$OUT/subs.srt"
run "burn-in subtitles (libass)" bash -c "$(declare -f ff); ff -i '$H264' -vf 'subtitles=$OUT/subs.srt' -c:v libx264 -c:a copy '$OUT/subtitled.mp4'"
run "picture-in-picture overlay" bash -c "$(declare -f ff); ff -i '$H264' -i '$H264' -filter_complex '[1:v]scale=480:-1[pip];[0:v][pip]overlay=W-w-40:H-h-40' -c:v libx264 -c:a copy '$OUT/pip.mp4'"
run "speed ramp 2x (setpts + atempo)" bash -c "$(declare -f ff duration_near); ff -i '$H264' -filter_complex '[0:v]setpts=0.5*PTS[v];[0:a]atempo=2[a]' -map '[v]' -map '[a]' -c:v libx264 -c:a aac '$OUT/fast.mp4' && duration_near '$OUT/fast.mp4' 1.5"
run "music + voice mix with ducking (sidechaincompress)" bash -c "$(declare -f ff); ff -f lavfi -i 'sine=f=220:d=3' -f lavfi -i 'sine=f=880:d=3' -filter_complex \
  '[1:a]asplit[sc][vo];[0:a][sc]sidechaincompress=threshold=0.05:ratio=8[duck];[duck][vo]amix=inputs=2:normalize=0[a]' -map '[a]' -c:a aac '$OUT/mix.m4a'"
run "loudness normalise to -14 LUFS (loudnorm)" bash -c "$(declare -f ff); ff -i '$H264' -af loudnorm=I=-14:TP=-1:LRA=11 -c:v copy -c:a aac '$OUT/loudnorm.mp4'"
run "colour grade (eq + curves + vignette)" bash -c "$(declare -f ff); ff -i '$H264' -vf 'eq=contrast=1.1:saturation=1.2,curves=preset=medium_contrast,vignette' -c:v libx264 -c:a copy '$OUT/graded.mp4'"
run "video stabilisation (vidstab)" bash -c "$(declare -f ff); cd '$OUT' && ff -i '$H264' -vf vidstabdetect=result=transforms.trf -f null - && ff -i '$H264' -vf vidstabtransform=input=transforms.trf -c:v libx264 -c:a copy '$OUT/stabilised.mp4'"
run "thumbnail + contact sheet" bash -c "$(declare -f ff); ff -ss 1 -i '$H264' -frames:v 1 '$OUT/thumb.jpg' && ff -i '$H264' -vf 'fps=2,scale=480:-1,tile=3x2' -frames:v 1 '$OUT/contact.png'"

echo
echo "HyperFrames (HTML + GSAP)"
HF="$ROOT/hyperframes"
run "hyperframes check (lint, runtime, layout, contrast)" bash -c "cd '$HF' && hyperframes check --json > '$OUT/hf-check.json'; node -e 'const t=require(\"fs\").readFileSync(\"$OUT/hf-check.json\",\"utf8\"); process.exit(JSON.parse(t.slice(t.indexOf(\"{\"))).ok ? 0 : 1)'"
run "hyperframes render to MP4" bash -c "cd '$HF' && hyperframes render -o '$OUT/hyperframes.mp4' --quiet"
run "  1920x1080, 30 fps, 8 s, with audio" bash -c "$(declare -f probe duration_near has_audio); probe '$OUT/hyperframes.mp4' width,height,r_frame_rate '1920,1080,30/1' && duration_near '$OUT/hyperframes.mp4' 8 && has_audio '$OUT/hyperframes.mp4'"
run "hyperframes render to transparent WebM" bash -c "cd '$HF' && hyperframes render --format webm -q draft -o '$OUT/hyperframes.webm' --quiet"
run "hyperframes snapshot PNG" bash -c "cd '$HF' && hyperframes snapshot --at 2 --json > '$OUT/hf-snapshot.json'"

echo
echo "Remotion (React)"
RM="$ROOT/remotion"
run "TypeScript typecheck" bash -c "cd '$RM' && npx tsc --noEmit"
run "remotion render Demo (16:9)" bash -c "cd '$RM' && npx remotion render Demo '$OUT/remotion.mp4' --log=error"
run "  1920x1080, 30 fps, 7.33 s, with audio" bash -c "$(declare -f probe duration_near has_audio); probe '$OUT/remotion.mp4' width,height,r_frame_rate '1920,1080,30/1' && duration_near '$OUT/remotion.mp4' 7.33 && has_audio '$OUT/remotion.mp4'"
run "remotion render DemoVertical (9:16)" bash -c "cd '$RM' && npx remotion render DemoVertical '$OUT/remotion-vertical.mp4' --log=error && $(declare -f probe); probe '$OUT/remotion-vertical.mp4' width,height '1080,1920'"
run "remotion render ProRes" bash -c "cd '$RM' && npx remotion render Demo '$OUT/remotion-prores.mov' --codec=prores --prores-profile=hq --frames=0-29 --log=error"
run "remotion still PNG" bash -c "cd '$RM' && npx remotion still Demo '$OUT/remotion-still.png' --frame=60 --log=error"

echo
echo "Result: $PASS passed, $FAIL failed. Outputs and log in $OUT"
if [ "$FAIL" -gt 0 ]; then
  printf '  failed: %s\n' "${FAILED[@]}"
  exit 1
fi
