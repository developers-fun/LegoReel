import sys, json
import numpy as np, cv2
from PIL import Image, ImageDraw
from stickreel.rotofit import *
def viz(fitjson, frames, out, box_y=(0,330,420,900), sc=0.9, cols=4):
    d=json.load(open(fitjson))
    tiles=[]
    for n in frames:
        im=np.array(Image.open(f'A_all/f{n:03d}.png').convert('RGB'))
        ref=white_mask(im)
        o=im.copy()
        o[ref>0]=(0.5*o[ref>0]+0.5*np.array([255,0,255])).astype(np.uint8)
        r=d[str(n)]
        for key,bk,col in (('f','bf',(0,200,0)),('y','by',(0,120,255))):
            pose=build(np.array(r[key]),tuple(r[bk]))
            ls,_=limbs(pose)
            for pts,w in ls:
                P=[(int(x),int(y)) for x,y in pts]
                cv2.polylines(o,[np.array(P)],False,col,2)
            c=pose['head']; cv2.circle(o,(int(c[0]),int(c[1])),int(HEAD_R),col,2)
        x0,y0,x1,y1=box_y
        t=Image.fromarray(o[y0:y1,x0:x1]).resize((int((x1-x0)*sc),int((y1-y0)*sc)))
        ImageDraw.Draw(t).text((4,4),f"f{n} Lf{r['Lf']:.2f} Ly{r['Ly']:.2f}",fill=(255,255,255))
        tiles.append(t)
    w,h=tiles[0].size; rows=(len(tiles)+cols-1)//cols
    W=Image.new('RGB',(w*cols,h*rows))
    for i,t in enumerate(tiles): W.paste(t,((i%cols)*w,(i//cols)*h))
    W.save(out)
if __name__=='__main__':
    viz(sys.argv[1],[int(x) for x in sys.argv[3].split(',')],sys.argv[2])
