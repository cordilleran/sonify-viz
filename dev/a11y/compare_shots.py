"""Pixel-compare two screenshot folders made by shots.js. Prints the share of differing pixels per image."""
import sys,os,numpy as np
from PIL import Image
a,b=sys.argv[1:3];bad=0
for f in sorted(os.listdir(a)):
    x=np.asarray(Image.open(os.path.join(a,f)).convert('RGB')).astype(int);y=np.asarray(Image.open(os.path.join(b,f)).convert('RGB')).astype(int)
    if x.shape!=y.shape:print(f'{f}: SIZE differs {x.shape} vs {y.shape}');bad+=1;continue
    d=(np.abs(x-y).sum(axis=2)>0);n=d.sum();print(f'{f}: {n} px differ ({100*n/d.size:.4f}%)');bad+=n>0
print('IDENTICAL' if not bad else f'{bad} image(s) differ')
