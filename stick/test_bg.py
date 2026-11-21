import time
from PIL import Image
from stickreel.engine import *
from stickreel.dig_bg import *
from stickreel.figure import *
t=time.time()
cam=Cam()
img=new_canvas()
draw_background(img,cam); draw_hook(img,cam)
UP=dict(head=(221,711),neck=(225,729),hip=(214,786),hands=[(252,689),(246,700)],feet=[(224,864),(182,862)],eb=[1,1],kb=[-1,-1],pick=-48,pick_len=64)
draw_figure(img,UP,cam)
F=shift(UP,-90,-290); draw_figure(img,F,cam)
draw_label(img,'FRIEND',(132,386),cam); draw_label(img,'YOU',(220,678),cam)
print('render',time.time()-t)
out=img.convert('RGB').resize((576,1024),Image.LANCZOS)
ref=Image.open('A_all/f001.png').convert('RGB')
W=Image.new('RGB',(576*3,1024)); W.paste(ref,(0,0)); W.paste(out,(576,0)); W.paste(Image.blend(ref,out,0.5),(1152,0)); W.save('cmp1.png')
