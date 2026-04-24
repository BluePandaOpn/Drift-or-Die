import math
import random
import sys

import pygame

# --- CONFIGURACION CONSTANTE ---
WIDTH, HEIGHT = 1200, 800
FPS = 60

# Colores
COLOR_BG = (240, 240, 240)
COLOR_GRID = (220, 220, 220)
COLOR_CAR = (30, 30, 200)
COLOR_AI = (220, 40, 40)
COLOR_AI_BUFF = (255, 100, 0)
COLOR_UI = (20, 20, 20)
COLOR_NITRO = (0, 191, 255)
COLOR_COLLECTIBLE = (255, 215, 0)
COLOR_HEALTH = (50, 200, 50)

GRID_SIZE = 200
PARTICLE_CULL_MARGIN = 30
CAR_CULL_MARGIN = 120
UPGRADE_CULL_MARGIN = 40
SKID_CULL_MARGIN = 30
SKID_LIFE = 220
UPGRADE_TARGET_COUNT = 24
UPGRADE_KEEP_RADIUS = 1500
UPGRADE_SPAWN_RADIUS_MIN = 450
UPGRADE_SPAWN_RADIUS_MAX = 1250
AI_SPAWN_RADIUS_MIN = 350
AI_SPAWN_RADIUS_MAX = 900


def world_to_screen(x, y, cam_x, cam_y):
    return x - cam_x + WIDTH / 2, y - cam_y + HEIGHT / 2


def is_visible(screen_x, screen_y, margin=0):
    return -margin <= screen_x <= WIDTH + margin and -margin <= screen_y <= HEIGHT + margin


def random_point_around(origin_x, origin_y, min_radius, max_radius, bias_x=0.0, bias_y=0.0):
    bias_len = math.hypot(bias_x, bias_y)
    if bias_len > 0.001:
        base_angle = math.atan2(bias_y, bias_x)
        angle = base_angle + random.uniform(-math.pi / 2.8, math.pi / 2.8)
    else:
        angle = random.uniform(0, math.tau)
    radius = random.uniform(min_radius, max_radius)
    return (
        origin_x + math.cos(angle) * radius,
        origin_y + math.sin(angle) * radius,
    )


def draw_infinite_grid(surface, cam_x, cam_y, grid_size=GRID_SIZE):
    start_x = -(cam_x % grid_size)
    start_y = -(cam_y % grid_size)

    for x in range(int(start_x), WIDTH + grid_size, grid_size):
        pygame.draw.line(surface, COLOR_GRID, (x, 0), (x, HEIGHT))
    for y in range(int(start_y), HEIGHT + grid_size, grid_size):
        pygame.draw.line(surface, COLOR_GRID, (0, y), (WIDTH, y))


class Particle:
    def __init__(self, x, y, color=(200, 200, 200), life=255, size=None):
        self.x = float(x)
        self.y = float(y)
        self.size = size if size else random.randint(3, 6)
        self.life = life
        self.vel_x = random.uniform(-0.8, 0.8)
        self.vel_y = random.uniform(-0.8, 0.8)
        self.color = color

    def update(self):
        self.x += self.vel_x
        self.y += self.vel_y
        self.life -= 7
        return self.life > 0


class SkidMark:
    def __init__(self, x, y, angle, life=SKID_LIFE, alpha=110):
        self.x = float(x)
        self.y = float(y)
        self.angle = float(angle)
        self.life = life
        self.alpha = alpha

    def update(self):
        self.life -= 1
        return self.life > 0

    def draw(self, surface, cam_x, cam_y):
        screen_x, screen_y = world_to_screen(self.x, self.y, cam_x, cam_y)
        if not is_visible(screen_x, screen_y, SKID_CULL_MARGIN):
            return

        fade = max(0.0, self.life / SKID_LIFE)
        skid_bit = pygame.Surface((8, 6), pygame.SRCALPHA)
        pygame.draw.rect(skid_bit, (20, 20, 20, int(self.alpha * fade)), (0, 0, 8, 6))
        skid_bit = pygame.transform.rotate(skid_bit, self.angle)
        rect = skid_bit.get_rect(center=(screen_x, screen_y))
        surface.blit(skid_bit, rect)


class Upgrade:
    label_font = None

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.type = random.choice(["speed", "drift", "nitro", "accel"])
        self.angle = 0.0
        self.color = COLOR_NITRO if self.type == "nitro" else COLOR_COLLECTIBLE

    def draw(self, surface, cam_x, cam_y):
        self.angle += 0.08
        float_y = math.sin(self.angle) * 8
        screen_x, screen_y = world_to_screen(self.x, self.y + float_y, cam_x, cam_y)
        if not is_visible(screen_x, screen_y, UPGRADE_CULL_MARGIN):
            return

        pos = (int(screen_x), int(screen_y))
        glow_size = 15 + math.sin(self.angle) * 5
        pygame.draw.circle(surface, (*self.color, 80), pos, glow_size)
        pygame.draw.circle(surface, self.color, pos, 12)

        if Upgrade.label_font is None:
            Upgrade.label_font = pygame.font.SysFont("Arial", 14, bold=True)
        label = Upgrade.label_font.render(self.type[0].upper(), True, (255, 255, 255))
        surface.blit(label, (pos[0] - 5, pos[1] - 8))


class Car:
    def __init__(self, x, y, color=COLOR_CAR, is_ai=False):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.is_ai = is_ai
        self.angle = float(random.randint(0, 360))
        self.speed = 0.0

        # Atributos base
        self.base_max_speed = 10.0 if is_ai else 14.0
        self.max_speed = self.base_max_speed
        self.acceleration = 0.22 if is_ai else 0.28
        self.friction = 0.09
        self.braking = 0.50
        self.rotation_speed = 4.0 if is_ai else 5.0
        self.drift_factor = 0.88

        # Jugador
        self.health = 100
        self.collected_types = []
        self.nitro_max = 100
        self.nitro_level = 50
        self.nitro_power = 0.6

        self.dir_x = 0.0
        self.dir_y = 0.0
        self.is_braking = False
        self.is_nitro_active = False
        self.particles = []

        # Buffs (IA)
        self.buff_timer = 0
        self.is_buffed = False

    def setup_class(self, choice):
        if choice == 0:  # DRIFT KING
            self.drift_factor = 0.95
            self.rotation_speed = 6.5
            self.color = (150, 50, 250)
        elif choice == 1:  # SPEED DEMON
            self.max_speed = 18.0
            self.acceleration = 0.35
            self.color = (50, 200, 50)
        elif choice == 2:  # NITRO JUNKIE
            self.nitro_max = 200
            self.nitro_level = 200
            self.nitro_power = 1.0
            self.color = COLOR_NITRO

    def apply_upgrade(self, upg_type):
        self.collected_types.append(upg_type)
        if upg_type == "speed":
            self.max_speed += 1.2
        elif upg_type == "accel":
            self.acceleration += 0.06
        elif upg_type == "nitro":
            self.nitro_max += 25
            self.nitro_level = self.nitro_max
        elif upg_type == "drift":
            self.drift_factor = min(0.98, self.drift_factor + 0.01)
            self.rotation_speed += 0.4

    def lose_random_upgrade(self):
        if self.collected_types:
            removed = self.collected_types.pop(random.randrange(len(self.collected_types)))
            if removed == "speed":
                self.max_speed = max(10.0, self.max_speed - 1.2)
            elif removed == "accel":
                self.acceleration = max(0.15, self.acceleration - 0.06)
            elif removed == "drift":
                self.drift_factor = max(0.85, self.drift_factor - 0.01)
                self.rotation_speed = max(3.0, self.rotation_speed - 0.4)
            return True
        return False

    def update(self, keys_or_target, skid_marks):
        input_fwd = False
        input_back = False
        input_left = False
        input_right = False
        input_handbrake = False
        input_nitro = False

        if not self.is_ai:
            input_fwd = keys_or_target[pygame.K_w]
            input_back = keys_or_target[pygame.K_s]
            input_left = keys_or_target[pygame.K_a]
            input_right = keys_or_target[pygame.K_d]
            input_handbrake = keys_or_target[pygame.K_SPACE]
            input_nitro = keys_or_target[pygame.K_LSHIFT] and self.nitro_level > 0 and input_fwd
        else:
            if self.is_buffed:
                self.buff_timer -= 1
                if self.buff_timer <= 0:
                    self.is_buffed = False
                    self.max_speed = self.base_max_speed
                    self.rotation_speed = 4.0

            dist = math.hypot(keys_or_target.x - self.x, keys_or_target.y - self.y)
            if dist < 1200:
                target_angle = math.degrees(math.atan2(-(keys_or_target.y - self.y), keys_or_target.x - self.x))
                angle_diff = (target_angle - self.angle + 180) % 360 - 180
                if angle_diff > 5:
                    input_left = True
                elif angle_diff < -5:
                    input_right = True
                input_fwd = True
                if dist < 100:
                    input_handbrake = True

        self.is_nitro_active = input_nitro
        actual_accel = self.acceleration + (self.nitro_power if self.is_nitro_active else 0)
        actual_max = self.max_speed + (8 if self.is_nitro_active else 0)

        if self.is_nitro_active:
            self.nitro_level -= 1.2
            if random.random() > 0.3:
                self.particles.append(Particle(self.x, self.y, COLOR_NITRO, size=8))

        if input_fwd:
            self.speed += actual_accel
        elif input_back:
            if self.speed > 0:
                self.speed -= self.braking
            else:
                self.speed -= self.acceleration
        else:
            if self.speed > 0:
                self.speed -= self.friction
            elif self.speed < 0:
                self.speed += self.friction
            if abs(self.speed) < self.friction:
                self.speed = 0

        self.is_braking = input_handbrake
        self.speed = max(-actual_max / 2, min(self.speed, actual_max))

        if self.speed != 0:
            rot_dir = 1 if self.speed > 0 else -1
            turn_mod = min(1.0, abs(self.speed) / 3.5)
            if input_left:
                self.angle += self.rotation_speed * rot_dir * turn_mod
            if input_right:
                self.angle -= self.rotation_speed * rot_dir * turn_mod

        target_dx = math.cos(math.radians(self.angle)) * self.speed
        target_dy = -math.sin(math.radians(self.angle)) * self.speed

        drift_smooth = 0.97 if self.is_braking else self.drift_factor
        self.dir_x = self.dir_x * drift_smooth + target_dx * (1 - drift_smooth)
        self.dir_y = self.dir_y * drift_smooth + target_dy * (1 - drift_smooth)

        drift_val = math.hypot(target_dx - self.dir_x, target_dy - self.dir_y)
        if (drift_val > 1.2 or self.is_braking) and abs(self.speed) > 3:
            self.add_skids(skid_marks, drift_val)

        self.x += self.dir_x
        self.y += self.dir_y
        self.particles = [p for p in self.particles if p.update()]

    def add_skids(self, skid_marks, drift):
        rad = math.radians(self.angle + 90)
        dist_back = 18
        offset = 12
        alpha = min(110, int(drift * 20))
        for side in (-1, 1):
            sx = self.x - math.cos(math.radians(self.angle)) * dist_back + math.cos(rad) * (offset * side)
            sy = self.y + math.sin(math.radians(self.angle)) * dist_back - math.sin(rad) * (offset * side)
            skid_marks.append(SkidMark(sx, sy, self.angle, alpha=alpha))

    def draw(self, surface, cam_x, cam_y):
        for p in self.particles:
            screen_x, screen_y = world_to_screen(p.x, p.y, cam_x, cam_y)
            if not is_visible(screen_x, screen_y, PARTICLE_CULL_MARGIN):
                continue
            pygame.draw.circle(
                surface,
                (*p.color, p.life // 2),
                (int(screen_x), int(screen_y)),
                int(p.size),
            )

        screen_x, screen_y = world_to_screen(self.x, self.y, cam_x, cam_y)
        if not is_visible(screen_x, screen_y, CAR_CULL_MARGIN):
            return

        car_w, car_h = 56, 32

        shadow_surf = pygame.Surface((car_w, car_h), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0, 0, 0, 80), (0, 0, car_w, car_h), border_radius=8)
        rotated_shadow = pygame.transform.rotate(shadow_surf, self.angle)
        shadow_rect = rotated_shadow.get_rect(center=(screen_x + 8, screen_y + 8))
        surface.blit(rotated_shadow, shadow_rect)

        car_surf = pygame.Surface((car_w, car_h), pygame.SRCALPHA)
        pygame.draw.rect(car_surf, self.color, (2, 2, car_w - 4, car_h - 4), border_radius=6)
        pygame.draw.rect(car_surf, (30, 30, 45), (16, 6, 22, car_h - 12), border_radius=4)

        rotated = pygame.transform.rotate(car_surf, self.angle)
        rect = rotated.get_rect(center=(screen_x, screen_y))
        surface.blit(rotated, rect)


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
        pygame.display.set_caption("Drift or Die")
        self.clock = pygame.time.Clock()
        self.font_gui = pygame.font.SysFont("Impact", 28)
        self.font_msg = pygame.font.SysFont("Impact", 72)
        self.font_btn = pygame.font.SysFont("Impact", 36)
        self.font_small = pygame.font.SysFont("Arial", 22)

        self.state = "MENU_MAIN"
        self.main_menu_buttons = [
            {"name": "JUGAR", "action": "play"},
            {"name": "OPCIONES", "action": "options"},
            {"name": "SALIR", "action": "exit"},
        ]
        self.menu_options = [
            {"name": "DRIFT KING", "desc": "+Giro, +Control lateral", "color": (150, 50, 250)},
            {"name": "SPEED DEMON", "desc": "+Velocidad, +Aceleracion", "color": (50, 200, 50)},
            {"name": "NITRO JUNKIE", "desc": "+Capacidad Nitro, +Empuje", "color": COLOR_NITRO},
        ]
        self.reset_game()

    def reset_game(self):
        self.player = Car(0.0, 0.0)
        self.cam_x, self.cam_y = self.player.x, self.player.y
        self.ais = [Car(*random_point_around(self.player.x, self.player.y, AI_SPAWN_RADIUS_MIN, AI_SPAWN_RADIUS_MAX), COLOR_AI, True) for _ in range(10)]
        self.upgrades = []
        self.skid_marks = []
        self.score = 0
        self.buff_event_timer = 0
        self.invul_timer = 0
        self.maintain_upgrade_density(force_full=True)

    def draw_main_menu(self):
        self.screen.fill((30, 30, 40))
        title = self.font_msg.render("DRIFT SURVIVAL", True, (255, 255, 255))
        subtitle = self.font_gui.render("Menu principal", True, (185, 185, 185))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 110))
        self.screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 200))

        mx, my = pygame.mouse.get_pos()
        for i, button in enumerate(self.main_menu_buttons):
            rect = pygame.Rect(WIDTH // 2 - 180, 290 + i * 110, 360, 78)
            is_hover = rect.collidepoint(mx, my)
            color = (80, 120, 220) if is_hover else (55, 55, 75)

            pygame.draw.rect(self.screen, color, rect, border_radius=16)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3, border_radius=16)

            label = self.font_btn.render(button["name"], True, (255, 255, 255))
            self.screen.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))

            if is_hover and pygame.mouse.get_pressed()[0]:
                if button["action"] == "play":
                    self.state = "MENU_PLAY"
                elif button["action"] == "options":
                    self.state = "OPTIONS"
                else:
                    pygame.quit()
                    sys.exit()
                pygame.time.delay(180)

    def draw_play_menu(self):
        self.screen.fill((30, 30, 40))
        title = self.font_msg.render("ELEGIR COCHE", True, (255, 255, 255))
        help_text = self.font_gui.render("Selecciona tu estilo de conduccion", True, (200, 200, 200))
        back_text = self.font_small.render("ESC para volver", True, (180, 180, 180))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 80))
        self.screen.blit(help_text, (WIDTH // 2 - help_text.get_width() // 2, 165))
        self.screen.blit(back_text, (40, 40))

        mx, my = pygame.mouse.get_pos()
        for i, opt in enumerate(self.menu_options):
            rect = pygame.Rect(WIDTH // 2 - 250, 280 + i * 130, 500, 100)
            is_hover = rect.collidepoint(mx, my)

            color = opt["color"] if is_hover else (60, 60, 80)
            pygame.draw.rect(self.screen, color, rect, border_radius=15)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3, border_radius=15)

            name = self.font_btn.render(opt["name"], True, (255, 255, 255))
            desc = self.font_gui.render(opt["desc"], True, (200, 200, 200))
            self.screen.blit(name, (rect.x + 20, rect.y + 15))
            self.screen.blit(desc, (rect.x + 20, rect.y + 60))

            if is_hover and pygame.mouse.get_pressed()[0]:
                self.reset_game()
                self.player.setup_class(i)
                self.state = "PLAYING"
                pygame.time.delay(200)

    def draw_options_menu(self):
        self.screen.fill((25, 28, 38))
        title = self.font_msg.render("OPCIONES", True, (255, 255, 255))
        line1 = self.font_gui.render("Controles: W A S D para mover, ESPACIO para derrapar.", True, (220, 220, 220))
        line2 = self.font_gui.render("SHIFT IZQ para usar nitro.", True, (220, 220, 220))
        line3 = self.font_gui.render("ESC para volver al menu principal.", True, (220, 220, 220))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 120))
        self.screen.blit(line1, (WIDTH // 2 - line1.get_width() // 2, 300))
        self.screen.blit(line2, (WIDTH // 2 - line2.get_width() // 2, 350))
        self.screen.blit(line3, (WIDTH // 2 - line3.get_width() // 2, 430))

    def spawn_upgrade(self):
        bias_x = self.player.dir_x if abs(self.player.dir_x) > 0.05 else math.cos(math.radians(self.player.angle))
        bias_y = self.player.dir_y if abs(self.player.dir_y) > 0.05 else -math.sin(math.radians(self.player.angle))
        x, y = random_point_around(
            self.player.x,
            self.player.y,
            UPGRADE_SPAWN_RADIUS_MIN,
            UPGRADE_SPAWN_RADIUS_MAX,
            bias_x,
            bias_y,
        )
        self.upgrades.append(Upgrade(x, y))

    def maintain_upgrade_density(self, force_full=False):
        if force_full:
            self.upgrades.clear()

        self.upgrades = [
            upgrade
            for upgrade in self.upgrades
            if math.hypot(upgrade.x - self.cam_x, upgrade.y - self.cam_y) <= UPGRADE_KEEP_RADIUS
        ]

        while len(self.upgrades) < UPGRADE_TARGET_COUNT:
            self.spawn_upgrade()

    def run(self):
        while True:
            self.clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state in ("MENU_PLAY", "OPTIONS"):
                            self.state = "MENU_MAIN"
                        elif self.state == "PLAYING":
                            self.state = "MENU_MAIN"
                            self.reset_game()
                    elif self.state == "GAME_OVER":
                        self.state = "MENU_MAIN"
                        self.reset_game()

            if self.state == "MENU_MAIN":
                self.draw_main_menu()
            elif self.state == "MENU_PLAY":
                self.draw_play_menu()
            elif self.state == "OPTIONS":
                self.draw_options_menu()
            elif self.state == "PLAYING":
                self.update_game()
                self.draw_game()
            elif self.state == "GAME_OVER":
                self.draw_game()
                self.draw_game_over()

            pygame.display.flip()

    def update_game(self):
        keys = pygame.key.get_pressed()

        # Evento de Furia IA
        self.buff_event_timer += 1
        if self.buff_event_timer >= 600:
            self.buff_event_timer = 0
            buffed_ai = random.choice(self.ais)
            buffed_ai.is_buffed = True
            buffed_ai.buff_timer = 300
            buffed_ai.max_speed += 7
            buffed_ai.rotation_speed += 2.5

        self.player.update(keys, self.skid_marks)
        for ai in self.ais:
            ai.update(self.player, self.skid_marks)

        self.cam_x += (self.player.x - self.cam_x) * 0.12
        self.cam_y += (self.player.y - self.cam_y) * 0.12

        self.skid_marks = [mark for mark in self.skid_marks if mark.update()]
        self.maintain_upgrade_density()

        # Colisiones Mejoras
        for u in self.upgrades[:]:
            if math.hypot(self.player.x - u.x, self.player.y - u.y) < 45:
                self.player.apply_upgrade(u.type)
                self.upgrades.remove(u)
                self.score += 500

        # Colisiones IA
        if self.invul_timer > 0:
            self.invul_timer -= 1
        else:
            for ai in self.ais:
                if math.hypot(self.player.x - ai.x, self.player.y - ai.y) < 45:
                    self.player.health -= 20
                    self.player.lose_random_upgrade()
                    self.invul_timer = 90
                    self.score = max(0, self.score - 1000)
                    if self.player.health <= 0:
                        self.state = "GAME_OVER"

    def draw_game(self):
        self.screen.fill(COLOR_BG)
        draw_infinite_grid(self.screen, self.cam_x, self.cam_y)

        for mark in self.skid_marks:
            mark.draw(self.screen, self.cam_x, self.cam_y)
        for u in self.upgrades:
            u.draw(self.screen, self.cam_x, self.cam_y)
        for ai in self.ais:
            ai.draw(self.screen, self.cam_x, self.cam_y)

        if self.invul_timer % 10 < 5:
            self.player.draw(self.screen, self.cam_x, self.cam_y)

        # UI
        v_text = self.font_gui.render(f"{abs(self.player.speed) * 12:.0f} KM/H", True, COLOR_UI)
        self.screen.blit(v_text, (40, 30))

        # Vida
        pygame.draw.rect(self.screen, (80, 80, 80), (40, 70, 250, 20), border_radius=10)
        h_w = (self.player.health / 100) * 250
        pygame.draw.rect(self.screen, COLOR_HEALTH, (40, 70, max(0, h_w), 20), border_radius=10)

        # Nitro
        pygame.draw.rect(self.screen, (80, 80, 80), (40, 100, 250, 12), border_radius=6)
        n_w = (self.player.nitro_level / self.player.nitro_max) * 250
        pygame.draw.rect(self.screen, COLOR_NITRO, (40, 100, max(0, n_w), 12), border_radius=6)

        score_txt = self.font_gui.render(f"PUNTAJE: {self.score}", True, (50, 50, 50))
        self.screen.blit(score_txt, (40, 130))

        # Alerta IA
        if any(ai.is_buffed for ai in self.ais):
            alert = self.font_gui.render("ADVERTENCIA: IA ENFURECIDA!", True, COLOR_AI_BUFF)
            self.screen.blit(alert, (WIDTH // 2 - alert.get_width() // 2, 20))

    def draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        msg = self.font_msg.render("JUEGO TERMINADO", True, (255, 50, 50))
        sub = self.font_btn.render(f"Puntaje Final: {self.score}", True, (255, 255, 255))
        instr = self.font_gui.render("Presiona cualquier tecla para ir al menu", True, (200, 200, 200))
        self.screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 80))
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 20))
        self.screen.blit(instr, (WIDTH // 2 - instr.get_width() // 2, HEIGHT // 2 + 100))


if __name__ == "__main__":
    Game().run()
