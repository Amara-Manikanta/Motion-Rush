import os, random
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
os.environ.setdefault("SDL_VIDEODRIVER","dummy"); os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import pygame; pygame.init(); pygame.display.set_mode((1280,720), pygame.HIDDEN)
import config as C
from game.game_manager import GameManager, State
from game.obstacle import ObstacleKind as K
from input.keyboard_input import KeyboardInput
from tests.autopilot import choose_action

class S:
    enabled=False; sounds={}
    def play(self,n): pass
    def close(self): pass

OUT="/tmp/dcshots"; os.makedirs(OUT, exist_ok=True)
DT=1/60
canvas = pygame.Surface((1280,720))
gm = GameManager(canvas, KeyboardInput(), S()); gm._save_best=lambda:None
gm.best_score = 4820.0

# 1. menu
gm.menu.t = 0.4; gm.draw(); pygame.image.save(canvas, f"{OUT}/1_menu.png")

# 2. mid-run, autopilot for a while
gm.spawner.rng = random.Random(2); gm.start_run()
for i in range(int(26/DT)):
    gm.handle_action(choose_action(gm)); gm.update(DT)
    if gm.state is State.GAME_OVER: break
gm.draw(); pygame.image.save(canvas, f"{OUT}/2_running.png")

# 3. a curated frame showing every obstacle type at once
gm2 = GameManager(pygame.Surface((1280,720)), KeyboardInput(), S()); gm2._save_best=lambda:None
gm2.start_run()
for o in gm2.spawner.obstacles: o.active=False
for o in gm2.spawner.orbs: o.active=False
specs=[(K.ENERGY_BARRIER,-1,16),(K.LASER_BEAM,0,15),(K.FORCE_FIELD,1,15),
       (K.HOVER_DRONE,0,42),(K.ENERGY_BARRIER,1,64),(K.LASER_BEAM,-1,64)]
for i,(k,l,z) in enumerate(specs): gm2.spawner.obstacles[i].spawn(k,l,z)
for i in range(6): gm2.spawner.orbs[i].spawn(-1, 26+i*C.ORB_SPACING)
for i in range(4): gm2.spawner.orbs[6+i].spawn(1, 30+i*C.ORB_SPACING)
gm2.run.score=3417; gm2.run.orbs=88; gm2.run.distance=1290; gm2.run.speed=24.5
gm2.player.lane=0; gm2.player.lane_visual=0.0
for _ in range(20): gm2.player.update(DT, 24.5)
gm2.draw(); pygame.image.save(gm2.screen, f"{OUT}/3_obstacles.png")

# 4. jumping + ducking poses
gm2.player.jump()
for _ in range(16): gm2.player.update(DT,24.5)
gm2.draw(); pygame.image.save(gm2.screen, f"{OUT}/4_jump.png")
gm2.player.reset(); gm2.player.duck()
for _ in range(3): gm2.player.update(DT,24.5)
gm2.draw(); pygame.image.save(gm2.screen, f"{OUT}/5_duck.png")

# 5. game over
gm.state=State.GAME_OVER; gm.death_timer=0.0; gm.is_best=True
gm.run.score=5231; gm.run.orbs=142; gm.run.distance=2104; gm.run.speed=28.4
gm.menu.t=0.4; gm.draw(); pygame.image.save(canvas, f"{OUT}/6_gameover.png")
print("saved:", sorted(os.listdir(OUT)))
