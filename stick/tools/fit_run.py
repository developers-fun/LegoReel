import sys, json, time, math
import numpy as np
from PIL import Image
from stickreel.rotofit import *

def load(n):
    return np.array(Image.open(f'A_all/f{n:03d}.png').convert('RGB'))

def init_params(hip,a,hd,hands,feet):
    return np.array([hip[0],hip[1],a,hd,*hands[0],*hands[1],*feet[0],*feet[1]],float)

PY = init_params((214,786),0.19,-0.41,[(252,689),(246,700)],[(224,864),(182,862)])
PF = PY + np.array([-90,-290,0,0,-90,-290,-90,-290,-90,-290,-90,-290],float)

def care_mask(shape):
    c=np.ones(shape,np.uint8)
    c[466:548,8:184]=0        # tiktok watermark (left)
    c[690:800,478:576]=0      # watermark (right) and token glow
    c[0:300,:]=0              # sky/text
    return c

if __name__=='__main__':
    f0,f1=int(sys.argv[1]),int(sys.argv[2]); out=sys.argv[3]
    fit=Fitter()
    res={}
    pf,py=PF.copy(),PY.copy(); bf,by=(1,1,-1,-1),(1,1,-1,-1)
    if len(sys.argv)>4:
        d=json.load(open(sys.argv[4])); k=str(f0-1)
        if k in d: pf,py=np.array(d[k]['f']),np.array(d[k]['y']); bf,by=tuple(d[k]['bf']),tuple(d[k]['by'])
    t=time.time(); prevLf=prevLy=0.55
    for n in range(f0,f1+1):
        ref=white_mask(load(n)); care=care_mask(ref.shape)
        ymask=draw_mask(build(py,by),(0,0,ref.shape[1],ref.shape[0]),ref.shape)[0]
        pf2,bf2,Lf=fit.fit(ref,pf,bf,care=care,other=ymask,prior=pf,trigger=prevLf+0.12,restarts=4,seed=n)
        fmask=draw_mask(build(pf2,bf2),(0,0,ref.shape[1],ref.shape[0]),ref.shape)[0]
        py2,by2,Ly=fit.fit(ref,py,by,care=care,other=fmask,prior=py,trigger=prevLy+0.12,restarts=4,seed=n+1000)
        pf,bf,py,by=pf2,bf2,py2,by2; prevLf,prevLy=0.6*prevLf+0.4*Lf,0.6*prevLy+0.4*Ly
        res[str(n)]=dict(f=pf.tolist(),y=py.tolist(),bf=list(bf),by=list(by),Lf=Lf,Ly=Ly)
        if n%5==0: print(n,round(Lf,3),round(Ly,3),round(time.time()-t,1),flush=True)
    json.dump(res,open(out,'w'))
