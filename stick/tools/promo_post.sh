#!/bin/bash
# usage: promo_post.sh RAW OUT DURATION [blur_start_frame blur_end_frame]
# Adds a blurred time-lapse look on a frame window (ramped gblur + tmix, done on trimmed segments) and softens the audio edges.
RAW=$1; OUT=$2; DUR=$3; F0=$4; F1=$5
AF="afade=t=in:st=0:d=0.4,afade=t=out:st=$(python3 -c "print(max(0,$DUR-0.6))"):d=0.6,lowpass=f=7000"
if [ -n "$F0" ]; then
  R=4
  FC="[0:v]split=5[a][b][c][d][e];
[a]trim=end_frame=$((F0-R)),setpts=PTS-STARTPTS[v1];
[b]trim=start_frame=$((F0-R)):end_frame=$F0,setpts=PTS-STARTPTS,gblur=sigma=3[v2];
[c]trim=start_frame=$F0:end_frame=$F1,setpts=PTS-STARTPTS,gblur=sigma=8,tmix=frames=5[v3];
[d]trim=start_frame=$F1:end_frame=$((F1+R)),setpts=PTS-STARTPTS,gblur=sigma=3[v4];
[e]trim=start_frame=$((F1+R)),setpts=PTS-STARTPTS[v5];
[v1][v2][v3][v4][v5]concat=n=5:v=1:a=0,format=yuv420p[v]"
  ffmpeg -y -loglevel error -i "$RAW" -filter_complex "$FC" -map "[v]" -map 0:a -af "$AF" -c:v libx264 -preset veryfast -crf 18 -c:a aac -b:a 160k "$OUT"
else
  ffmpeg -y -loglevel error -i "$RAW" -c:v copy -af "$AF" -c:a aac -b:a 160k "$OUT"
fi
