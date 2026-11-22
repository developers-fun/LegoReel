#!/usr/bin/env python3
import argparse, glob, json, math, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
MAX_EDGE=1568; MAX_PIXELS=1_150_000; LABEL_H,BAR_H,GAP=16,6,3
def est_tokens(w,h):
    s=min(1.0,MAX_EDGE/max(w,h),math.sqrt(MAX_PIXELS/(w*h))); return int(round(w*s)*round(h*s)/750)
def font(size=12):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
        if os.path.exists(p): return ImageFont.truetype(p,size)
    return ImageFont.load_default()
def probe(v):
    out=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-count_packets","-show_entries","stream=width,height,r_frame_rate,nb_read_packets","-of","json",v],capture_output=True,text=True,check=True).stdout
    s=json.loads(out)["streams"][0]; n,d=s["r_frame_rate"].split("/")
    return int(s["width"]),int(s["height"]),float(n)/float(d),int(s.get("nb_read_packets") or 0)
def video_frames(a):
    W,H,fps,nf=probe(a.video)
    start=a.start or 0.0; end=a.end if a.end is not None else (nf/fps if nf else start+10)
    f0=int(round(start*fps)); f1=int(round(end*fps))
    if nf: f1=min(f1,nf-1)
    s=min(1.0,a.tile_h/H); ow,oh=max(2,int(W*s)//2*2),max(2,int(H*s)//2*2)
    vf=f"select='between(n\\,{f0}\\,{f1})*not(mod(n-{f0}\\,{a.step}))',scale={ow}:{oh}:flags=area"
    raw=subprocess.run(["ffmpeg","-v","error","-i",a.video,"-vf",vf,"-vsync","0","-f","rawvideo","-pix_fmt","rgb24","-"],capture_output=True,check=True).stdout
    n=len(raw)//(ow*oh*3); arr=np.frombuffer(raw[:n*ow*oh*3],np.uint8).reshape(n,oh,ow,3)
    return [{"img":Image.fromarray(arr[i]),"frame":f0+i*a.step,"t":(f0+i*a.step)/fps} for i in range(n)],fps
def score(items):
    prev=None
    for it in items:
        g=np.asarray(it["img"].convert("L").resize((64,int(64*it["img"].height/it["img"].width))),np.float32)
        it["chg"]=0.0 if prev is None else float(np.mean(np.abs(g-prev))); prev=g
    top=max([i["chg"] for i in items]+[1e-6])
    for it in items: it["bar"]=it["chg"]/top; it["cut"]=it["chg"]>18
def sheets(items,a):
    n=len(items); aspect=items[0]["img"].height/items[0]["img"].width
    cols=a.cols; per=a.per; ns=math.ceil(n/per); f=font(10); outs=[]
    for s in range(ns):
        ch=items[s*per:(s+1)*per]; r=math.ceil(len(ch)/cols)
        tw=int((MAX_EDGE-GAP*(cols+1))/cols); tw=min(tw,items[0]["img"].width); th=int(tw*aspect)
        while True:
            sw=cols*tw+GAP*(cols+1); sh=r*(th+LABEL_H+BAR_H)+GAP*(r+1)
            if sw*sh<=MAX_PIXELS and sh<=MAX_EDGE: break
            tw-=4; th=int(tw*aspect)
        sheet=Image.new("RGB",(sw,sh),(18,18,18)); d=ImageDraw.Draw(sheet)
        for i,it in enumerate(ch):
            x=GAP+(i%cols)*(tw+GAP); y=GAP+(i//cols)*(th+LABEL_H+BAR_H+GAP)
            sheet.paste(it["img"].resize((tw,th)),(x,y+LABEL_H))
            d.text((x+2,y+2),f"{it['t']:.2f}s",fill=(255,255,255),font=f)
            by=y+LABEL_H+th; d.rectangle([x,by,x+tw-1,by+BAR_H-1],fill=(45,45,45))
            d.rectangle([x,by,x+max(1,int((tw-1)*it["bar"])),by+BAR_H-1],fill=(235,40,40) if it["cut"] else (40,200,90))
        p=f"{a.out}_{s+1:02d}.jpg"; os.makedirs(os.path.dirname(p) or ".",exist_ok=True)
        sheet.save(p,"JPEG",quality=80); outs.append((p,sheet.size,len(ch)))
    return outs
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("video"); p.add_argument("--start",type=float); p.add_argument("--end",type=float)
    p.add_argument("--step",type=int,default=6); p.add_argument("--cols",type=int,default=6); p.add_argument("--per",type=int,default=30)
    p.add_argument("--tile-h",type=int,default=220); p.add_argument("--out",default="grid")
    a=p.parse_args(); items,fps=video_frames(a); score(items); outs=sheets(items,a)
    print(f"{len(items)} frames fps={fps:.2f} -> {len(outs)} sheets")
    for pth,sz,k in outs: print(" ",pth,sz,k,"frames ~",est_tokens(*sz),"tokens")
    cuts=[f"{i['t']:.2f}" for i in items if i['cut']]; print("hard-change times:",cuts)
