from PIL import Image, ImageDraw
import sys
def gsheet(box, frames, name, sc=1.8, step=20, cols=4, src='A_all/f{:03d}.png'):
    w=int((box[2]-box[0])*sc); h=int((box[3]-box[1])*sc)
    rows=(len(frames)+cols-1)//cols
    W=Image.new('RGB',(w*cols,h*rows))
    for i,n in enumerate(frames):
        im=Image.open(src.format(n)).convert('RGB').crop(box).resize((w,h),Image.LANCZOS)
        d=ImageDraw.Draw(im)
        for gx in range((box[0]//step+1)*step, box[2], step):
            x=(gx-box[0])*sc; d.line([(x,0),(x,h)],fill=(0,0,255) if gx%100==0 else (120,160,255),width=1)
            if gx%100==0 or gx%step==0 and (gx//step)%2==0: d.text((x+2,2),str(gx),fill=(0,0,200))
        for gy in range((box[1]//step+1)*step, box[3], step):
            y=(gy-box[1])*sc; d.line([(0,y),(w,y)],fill=(0,0,255) if gy%100==0 else (120,160,255),width=1)
            if (gy//step)%2==0: d.text((2,y+1),str(gy),fill=(0,0,200))
        d.text((w-50,h-14),f"f{n}",fill='red')
        W.paste(im,((i%cols)*w,(i//cols)*h))
    W.save(name)
if __name__=='__main__':
    pass
