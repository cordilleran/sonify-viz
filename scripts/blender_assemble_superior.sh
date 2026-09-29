#!/usr/bin/env bash
# Assemble the Blender frames of Superior Ice Year (blender_superior_ice.py --fpd N) into:
#   webp/     one WebP per day (the day's first frame), 1600 px: the site's image sequence, cross-faded by the page
#   preview   a synced MP4 with the v1.0 audio, frames cross-blended to 24 fps, the last day held through the coda (for review, not the site)
# Usage: blender_assemble_superior.sh TAG FPD [AUDIO]
#   frames are read from $SONIFICATION_HEAVY/icecover/blender/frames_TAG/ (default: the repo's rendered/)
#   AUDIO defaults to superior-ice/icecover_sup2526__v1.mp3 (3 s per day)
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
TAG=${1:?tag}; FPD=${2:?frames per day}
AUDIO=${3:-$HERE/superior-ice/icecover_sup2526__v1.mp3}
BL=${SONIFICATION_HEAVY:-$HERE/rendered}/icecover/blender
F="$BL/frames_$TAG"
DAY_S=3
mkdir -p "$BL/webp_$TAG"
n=$(ls "$F"/frame_*.png | wc -l)
for ((k = 0; k < n; k += FPD)); do
  d=$((k / FPD))
  ffmpeg -loglevel error -y -i "$F/frame_$(printf %05d $k).png" -vf scale=1600:-2 -c:v libwebp -quality 80 "$BL/webp_$TAG/day_$(printf %03d $d).webp"
done
ffmpeg -y -loglevel error -framerate "$FPD/$DAY_S" -i "$F/frame_%05d.png" -i "$AUDIO" \
  -vf "minterpolate=fps=24:mi_mode=blend,scale=1920:-2,tpad=stop_mode=clone:stop_duration=30,format=yuv420p" -c:v libx264 -crf 20 -c:a aac -b:a 192k -shortest \
  "$BL/superior_ice_${TAG}_preview.mp4"
du -sh "$BL/webp_$TAG"; ls -la "$BL/superior_ice_${TAG}_preview.mp4"
