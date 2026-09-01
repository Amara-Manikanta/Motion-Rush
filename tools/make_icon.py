"""Generate the app icon from the game's own palette."""
import os
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
import numpy as np
import pygame; pygame.init(); pygame.display.set_mode((64,64), pygame.HIDDEN)
import config as C

T = C.theme(); S = 1024
scene = pygame.Surface((S,S))
scene.fill((7,4,24))

hy, gy = S*0.42, S*1.06          # horizon and near-ground screen rows
half_far, half_near = S*0.055, S*0.86

# --- soft bloom on the vanishing point (per-pixel falloff, not stacked ellipses)
yy, xx = np.mgrid[0:S, 0:S]
dx = (xx - S*0.5) / (S*0.60)
dy = (yy - hy) / (S*0.20)
inten = np.clip(1.0 - np.sqrt(dx*dx + dy*dy), 0, 1) ** 2.2
bloom = np.zeros((S,S,3), dtype=np.uint8)
for ch in range(3):
    bloom[:,:,ch] = (inten.T * T["horizon_glow"][ch]).astype(np.uint8)
scene.blit(pygame.surfarray.make_surface(bloom),(0,0), special_flags=pygame.BLEND_RGB_ADD)

def edge(t):                      # track half-width at depth t (0=far,1=near)
    return half_far + (half_near-half_far) * (t**2.0)
def row(t):
    return hy + (gy-hy) * (t**2.0)

# --- ground bands
for i in range(10):
    t0, t1 = i/10, (i+1)/10
    y0, y1, w0, w1 = row(t0), row(t1), edge(t0), edge(t1)
    col = T["rung"] if i % 2 == 0 else T["rung_alt"]
    pygame.draw.polygon(scene, col, [(S*0.5-w0,y0),(S*0.5+w0,y0),
                                     (S*0.5+w1,y1),(S*0.5-w1,y1)])

# --- lane lines
for frac, w in ((-1.0,16),(-1/3.,9),(1/3.,9),(1.0,16)):
    pts = [(S*0.5 + frac*edge(t/24), row(t/24)) for t in range(25)]
    pygame.draw.lines(scene, T["lane_line"], False, pts, w)

# --- runner, kept small and low so it still reads at 32px
cx, base = S*0.5, S*0.90
def box(x,y,w,h,col,r=0.2):
    pygame.draw.rect(scene,col,(x-w/2,y-h,w,h),border_radius=int(w*r))
box(cx-46, base, 40, 104, T["player_dark"]); box(cx+46, base, 40, 104, T["player_dark"])
box(cx-118, base-118, 34, 128, T["player_dark"]); box(cx+118, base-118, 34, 128, T["player_dark"])
box(cx, base-96, 176, 196, T["player"])
pygame.draw.rect(scene, T["accent"], (cx-38, base-206, 76, 28), border_radius=13)
box(cx, base-312, 112, 100, T["player"])
pygame.draw.rect(scene, T["accent"], (cx-40, base-288, 80, 26), border_radius=12)

# --- clip everything to a rounded panel, then add the rim
mask = pygame.Surface((S,S), pygame.SRCALPHA)
pygame.draw.rect(mask, (255,255,255,255), (0,0,S,S), border_radius=228)
icon = pygame.Surface((S,S), pygame.SRCALPHA)
icon.blit(scene,(0,0))
icon.blit(mask,(0,0), special_flags=pygame.BLEND_RGBA_MULT)
pygame.draw.rect(icon, T["accent"], (9,9,S-18,S-18), width=14, border_radius=222)

os.makedirs("/tmp/dcicon.iconset", exist_ok=True)
pygame.image.save(icon, "/tmp/dc_icon_1024.png")
for sz in (16,32,64,128,256,512):
    pygame.image.save(pygame.transform.smoothscale(icon,(sz,sz)), f"/tmp/dcicon.iconset/icon_{sz}x{sz}.png")
    pygame.image.save(pygame.transform.smoothscale(icon,(sz*2,sz*2)), f"/tmp/dcicon.iconset/icon_{sz}x{sz}@2x.png")
pygame.image.save(icon, "/tmp/dcicon.iconset/icon_512x512@2x.png")
print("icon rendered")
