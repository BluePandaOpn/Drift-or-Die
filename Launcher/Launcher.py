# Version: V1.2
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from threading import Thread

import customtkinter as ctk
import requests


APP_NAME = "Drift Or Die Hub"
GAME_NAME = "Drift Or Die Pro"
LAUNCHER_VERSION = "1.2.0"

USER_PROFILE = os.path.expanduser("~")
DOCUMENTS_DIR = os.path.join(USER_PROFILE, "Documents")
ROOT_INSTALL_DIR = os.path.join(DOCUMENTS_DIR, "DriftOrDie")
LAUNCHER_INSTALL_DIR = os.path.join(ROOT_INSTALL_DIR, "Launcher")
GAME_INSTALL_DIR = os.path.join(ROOT_INSTALL_DIR, "Game")
LAUNCHER_EXECUTABLE_PATH = os.path.join(LAUNCHER_INSTALL_DIR, "DriftOrDieLauncher.exe")
GAME_EXECUTABLE_PATH = os.path.join(GAME_INSTALL_DIR, "Snake.exe")
GAME_VERSION_PATH = os.path.join(GAME_INSTALL_DIR, "version.txt")
LAUNCHER_STATE_PATH = os.path.join(LAUNCHER_INSTALL_DIR, "launcher_state.json")
DESKTOP_SHORTCUT_PATH = os.path.join(os.path.join(USER_PROFILE, "Desktop"), "Drift Or Die Launcher.lnk")

RAW_BASE_URL = "https://raw.githubusercontent.com/BluePandaOpn/Drift-or-Die/main"
MANIFEST_URL = f"{RAW_BASE_URL}/launcher_manifest.json"
FALLBACK_GAME_URL = "https://github.com/BluePandaOpn/Drift-or-Die/raw/main/bin/Snake.exe"
FALLBACK_LAUNCHER_URL = "https://github.com/BluePandaOpn/Drift-or-Die/raw/main/Launcher/SnakeLauncher.exe"
FALLBACK_GAME_VERSION_URL = f"{RAW_BASE_URL}/version.txt"

ACCENT = "#2ecc71"
ACCENT_ALT = "#38bdf8"
TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#7f8c8d"
WARNING = "#f59e0b"
ERROR = "#fb7185"
BG_PANEL = "#182338"
BG_CARD = "#182338"


def parse_version(version_text):
    parts = [int(part) for part in re.findall(r"\d+", version_text or "0")]
    return tuple((parts + [0, 0, 0])[:3])


def get_project_root():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_resource_path(relative_path):
    root = get_project_root()
    candidates = [
        os.path.join(root, relative_path),
        os.path.join(root, "assets", os.path.basename(relative_path)),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def ensure_directory(path):
    os.makedirs(path, exist_ok=True)
    return path


def read_text_file(path, default_value=""):
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return file_obj.read().strip()
    except OSError:
        return default_value


def write_text_file(path, content):
    ensure_directory(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as file_obj:
        file_obj.write(content)


def copy_file(source_path, destination_path):
    ensure_directory(os.path.dirname(destination_path))
    temp_copy = f"{destination_path}.download"
    shutil.copyfile(source_path, temp_copy)
    os.replace(temp_copy, destination_path)


def create_windows_shortcut(shortcut_path, target_path, working_directory, icon_path=None):
    shortcut_path = shortcut_path.replace("'", "''")
    target_path = target_path.replace("'", "''")
    working_directory = working_directory.replace("'", "''")
    icon_literal = "$null"
    if icon_path:
        icon_literal = "'" + icon_path.replace("'", "''") + "'"
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $ws.CreateShortcut('{shortcut_path}'); "
        f"$shortcut.TargetPath = '{target_path}'; "
        f"$shortcut.WorkingDirectory = '{working_directory}'; "
        "$shortcut.Description = 'Snake Launcher'; "
        f"if ({icon_literal} -ne $null) {{ $shortcut.IconLocation = {icon_literal}; }} "
        "$shortcut.Save()"
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        creationflags=creation_flags,
    )


class SnakeLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.width = 400
        self.height = 450
        self.overrideredirect(True)
        self.resizable(False, False)
        self.configure(fg_color="#28282d")
        ctk.set_appearance_mode("dark")

        icon_path = get_resource_path("ico.ico")
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.remote_manifest = {}
        self.progress_mode = "determinate"
        self.progress_value = 0
        self.versions_text = ""
        self.notes_text = ""

        self.build_layout()
        self.center_window()
        self.animar_gusano()
        Thread(target=self.proceso_principal, daemon=True).start()

    def build_layout(self):
        self.label_titulo = ctk.CTkLabel(
            self,
            text="SNAKE ENGINE",
            font=("Arial", 26, "bold"),
            text_color="white",
        )
        self.label_titulo.pack(pady=(58, 22))

        self.canvas = tk.Canvas(self, width=120, height=120, bg="#28282d", highlightthickness=0)
        self.canvas.pack(pady=10)

        self.posiciones = [(20, 20), (70, 20), (70, 70), (20, 70)]
        self.segmentos_indices = [0, 1, 2]
        self.rects = []

        for i in range(3):
            x, y = self.posiciones[self.segmentos_indices[i]]
            color = "#27ae60" if i == 2 else "#2ecc71"
            self.rects.append(self.canvas.create_rectangle(x, y, x + 30, y + 30, fill=color, outline=""))

        self.label_estado = ctk.CTkLabel(
            self,
            text="Buscando actualizaciones...",
            font=("Arial", 13),
            text_color="#2ecc71",
        )
        self.label_estado.pack(pady=(22, 10))

        self.label_detalles = ctk.CTkLabel(
            self,
            text="Consultando version en GitHub...",
            font=("Arial", 11),
            text_color="#7f8c8d",
            wraplength=280,
            justify="center",
        )
        self.label_detalles.pack(pady=(0, 0))

    def center_window(self):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (self.width // 2)
        y = (screen_height // 2) - (self.height // 2)
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def animar_gusano(self):
        todas = {0, 1, 2, 3}
        vacia = list(todas - set(self.segmentos_indices))[0]
        self.segmentos_indices.pop(0)
        self.segmentos_indices.append(vacia)

        for i in range(3):
            nx, ny = self.posiciones[self.segmentos_indices[i]]
            self.canvas.coords(self.rects[i], nx, ny, nx + 30, ny + 30)

        self.after(350, self.animar_gusano)

    def ui(self, callback, *args, **kwargs):
        self.after(0, lambda: callback(*args, **kwargs))

    def set_status(self, chip_text=None, chip_color=None, title=None, detail=None):
        def update():
            if title is not None:
                self.label_estado.configure(text=title)
            elif chip_text is not None:
                self.label_estado.configure(text=chip_text)
            if chip_color is not None:
                self.label_estado.configure(text_color=chip_color)
            if detail is not None:
                self.label_detalles.configure(text=detail)

        self.ui(update)

    def set_progress(self, value=None, mode=None, label=None):
        def update():
            if mode:
                self.progress_mode = mode

            if value is not None:
                self.progress_value = max(0.0, min(1.0, value))

            if label is not None:
                self.label_detalles.configure(text=label)

        self.ui(update)

    def set_versions(self, game_text=None, launcher_text=None):
        if game_text is not None:
            self.versions_text = game_text
        if launcher_text is not None:
            if self.versions_text:
                self.versions_text = f"{self.versions_text}\n{launcher_text}"
            else:
                self.versions_text = launcher_text

    def set_notes(self, notes):
        self.notes_text = "\n".join(f"- {note}" for note in notes[:3]) if notes else ""

    def show_toast(self, title, message, accent_color=ACCENT_ALT):
        def build_toast():
            toast = ctk.CTkToplevel(self)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.configure(fg_color=BG_CARD)

            width = 360
            height = 118
            x = self.winfo_screenwidth() - width - 24
            y = self.winfo_screenheight() - height - 54
            toast.geometry(f"{width}x{height}+{x}+{y}")

            frame = ctk.CTkFrame(toast, fg_color=BG_CARD, corner_radius=18, border_width=1, border_color="#24324c")
            frame.pack(fill="both", expand=True)

            accent = ctk.CTkFrame(frame, fg_color=accent_color, width=8, corner_radius=18)
            accent.pack(side="left", fill="y")

            content = ctk.CTkFrame(frame, fg_color="transparent")
            content.pack(side="left", fill="both", expand=True, padx=14, pady=14)

            header = ctk.CTkLabel(
                content,
                text=f"{GAME_NAME} | {title}",
                font=("Segoe UI Semibold", 15),
                text_color=TEXT_PRIMARY,
                anchor="w",
            )
            header.pack(fill="x")

            message_label = ctk.CTkLabel(
                content,
                text=message,
                font=("Segoe UI", 13),
                text_color=TEXT_SECONDARY,
                justify="left",
                wraplength=280,
                anchor="w",
            )
            message_label.pack(fill="x", pady=(8, 0))

            toast.after(4400, toast.destroy)

        self.ui(build_toast)

    def load_launcher_state(self):
        try:
            with open(LAUNCHER_STATE_PATH, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except (OSError, json.JSONDecodeError):
            return {}

    def save_launcher_state(self, state):
        ensure_directory(LAUNCHER_INSTALL_DIR)
        with open(LAUNCHER_STATE_PATH, "w", encoding="utf-8") as file_obj:
            json.dump(state, file_obj, indent=2)

    def ensure_install_layout(self):
        ensure_directory(ROOT_INSTALL_DIR)
        ensure_directory(LAUNCHER_INSTALL_DIR)
        ensure_directory(GAME_INSTALL_DIR)

    def seed_launcher_from_local_build(self):
        if os.path.exists(LAUNCHER_EXECUTABLE_PATH):
            return False

        local_build_candidates = [
            os.path.join(get_project_root(), "Launcher", "SnakeLauncher.exe"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "SnakeLauncher.exe"),
        ]
        for candidate in local_build_candidates:
            if os.path.isfile(candidate):
                copy_file(candidate, LAUNCHER_EXECUTABLE_PATH)
                self.ensure_desktop_shortcut()
                return True

        return False

    def ensure_local_launcher_copy(self):
        if not getattr(sys, "frozen", False):
            return False

        current_launcher = os.path.abspath(sys.executable)
        installed_launcher = os.path.abspath(LAUNCHER_EXECUTABLE_PATH)
        if current_launcher == installed_launcher:
            return False

        copy_file(current_launcher, installed_launcher)
        self.ensure_desktop_shortcut()

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([installed_launcher], cwd=LAUNCHER_INSTALL_DIR, creationflags=creation_flags)
        self.after(200, self.destroy)
        return True

    def ensure_desktop_shortcut(self):
        if not os.path.exists(LAUNCHER_EXECUTABLE_PATH):
            return

        icon_path = get_resource_path("ico.ico")
        try:
            create_windows_shortcut(
                DESKTOP_SHORTCUT_PATH,
                LAUNCHER_EXECUTABLE_PATH,
                LAUNCHER_INSTALL_DIR,
                icon_path or LAUNCHER_EXECUTABLE_PATH,
            )
        except Exception:
            pass

    def fetch_manifest(self):
        response = requests.get(MANIFEST_URL, timeout=8)
        response.raise_for_status()
        manifest = response.json()
        game_info = manifest.get("game", {})
        launcher_info = manifest.get("launcher", {})
        game_info.setdefault("version", read_text_file(GAME_VERSION_PATH, "0.0.0"))
        game_info.setdefault("url", FALLBACK_GAME_URL)
        launcher_info.setdefault("version", LAUNCHER_VERSION)
        launcher_info.setdefault("url", FALLBACK_LAUNCHER_URL)
        manifest["game"] = game_info
        manifest["launcher"] = launcher_info
        return manifest

    def fetch_manifest_fallback(self):
        version_response = requests.get(FALLBACK_GAME_VERSION_URL, timeout=8)
        version_response.raise_for_status()
        game_version = version_response.text.strip()
        return {
            "game": {
                "version": game_version,
                "url": FALLBACK_GAME_URL,
                "notes": ["Actualizacion basica del ejecutable del juego."],
            },
            "launcher": {
                "version": LAUNCHER_VERSION,
                "url": FALLBACK_LAUNCHER_URL,
                "notes": ["Modo de compatibilidad sin manifiesto remoto."],
            },
        }

    def download_file(self, url, destination, progress_prefix):
        temp_destination = f"{destination}.download"
        ensure_directory(os.path.dirname(destination))
        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(temp_destination, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                file_obj.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    fraction = downloaded / total_size
                    self.set_progress(fraction, "determinate", f"{progress_prefix}: {int(fraction * 100)}%")
                else:
                    self.set_progress(None, "indeterminate", f"{progress_prefix}...")

        os.replace(temp_destination, destination)
        self.set_progress(1, "determinate", "100%")

    def schedule_launcher_replace(self, new_launcher_path):
        current_launcher = sys.executable
        if not getattr(sys, "frozen", False) or not os.path.isfile(current_launcher):
            return False

        temp_dir = tempfile.mkdtemp(prefix="snake-launcher-")
        updater_path = os.path.join(temp_dir, "update_launcher.bat")
        script = "\n".join(
            [
                "@echo off",
                "setlocal",
                f'if not exist "{LAUNCHER_INSTALL_DIR}" mkdir "{LAUNCHER_INSTALL_DIR}"',
                "ping 127.0.0.1 -n 3 > nul",
                f'copy /Y "{new_launcher_path}" "{LAUNCHER_EXECUTABLE_PATH}" > nul',
                f'start "" "{LAUNCHER_EXECUTABLE_PATH}"',
                'del "%~f0"',
            ]
        )
        with open(updater_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(script)

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd", "/c", updater_path], creationflags=creation_flags)
        return True

    def maybe_update_launcher(self, manifest):
        launcher_info = manifest.get("launcher", {})
        remote_version = launcher_info.get("version", LAUNCHER_VERSION)
        remote_url = launcher_info.get("url", "").strip()
        self.set_versions(launcher_text=f"Lanzador: {LAUNCHER_VERSION} -> remoto {remote_version}")

        if parse_version(remote_version) <= parse_version(LAUNCHER_VERSION) or not remote_url:
            return False

        self.set_status(
            chip_text="Launcher Update",
            chip_color=WARNING,
            title="Actualizando el lanzador",
            detail=f"Instalando launcher {remote_version}...",
        )
        self.show_toast("Actualizacion del launcher", f"Instalando launcher {remote_version}.", WARNING)

        if not getattr(sys, "frozen", False):
            self.set_status(
                chip_text="Modo Desarrollo",
                chip_color=ACCENT_ALT,
                detail="La autoactualizacion del launcher solo se aplica al ejecutable empaquetado.",
            )
            return False

        temp_dir = tempfile.mkdtemp(prefix="snake-launcher-binary-")
        downloaded_launcher = os.path.join(temp_dir, "SnakeLauncher.exe")
        self.download_file(remote_url, downloaded_launcher, "Descargando launcher")
        return self.schedule_launcher_replace(downloaded_launcher)

    def update_game_if_needed(self, manifest):
        game_info = manifest.get("game", {})
        remote_version = game_info.get("version", "0.0.0")
        remote_url = game_info.get("url", FALLBACK_GAME_URL)
        notes = game_info.get("notes", [])
        local_version = read_text_file(GAME_VERSION_PATH, "Sin instalar")
        local_exists = os.path.exists(GAME_EXECUTABLE_PATH)

        self.set_notes(notes[:5])
        self.set_versions(game_text=f"Juego instalado: {local_version}", launcher_text=None)

        if local_exists and parse_version(local_version) >= parse_version(remote_version):
            self.set_status(
                chip_text="Listo",
                chip_color=ACCENT,
                title="Juego actualizado",
                detail=f"Version actual: {local_version}",
            )
            self.set_progress(1, "determinate", "Sin descargas pendientes")
            return local_version

        self.set_status(
            chip_text="Update Game",
            chip_color=ACCENT,
            title="Descargando actualizacion",
            detail=f"Instalando {GAME_NAME} {remote_version}...",
        )
        self.show_toast("Nueva version", f"Descargando {GAME_NAME} {remote_version}.", ACCENT)
        self.download_file(remote_url, GAME_EXECUTABLE_PATH, "Descargando juego")
        write_text_file(GAME_VERSION_PATH, remote_version)
        self.set_versions(game_text=f"Juego instalado: {remote_version}", launcher_text=None)
        return remote_version

    def ejecutar_juego(self):
        if not os.path.exists(GAME_EXECUTABLE_PATH):
            self.set_status(
                chip_text="Error",
                chip_color=ERROR,
                title="Error fatal",
                detail="Snake.exe no encontrado.",
            )
            self.show_toast("Error de arranque", "No se encontro Snake.exe.", ERROR)
            return

        self.set_status(
            chip_text="Arrancando",
            chip_color=ACCENT_ALT,
            title=f"Iniciando {GAME_NAME}",
            detail="Abriendo juego...",
        )
        self.set_progress(1, "determinate", "Inicio completado")
        self.show_toast("Inicio del juego", f"Abriendo {GAME_NAME}.", ACCENT_ALT)
        subprocess.Popen([GAME_EXECUTABLE_PATH], cwd=GAME_INSTALL_DIR)
        self.after(1200, self.destroy)

    def proceso_principal(self):
        self.ensure_install_layout()
        self.seed_launcher_from_local_build()
        if self.ensure_local_launcher_copy():
            return
        self.ensure_desktop_shortcut()
        state = self.load_launcher_state()

        self.set_progress(None, "indeterminate", "Consultando version en GitHub...")
        self.set_status(
            chip_text="Online",
            chip_color=ACCENT_ALT,
            title="Buscando actualizaciones...",
            detail="Consultando version en GitHub...",
        )

        try:
            manifest = self.fetch_manifest()
        except Exception:
            try:
                manifest = self.fetch_manifest_fallback()
            except Exception:
                manifest = None

        if manifest is None:
            if os.path.exists(GAME_EXECUTABLE_PATH):
                local_version = read_text_file(GAME_VERSION_PATH, "desconocida")
                self.set_versions(game_text=f"Juego instalado: {local_version}", launcher_text=f"Lanzador: {LAUNCHER_VERSION}")
                self.set_status(
                    chip_text="Offline",
                    chip_color=WARNING,
                    title="Modo offline",
                    detail="No se pudo verificar la version.",
                )
                self.set_progress(1, "determinate", "Sin conexion")
                self.set_notes(["Arranque local sin verificacion remota."])
                self.show_toast("Modo offline", "Se abrira la copia local instalada.", WARNING)
                self.ejecutar_juego()
                return

            self.set_status(
                chip_text="Error",
                chip_color=ERROR,
                title="Error fatal",
                detail="No hay instalacion local.",
            )
            self.set_progress(0, "determinate", "Sin instalacion")
            self.show_toast("Instalacion no disponible", "Conecta Internet para descargar el juego.", ERROR)
            return

        self.remote_manifest = manifest
        self.set_versions(
            game_text=f"Juego instalado: {read_text_file(GAME_VERSION_PATH, 'Sin instalar')} -> remoto {manifest['game']['version']}",
            launcher_text=f"Lanzador: {LAUNCHER_VERSION} -> remoto {manifest['launcher']['version']}",
        )

        try:
            if self.maybe_update_launcher(manifest):
                state["last_launcher_update_target"] = manifest["launcher"]["version"]
                self.save_launcher_state(state)
                self.after(350, self.destroy)
                return

            installed_game_version = self.update_game_if_needed(manifest)
            self.ensure_desktop_shortcut()
            state["last_game_version"] = installed_game_version
            state["last_launcher_version"] = LAUNCHER_VERSION
            state["last_check_ok"] = True
            self.save_launcher_state(state)
        except Exception as exc:
            if not os.path.exists(GAME_EXECUTABLE_PATH):
                self.set_status(
                    chip_text="Error",
                    chip_color=ERROR,
                    title="Actualizacion fallida",
                    detail=f"No se pudo completar la descarga. {exc}",
                )
                self.set_progress(0, "determinate", "Descarga fallida")
                self.show_toast("Actualizacion fallida", "No hay binario local para continuar.", ERROR)
                return

            self.set_status(
                chip_text="Recuperado",
                chip_color=WARNING,
                title="Usando version local",
                detail="No se pudo completar la descarga remota.",
            )
            self.set_progress(1, "determinate", "Fallback local")
            self.show_toast("Usando instalacion local", "No se pudo completar la descarga remota.", WARNING)

        self.ejecutar_juego()


if __name__ == "__main__":
    app = SnakeLauncher()
    app.mainloop()
