import json
import math
import os
import random
import sys
import threading
import urllib.error
import urllib.request

import pygame

# --- CONFIGURACION CONSTANTE ---
WIDTH, HEIGHT = 1200, 800
FPS = 60
GAME_TITLE = "Drift or Die"
USER_PROFILE = os.path.expanduser("~")
DOCUMENTS_DIR = os.path.join(USER_PROFILE, "Documents")
USER_GAME_DIR = os.path.join(DOCUMENTS_DIR, "DriftOrDie")
USER_MUSIC_DIR = os.path.join(USER_GAME_DIR, "assets", "music")
RAW_BASE_URL = "https://raw.githubusercontent.com/BluePandaOpn/Drift-or-Die/main"
MUSIC_MANIFEST_URL = f"{RAW_BASE_URL}/music_manifest.json"
LOCAL_MUSIC_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "music_manifest.json")
MUSIC_CACHE_METADATA_PATH = os.path.join(USER_MUSIC_DIR, "music_cache.json")
DEFAULT_MUSIC_VOLUME = 0.35
ENGINE_BASE_VOLUME = 0.08
ENGINE_SPEED_VOLUME = 0.35
DRIFT_BASE_VOLUME = 0.12
DRIFT_SPEED_VOLUME = 0.65
NITRO_BASE_VOLUME = 0.18
NITRO_SPEED_VOLUME = 0.45
SUPPORTED_EFFECT_EXTENSIONS = (".wav", ".ogg", ".mp3", ".m4a")
DRIFT_RELEASE_FRAMES = 6

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
COLOR_MAGNET = (255, 80, 120)
COLOR_SHIELD = (70, 240, 255)

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
MAGNET_RADIUS = 260
MAGNET_PULL_STRENGTH = 0.14
SHIELD_DURATION = 300
MAGNET_DURATION = 300
AI_INTERCEPT_ANTICIPATION = 22
AI_RESPAWN_DISTANCE = 2000


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


def ensure_directory(path):
    os.makedirs(path, exist_ok=True)
    return path


def safe_json_load(path, default_value):
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except (OSError, ValueError, TypeError):
        return default_value


def safe_json_dump(path, payload):
    try:
        ensure_directory(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, indent=2)
        return True
    except OSError:
        return False


def download_bytes(url, timeout=8):
    request = urllib.request.Request(url, headers={"User-Agent": f"{GAME_TITLE}/music-loader"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class AudioManager:
    def __init__(self):
        self.enabled = False
        self.ready = False
        self.failed = False
        self.thread = None
        self.status = "disabled"
        self.asset_map = {}
        self.background_volume = DEFAULT_MUSIC_VOLUME
        self.engine_channel = None
        self.drift_channel = None
        self.nitro_channel = None
        self.engine_sound = None
        self.drift_sound = None
        self.nitro_sound = None
        self.channel_states = {}
        self.drift_release_counter = 0

    def _log(self, message):
        print(f"[manager_music] {message}", flush=True)

    def start(self):
        if self.thread and self.thread.is_alive():
            self._log("inicio omitido: el hilo de audio ya esta activo")
            return
        self._log("iniciando sistema de audio")
        self.thread = threading.Thread(target=self._bootstrap_audio, daemon=True)
        self.thread.start()

    def _bootstrap_audio(self):
        try:
            self._log(f"asegurando carpeta local de musica: {USER_MUSIC_DIR}")
            ensure_directory(USER_MUSIC_DIR)
            if not self._init_mixer():
                return

            manifest = self._load_manifest()
            tracks = manifest.get("tracks", {})
            if not tracks:
                self.status = "manifest-empty"
                self._log("manifiesto sin pistas disponibles")
                return

            cache = safe_json_load(MUSIC_CACHE_METADATA_PATH, {})
            self._log(f"cache cargada desde: {MUSIC_CACHE_METADATA_PATH}")
            resolved_assets = self._ensure_assets(tracks, manifest.get("version", "0.0.0"), cache)
            self.asset_map = resolved_assets
            self.background_volume = self._read_float(manifest.get("background_volume"), DEFAULT_MUSIC_VOLUME)
            self._log(f"volumen de fondo configurado en: {self.background_volume:.2f}")
            self._load_sound_objects()
            self._play_background()
            self.ready = any(os.path.isfile(path) for path in resolved_assets.values())
            self.status = "ready" if self.ready else "no-audio-files"
            self._log(f"bootstrap completado. estado={self.status}, assets={list(resolved_assets.keys())}")
        except Exception:
            self.failed = True
            if not self.ready:
                self.status = "disabled"
            self._log("error inesperado durante el bootstrap del audio")

    def _init_mixer(self):
        try:
            if not pygame.mixer.get_init():
                self._log("inicializando pygame.mixer")
                pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self.engine_channel = pygame.mixer.Channel(1)
            self.drift_channel = pygame.mixer.Channel(2)
            self.nitro_channel = pygame.mixer.Channel(3)
            self.enabled = True
            self._log("mixer inicializado y canales reservados")
            return True
        except pygame.error:
            self.failed = True
            self.status = "mixer-error"
            self._log("fallo al inicializar pygame.mixer")
            return False

    def _load_manifest(self):
        self._log(f"intentando cargar manifiesto remoto: {MUSIC_MANIFEST_URL}")
        manifest = self._fetch_remote_manifest()
        if manifest:
            self._log("manifiesto remoto cargado correctamente")
            return manifest
        self._log(f"fallo remoto. usando manifiesto local: {LOCAL_MUSIC_MANIFEST_PATH}")
        local_manifest = safe_json_load(LOCAL_MUSIC_MANIFEST_PATH, {})
        return local_manifest if isinstance(local_manifest, dict) else {}

    def _fetch_remote_manifest(self):
        try:
            payload = download_bytes(MUSIC_MANIFEST_URL, timeout=8)
            manifest = json.loads(payload.decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            self._log("no se pudo descargar o parsear el manifiesto remoto")
            return None

        if not isinstance(manifest, dict):
            self._log("el manifiesto remoto no tiene formato valido")
            return None
        return manifest

    def _read_float(self, value, default_value):
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default_value

    def _ensure_assets(self, tracks, version, cache):
        resolved_assets = {}
        cache_version = cache.get("version")
        cache_tracks = cache.get("tracks", {})
        self._log(f"sincronizando assets. version remota={version}, version cache={cache_version}")

        for track_name, track_info in tracks.items():
            if not isinstance(track_info, dict):
                self._log(f"pista ignorada por formato invalido: {track_name}")
                continue
            url = track_info.get("url")
            filename = os.path.basename(str(track_info.get("filename") or os.path.basename(str(url or ""))))
            if not filename:
                self._log(f"pista ignorada sin filename valido: {track_name}")
                continue

            target_path = os.path.join(USER_MUSIC_DIR, filename)
            cached_track = cache_tracks.get(track_name, {})
            needs_download = (
                not os.path.isfile(target_path)
                or cache_version != version
                or cached_track.get("url") != url
            )
            self._log(
                f"pista={track_name} archivo={filename} existe={os.path.isfile(target_path)} "
                f"needs_download={needs_download}"
            )

            if needs_download and isinstance(url, str) and url.startswith(("http://", "https://")):
                try:
                    self._log(f"descargando pista {track_name} desde {url}")
                    payload = download_bytes(url, timeout=15)
                    temp_path = f"{target_path}.download"
                    with open(temp_path, "wb") as file_obj:
                        file_obj.write(payload)
                    os.replace(temp_path, target_path)
                    self._log(f"descarga completada para {track_name}: {target_path}")
                except (urllib.error.URLError, TimeoutError, OSError):
                    self._log(f"fallo la descarga de {track_name}. se intentara usar copia local si existe")
                    pass

            if os.path.isfile(target_path):
                resolved_assets[track_name] = target_path
                self._log(f"pista disponible para {track_name}: {target_path}")
            else:
                self._log(f"pista no disponible para {track_name}")

        safe_json_dump(
            MUSIC_CACHE_METADATA_PATH,
            {
                "version": version,
                "tracks": {
                    track_name: {"url": track_info.get("url"), "path": resolved_assets.get(track_name, "")}
                    for track_name, track_info in tracks.items()
                    if isinstance(track_info, dict)
                },
            },
        )
        self._log(f"cache de audio actualizada en: {MUSIC_CACHE_METADATA_PATH}")
        return resolved_assets

    def _resolve_effect_candidate_paths(self, effect_key):
        asset_path = self.asset_map.get(effect_key)
        if not asset_path:
            return []

        root_path, ext = os.path.splitext(asset_path)
        candidates = []
        preferred_extensions = (".wav", ".ogg", ".mp3", ".m4a")
        if ext.lower() in preferred_extensions:
            ordered_extensions = tuple(
                candidate_ext for candidate_ext in preferred_extensions if candidate_ext != ext.lower()
            ) + (ext.lower(),)
            ordered_extensions = (".wav", ".ogg", ext.lower(), ".mp3", ".m4a")
        else:
            ordered_extensions = preferred_extensions + (ext.lower(),)

        seen = set()
        for candidate_ext in ordered_extensions:
            candidate_path = root_path + candidate_ext
            if candidate_path in seen:
                continue
            seen.add(candidate_path)
            if os.path.isfile(candidate_path):
                candidates.append(candidate_path)

        if asset_path not in seen and os.path.isfile(asset_path):
            candidates.append(asset_path)
        return candidates

    def _load_sound_objects(self):
        effect_targets = (
            ("accelerate", "engine_sound"),
            ("drift", "drift_sound"),
            ("nitro", "nitro_sound"),
        )
        self._log("cargando efectos en memoria con fallback de formatos")
        for effect_key, attr_name in effect_targets:
            setattr(self, attr_name, None)
            candidate_paths = self._resolve_effect_candidate_paths(effect_key)
            if not candidate_paths:
                self._log(f"sin archivo disponible para efecto={effect_key}")
                continue

            for candidate_path in candidate_paths:
                try:
                    setattr(self, attr_name, pygame.mixer.Sound(candidate_path))
                    self._log(f"efecto cargado: {effect_key} <- {candidate_path}")
                    break
                except pygame.error:
                    self.failed = True
                    self._log(f"fallo al cargar efecto: {effect_key} archivo={candidate_path}")

        if not any((self.engine_sound, self.drift_sound, self.nitro_sound)):
            self.status = "playback-error"
            self._log("ningun efecto pudo cargarse en memoria")
            return

    def _play_background(self):
        background_path = self.asset_map.get("background")
        if not background_path:
            self._log("no hay pista de fondo disponible")
            return
        try:
            self._log(f"reproduciendo musica de fondo desde {background_path}")
            pygame.mixer.music.load(background_path)
            pygame.mixer.music.set_volume(self.background_volume)
            pygame.mixer.music.play(-1)
            self._log("musica de fondo activa en loop")
        except pygame.error:
            self.failed = True
            self.status = "background-error"
            self._log("fallo al reproducir la musica de fondo")

    def update_vehicle_audio(self, player):
        if not self.enabled or not player or not pygame.mixer.get_init():
            return

        speed_ratio = min(1.0, abs(player.speed) / max(1.0, player.max_speed))
        is_accelerating = player.is_moving and not player.is_nitro_active
        if player.is_drifting:
            self.drift_release_counter = DRIFT_RELEASE_FRAMES
        else:
            self.drift_release_counter = max(0, self.drift_release_counter - 1)
        is_drifting = self.drift_release_counter > 0
        is_using_nitro = player.is_nitro_active

        self._update_loop_channel(
            "accelerate",
            self.engine_channel,
            self.engine_sound,
            is_accelerating,
            ENGINE_BASE_VOLUME + (speed_ratio * ENGINE_SPEED_VOLUME),
        )
        self._update_loop_channel(
            "drift",
            self.drift_channel,
            self.drift_sound,
            is_drifting,
            DRIFT_BASE_VOLUME + (speed_ratio * DRIFT_SPEED_VOLUME),
        )
        self._update_loop_channel(
            "nitro",
            self.nitro_channel,
            self.nitro_sound,
            is_using_nitro,
            NITRO_BASE_VOLUME + (speed_ratio * NITRO_SPEED_VOLUME),
        )

    def _update_loop_channel(self, channel_name, channel, sound, should_play, volume):
        if channel is None or sound is None:
            return
        try:
            clamped_volume = max(0.0, min(1.0, volume))
            target_volume = clamped_volume if should_play else 0.0
            previous = self.channel_states.get(channel_name)
            was_playing = bool(previous[0]) if previous else False
            current = (bool(should_play), round(target_volume, 2))
            if previous != current:
                self.channel_states[channel_name] = current
                self._log(f"canal={channel_name} play={current[0]} volume={current[1]:.2f}")

            if should_play:
                if not was_playing or not channel.get_busy():
                    if channel.get_busy():
                        channel.stop()
                    channel.play(sound, loops=-1)
                    self._log(f"canal={channel_name} reiniciado desde 0")
                channel.set_volume(clamped_volume)
            elif channel.get_busy():
                channel.stop()
                self._log(f"canal={channel_name} detenido")
        except pygame.error:
            self.failed = True
            self._log(f"error de reproduccion en canal={channel_name}")

    def stop(self):
        if not pygame.mixer.get_init():
            return
        try:
            self._log("deteniendo sistema de audio")
            for channel in (self.engine_channel, self.drift_channel, self.nitro_channel):
                if channel is not None:
                    channel.stop()
            pygame.mixer.music.stop()
            self._log("audio detenido")
        except pygame.error:
            self._log("fallo al detener el audio")


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
        self.type = random.choice(["speed", "drift", "nitro", "accel", "magnet", "shield"])
        self.angle = 0.0
        if self.type == "nitro":
            self.color = COLOR_NITRO
        elif self.type == "magnet":
            self.color = COLOR_MAGNET
        elif self.type == "shield":
            self.color = COLOR_SHIELD
        else:
            self.color = COLOR_COLLECTIBLE

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
        self.handbrake_drift = 0.90
        self.grip = 0.22 if is_ai else 0.31
        self.side_friction = 0.86 if is_ai else 0.76

        # Jugador
        self.health = 100
        self.collected_types = []
        self.nitro_max = 100
        self.nitro_level = 50
        self.nitro_power = 0.6

        self.dir_x = 0.0
        self.dir_y = 0.0
        self.is_moving = False
        self.is_braking = False
        self.is_drifting = False
        self.is_nitro_active = False
        self.particles = []
        self.magnet_timer = 0
        self.shield_timer = 0

        # Buffs (IA)
        self.buff_timer = 0
        self.is_buffed = False
        self.ai_error_x = random.uniform(-90.0, 90.0) if is_ai else 0.0
        self.ai_error_y = random.uniform(-90.0, 90.0) if is_ai else 0.0

    def setup_class(self, choice):
        if choice == 0:  # DRIFT KING
            self.drift_factor = 0.95
            self.handbrake_drift = 0.935
            self.rotation_speed = 6.5
            self.grip = 0.25
            self.side_friction = 0.74
            self.color = (150, 50, 250)
        elif choice == 1:  # SPEED DEMON
            self.max_speed = 18.0
            self.acceleration = 0.35
            self.grip = 0.33
            self.side_friction = 0.80
            self.color = (50, 200, 50)
        elif choice == 2:  # NITRO JUNKIE
            self.nitro_max = 200
            self.nitro_level = 200
            self.nitro_power = 1.0
            self.grip = 0.28
            self.side_friction = 0.78
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
            self.handbrake_drift = min(0.955, self.handbrake_drift + 0.003)
            self.rotation_speed += 0.4
            self.side_friction = max(0.72, self.side_friction - 0.008)
        elif upg_type == "magnet":
            self.magnet_timer = MAGNET_DURATION
        elif upg_type == "shield":
            self.shield_timer = SHIELD_DURATION

    def lose_random_upgrade(self):
        if self.collected_types:
            removed = self.collected_types.pop(random.randrange(len(self.collected_types)))
            if removed == "speed":
                self.max_speed = max(10.0, self.max_speed - 1.2)
            elif removed == "accel":
                self.acceleration = max(0.15, self.acceleration - 0.06)
            elif removed == "drift":
                self.drift_factor = max(0.85, self.drift_factor - 0.01)
                self.handbrake_drift = max(0.88, self.handbrake_drift - 0.003)
                self.rotation_speed = max(3.0, self.rotation_speed - 0.4)
                self.side_friction = min(0.90, self.side_friction + 0.01)
            return True
        return False

    def update(self, keys_or_target, skid_marks):
        input_fwd = False
        input_back = False
        input_left = False
        input_right = False
        input_handbrake = False
        input_nitro = False
        threshold_brake = False

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
                anticipacion = AI_INTERCEPT_ANTICIPATION + random.uniform(-4.0, 6.0)
                future_x = keys_or_target.x + (keys_or_target.dir_x * anticipacion) + self.ai_error_x
                future_y = keys_or_target.y + (keys_or_target.dir_y * anticipacion) + self.ai_error_y
                target_angle = math.degrees(math.atan2(-(future_y - self.y), future_x - self.x))
                angle_diff = (target_angle - self.angle + 180) % 360 - 180
                if angle_diff > 5:
                    input_left = True
                elif angle_diff < -5:
                    input_right = True
                input_fwd = True
                if dist < 140 or (dist < 260 and abs(angle_diff) > 55):
                    threshold_brake = True
                if dist < 100:
                    input_handbrake = True

        self.is_nitro_active = input_nitro
        if not self.is_ai:
            if self.magnet_timer > 0:
                self.magnet_timer -= 1
            if self.shield_timer > 0:
                self.shield_timer -= 1

        if threshold_brake:
            input_handbrake = True
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

        turn_input = 0
        if input_left:
            turn_input += 1
        if input_right:
            turn_input -= 1

        if self.speed != 0:
            rot_dir = 1 if self.speed > 0 else -1
            turn_mod = min(1.0, abs(self.speed) / 3.5)
            if self.is_braking:
                turn_mod = min(1.10, turn_mod + 0.06)
            self.angle += turn_input * self.rotation_speed * rot_dir * turn_mod

        target_dx = math.cos(math.radians(self.angle)) * self.speed
        target_dy = -math.sin(math.radians(self.angle)) * self.speed

        if abs(self.dir_x) + abs(self.dir_y) < 0.001:
            self.dir_x = target_dx
            self.dir_y = target_dy
        else:
            forward_x = math.cos(math.radians(self.angle))
            forward_y = -math.sin(math.radians(self.angle))
            lateral_x = -forward_y
            lateral_y = forward_x
            speed_ratio = min(1.0, abs(self.speed) / max(1.0, self.max_speed))
            drift_scale = 0.35 + speed_ratio * 0.50

            forward_speed = self.dir_x * forward_x + self.dir_y * forward_y
            lateral_speed = self.dir_x * lateral_x + self.dir_y * lateral_y

            grip = self.grip + (1.0 - speed_ratio) * 0.12
            if self.is_braking:
                grip *= 0.88
            forward_speed += (self.speed - forward_speed) * grip

            side_friction = self.side_friction
            if self.is_braking:
                side_friction = min(0.92, self.handbrake_drift + speed_ratio * 0.015)
            lateral_speed *= side_friction

            if turn_input != 0 and abs(self.speed) > 2.0:
                drift_push = (0.08 if self.is_braking else 0.03) * drift_scale
                lateral_speed += turn_input * abs(self.speed) * drift_push

            self.dir_x = forward_x * forward_speed + lateral_x * lateral_speed
            self.dir_y = forward_y * forward_speed + lateral_y * lateral_speed

        drift_val = math.hypot(target_dx - self.dir_x, target_dy - self.dir_y)
        self.is_moving = abs(self.speed) > 0.35 or math.hypot(self.dir_x, self.dir_y) > 0.35
        self.is_drifting = (drift_val > 0.8 or self.is_braking) and abs(self.speed) > 3
        if (drift_val > 0.8 or self.is_braking) and abs(self.speed) > 3:
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

        if self.shield_timer > 0:
            shield_radius = 36 + math.sin(pygame.time.get_ticks() * 0.015) * 3
            pygame.draw.circle(surface, (*COLOR_SHIELD, 70), (int(screen_x), int(screen_y)), int(shield_radius), 3)
        elif self.magnet_timer > 0:
            pulse_radius = 30 + math.sin(pygame.time.get_ticks() * 0.02) * 6
            pygame.draw.circle(surface, (*COLOR_MAGNET, 60), (int(screen_x), int(screen_y)), int(pulse_radius), 2)

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
        pygame.display.set_caption(GAME_TITLE)
        self.clock = pygame.time.Clock()
        self.font_gui = pygame.font.SysFont("Impact", 28)
        self.font_msg = pygame.font.SysFont("Impact", 72)
        self.font_btn = pygame.font.SysFont("Impact", 36)
        self.font_small = pygame.font.SysFont("Arial", 22)
        self.music = AudioManager()
        self.music.start()

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
        self.game_over_buttons = [
            {"name": "REINICIAR", "action": "restart"},
            {"name": "MENU", "action": "menu"},
        ]
        self.selected_class = 0
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

    def start_game(self, class_index=None):
        if class_index is not None:
            self.selected_class = class_index
        self.reset_game()
        self.player.setup_class(self.selected_class)
        self.state = "PLAYING"

    def handle_game_over_action(self, action):
        if action == "restart":
            self.start_game()
        else:
            self.state = "MENU_MAIN"
            self.reset_game()

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
                    self.music.stop()
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
                self.start_game(i)
                pygame.time.delay(200)

    def draw_options_menu(self):
        self.screen.fill((25, 28, 38))
        title = self.font_msg.render("OPCIONES", True, (255, 255, 255))
        line1 = self.font_gui.render("Controles: W A S D para mover, ESPACIO para derrapar.", True, (220, 220, 220))
        line2 = self.font_gui.render("SHIFT IZQ para usar nitro.", True, (220, 220, 220))
        line3 = self.font_gui.render("ESC para volver al menu principal.", True, (220, 220, 220))
        if self.music.ready:
            music_text = f"Musica: cargada en {USER_MUSIC_DIR}"
            music_color = (120, 220, 160)
        elif self.music.failed:
            music_text = "Musica: error detectado, el juego sigue sin audio"
            music_color = (255, 170, 120)
        else:
            music_text = "Musica: creando carpeta local y descargando desde GitHub"
            music_color = (180, 180, 210)
        line4 = self.font_gui.render(music_text, True, music_color)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 120))
        self.screen.blit(line1, (WIDTH // 2 - line1.get_width() // 2, 300))
        self.screen.blit(line2, (WIDTH // 2 - line2.get_width() // 2, 350))
        self.screen.blit(line3, (WIDTH // 2 - line3.get_width() // 2, 430))
        self.screen.blit(line4, (WIDTH // 2 - line4.get_width() // 2, 500))

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

    def apply_magnet_effect(self):
        if self.player.magnet_timer <= 0:
            return

        for upgrade in self.upgrades:
            dx = self.player.x - upgrade.x
            dy = self.player.y - upgrade.y
            dist = math.hypot(dx, dy)
            if dist <= 0.001 or dist > MAGNET_RADIUS:
                continue

            angle = math.atan2(dy, dx)
            strength = (1.0 - (dist / MAGNET_RADIUS)) * MAGNET_PULL_STRENGTH
            target_x = upgrade.x + math.cos(angle) * dist * strength
            target_y = upgrade.y + math.sin(angle) * dist * strength
            upgrade.x += (target_x - upgrade.x) * 0.55
            upgrade.y += (target_y - upgrade.y) * 0.55

    def respawn_far_ais(self):
        move_x = self.player.dir_x if abs(self.player.dir_x) > 0.1 else math.cos(math.radians(self.player.angle)) * 8
        move_y = self.player.dir_y if abs(self.player.dir_y) > 0.1 else -math.sin(math.radians(self.player.angle)) * 8
        heading = math.atan2(move_y, move_x)

        for ai in self.ais:
            dist = math.hypot(ai.x - self.player.x, ai.y - self.player.y)
            if dist <= AI_RESPAWN_DISTANCE:
                continue

            offset_angle = heading + random.uniform(-0.7, 0.7)
            spawn_distance = random.uniform(650, 1100)
            ai.x = self.player.x + math.cos(offset_angle) * spawn_distance
            ai.y = self.player.y + math.sin(offset_angle) * spawn_distance
            ai.dir_x = 0.0
            ai.dir_y = 0.0
            ai.speed = max(2.0, self.player.speed * 0.55)
            ai.angle = math.degrees(math.atan2(-move_y, move_x)) + random.uniform(-18.0, 18.0)

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
                    self.music.stop()
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
                            self.handle_game_over_action("menu")
                    elif self.state == "GAME_OVER":
                        if event.key in (pygame.K_r, pygame.K_RETURN, pygame.K_SPACE):
                            self.handle_game_over_action("restart")
                        elif event.key in (pygame.K_m, pygame.K_ESCAPE):
                            self.handle_game_over_action("menu")

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
        self.music.update_vehicle_audio(self.player)
        for ai in self.ais:
            ai.update(self.player, self.skid_marks)

        self.cam_x += (self.player.x - self.cam_x) * 0.12
        self.cam_y += (self.player.y - self.cam_y) * 0.12

        self.skid_marks = [mark for mark in self.skid_marks if mark.update()]
        self.maintain_upgrade_density()
        self.apply_magnet_effect()
        self.respawn_far_ais()

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
                    if self.player.shield_timer > 0:
                        repel_dx = ai.x - self.player.x
                        repel_dy = ai.y - self.player.y
                        repel_dist = math.hypot(repel_dx, repel_dy) or 1.0
                        repel_force = 14.0
                        ai.dir_x += (repel_dx / repel_dist) * repel_force
                        ai.dir_y += (repel_dy / repel_dist) * repel_force
                        ai.speed = min(ai.max_speed + 4, abs(ai.speed) + 3)
                        ai.x += (repel_dx / repel_dist) * 18
                        ai.y += (repel_dy / repel_dist) * 18
                        self.score += 150
                    else:
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
        instr = self.font_gui.render("R o Enter: reiniciar | M o Esc: menu", True, (200, 200, 200))
        self.screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 - 80))
        self.screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 20))
        self.screen.blit(instr, (WIDTH // 2 - instr.get_width() // 2, HEIGHT // 2 + 100))

        mx, my = pygame.mouse.get_pos()
        for i, button in enumerate(self.game_over_buttons):
            rect = pygame.Rect(WIDTH // 2 - 240 + i * 260, HEIGHT // 2 + 155, 220, 68)
            is_hover = rect.collidepoint(mx, my)
            color = (200, 70, 70) if button["action"] == "restart" else (70, 110, 185)
            fill = color if is_hover else (50, 50, 66)
            pygame.draw.rect(self.screen, fill, rect, border_radius=16)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3, border_radius=16)

            label = self.font_btn.render(button["name"], True, (255, 255, 255))
            self.screen.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))

            if is_hover and pygame.mouse.get_pressed()[0]:
                self.handle_game_over_action(button["action"])
                pygame.time.delay(180)


if __name__ == "__main__":
    Game().run()
