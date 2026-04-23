import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "Drift or Die Launcher"
GAME_NAME = "Drift or Die"
LAUNCHER_VERSION = "2.0.0"

WINDOW_WIDTH = 920
WINDOW_HEIGHT = 620

PRIMARY = "#f97316"
PRIMARY_ALT = "#fb923c"
SURFACE = "#121826"
CARD = "#1b2436"
CARD_ALT = "#24324b"
TEXT = "#f8fafc"
TEXT_SOFT = "#94a3b8"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
ERROR = "#ef4444"

ROOT_DIR = Path(__file__).resolve().parent
USER_HOME = Path.home()
INSTALL_ROOT = USER_HOME / "Documents" / "DriftOrDie"
INSTALL_GAME_DIR = INSTALL_ROOT / "Game"
INSTALL_LAUNCHER_DIR = INSTALL_ROOT / "Launcher"
STATE_FILE = INSTALL_LAUNCHER_DIR / "launcher_state.json"

SOURCE_MAIN = ROOT_DIR / "main.py"
SOURCE_VERSION = ROOT_DIR / "version.txt"
SOURCE_README = ROOT_DIR / "README.md"
LOCAL_MANIFEST = ROOT_DIR / "launcher_manifest.json"

INSTALL_MAIN = INSTALL_GAME_DIR / "main.py"
INSTALL_VERSION = INSTALL_GAME_DIR / "version.txt"
INSTALL_MANIFEST = INSTALL_GAME_DIR / "launcher_manifest.json"

RUNTIME_DIRS = ("bin", "assets", "data", "audio", "fonts", "maps")
RUNTIME_FILES = ("main.py", "version.txt", "README.md", "launcher_manifest.json")


@dataclass
class LaunchTarget:
    path: Path
    mode: str
    working_directory: Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


def parse_version(value: str) -> tuple[int, int, int]:
    parts = []
    number = ""
    for char in value:
        if char.isdigit():
            number += char
        elif number:
            parts.append(int(number))
            number = ""
    if number:
        parts.append(int(number))
    parts = (parts + [0, 0, 0])[:3]
    return tuple(parts)


def write_json(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def copy_file(source: Path, destination: Path) -> None:
    ensure_dir(destination.parent)
    temp_destination = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, temp_destination)
    os.replace(temp_destination, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def detect_python() -> str | None:
    return sys.executable if Path(sys.executable).exists() else None


def has_pygame() -> bool:
    try:
        import pygame  # noqa: F401
    except Exception:
        return False
    return True


def load_manifest() -> dict:
    for candidate in (LOCAL_MANIFEST, INSTALL_MANIFEST):
        data = read_json(candidate)
        if data:
            return data
    return {}


def build_manifest_notes() -> list[str]:
    manifest = load_manifest()
    notes = manifest.get("notes", [])
    if isinstance(notes, list):
        return [str(note) for note in notes[:4]]
    return []


def detect_launch_target() -> LaunchTarget | None:
    exe_candidates = [
        INSTALL_GAME_DIR / "DriftOrDie.exe",
        INSTALL_GAME_DIR / "bin" / "DriftOrDie.exe",
        ROOT_DIR / "bin" / "DriftOrDie.exe",
        ROOT_DIR / "DriftOrDie.exe",
    ]
    for candidate in exe_candidates:
        if candidate.is_file():
            return LaunchTarget(candidate, "exe", candidate.parent)

    py_candidates = [
        INSTALL_MAIN,
        SOURCE_MAIN,
    ]
    python_path = detect_python()
    if python_path:
        for candidate in py_candidates:
            if candidate.is_file():
                return LaunchTarget(candidate, "python", candidate.parent)

    return None


def install_local_build() -> tuple[str, str]:
    ensure_dir(INSTALL_ROOT)
    ensure_dir(INSTALL_GAME_DIR)
    ensure_dir(INSTALL_LAUNCHER_DIR)

    copied_items = []
    for file_name in RUNTIME_FILES:
        source = ROOT_DIR / file_name
        if source.is_file():
            copy_file(source, INSTALL_GAME_DIR / file_name)
            copied_items.append(file_name)

    for dir_name in RUNTIME_DIRS:
        source_dir = ROOT_DIR / dir_name
        if source_dir.is_dir():
            copy_tree(source_dir, INSTALL_GAME_DIR / dir_name)
            copied_items.append(dir_name)

    version = read_text(SOURCE_VERSION, "0.0.0")
    if not copied_items:
        raise FileNotFoundError("No se encontraron archivos del juego para instalar.")

    return version, ", ".join(copied_items)


class DriftLauncher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry(self._center_geometry(WINDOW_WIDTH, WINDOW_HEIGHT))
        self.minsize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.configure(bg=SURFACE)

        self.state_data = read_json(STATE_FILE)
        self.notes = build_manifest_notes()
        self.launch_target: LaunchTarget | None = None
        self.ready_to_play = False

        self.status_var = tk.StringVar(value="Preparando launcher...")
        self.detail_var = tk.StringVar(value="Analizando instalacion local y archivos del juego.")
        self.version_var = tk.StringVar(value="Versiones: comprobando...")
        self.path_var = tk.StringVar(value="Destino de arranque: comprobando...")
        self.install_var = tk.StringVar(value=f"Instalacion: {INSTALL_GAME_DIR}")
        self.notes_var = tk.StringVar(value="Notas: cargando...")

        self._build_ui()
        self._set_busy(True)
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _center_geometry(self, width: int, height: int) -> str:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        shell = tk.Frame(self, bg=SURFACE)
        shell.grid(sticky="nsew")
        shell.columnconfigure(0, weight=5)
        shell.columnconfigure(1, weight=4)
        shell.rowconfigure(0, weight=1)

        left = tk.Frame(shell, bg=SURFACE, padx=28, pady=28)
        left.grid(row=0, column=0, sticky="nsew")

        right = tk.Frame(shell, bg="#101522", padx=24, pady=24)
        right.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            left,
            text=GAME_NAME,
            font=("Segoe UI Semibold", 28),
            fg=TEXT,
            bg=SURFACE,
        ).pack(anchor="w")

        tk.Label(
            left,
            text="Launcher completo para instalar, reparar y arrancar el juego.",
            font=("Segoe UI", 12),
            fg=TEXT_SOFT,
            bg=SURFACE,
        ).pack(anchor="w", pady=(6, 20))

        hero = tk.Frame(left, bg=CARD, padx=22, pady=22, highlightbackground=CARD_ALT, highlightthickness=1)
        hero.pack(fill="x")

        tk.Label(
            hero,
            textvariable=self.status_var,
            font=("Segoe UI Semibold", 19),
            fg=TEXT,
            bg=CARD,
        ).pack(anchor="w")

        tk.Label(
            hero,
            textvariable=self.detail_var,
            font=("Segoe UI", 11),
            fg=TEXT_SOFT,
            bg=CARD,
            justify="left",
            wraplength=440,
        ).pack(anchor="w", pady=(10, 16))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Launcher.Horizontal.TProgressbar",
            troughcolor=CARD_ALT,
            background=PRIMARY,
            bordercolor=CARD_ALT,
            lightcolor=PRIMARY,
            darkcolor=PRIMARY,
        )

        self.progress = ttk.Progressbar(hero, style="Launcher.Horizontal.TProgressbar", mode="indeterminate")
        self.progress.pack(fill="x")

        info = tk.Frame(left, bg=SURFACE)
        info.pack(fill="x", pady=(20, 18))
        info.columnconfigure(0, weight=1)
        info.columnconfigure(1, weight=1)

        self._make_card(info, "Versiones", self.version_var).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._make_card(info, "Arranque", self.path_var).grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._make_card(info, "Instalacion", self.install_var).grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(16, 0))
        self._make_card(info, "Notas", self.notes_var).grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(16, 0))

        buttons = tk.Frame(left, bg=SURFACE)
        buttons.pack(fill="x", pady=(4, 0))
        buttons.columnconfigure((0, 1), weight=1)

        self.play_button = self._make_button(buttons, "Jugar", PRIMARY, self.launch_game)
        self.play_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.repair_button = self._make_button(buttons, "Reparar / Reinstalar", CARD_ALT, self.repair_install)
        self.repair_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.open_button = self._make_button(buttons, "Abrir carpeta", CARD_ALT, self.open_install_folder)
        self.open_button.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(14, 0))

        self.exit_button = self._make_button(buttons, "Cerrar", "#334155", self.destroy)
        self.exit_button.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(14, 0))

        tk.Label(
            right,
            text="Estado del sistema",
            font=("Segoe UI Semibold", 18),
            fg=TEXT,
            bg="#101522",
        ).pack(anchor="w")

        self.system_box = tk.Text(
            right,
            height=18,
            bg="#101522",
            fg=TEXT_SOFT,
            relief="flat",
            borderwidth=0,
            insertbackground=TEXT,
            font=("Consolas", 10),
            wrap="word",
            padx=0,
            pady=12,
        )
        self.system_box.pack(fill="both", expand=True)
        self.system_box.configure(state="disabled")

        footer = tk.Label(
            right,
            text=f"Launcher {LAUNCHER_VERSION}",
            font=("Segoe UI", 10),
            fg=TEXT_SOFT,
            bg="#101522",
        )
        footer.pack(anchor="w", pady=(12, 0))

    def _make_card(self, parent: tk.Widget, title: str, variable: tk.StringVar) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD, padx=16, pady=16, highlightbackground=CARD_ALT, highlightthickness=1)
        tk.Label(
            frame,
            text=title,
            font=("Segoe UI Semibold", 11),
            fg=PRIMARY_ALT,
            bg=CARD,
        ).pack(anchor="w")
        tk.Label(
            frame,
            textvariable=variable,
            font=("Segoe UI", 10),
            fg=TEXT,
            bg=CARD,
            justify="left",
            wraplength=270,
        ).pack(anchor="w", pady=(8, 0))
        return frame

    def _make_button(self, parent: tk.Widget, label: str, background: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=label,
            font=("Segoe UI Semibold", 11),
            bg=background,
            fg=TEXT,
            activebackground=PRIMARY_ALT,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=14,
            pady=14,
            command=command,
            cursor="hand2",
        )

    def _ui(self, fn, *args) -> None:
        self.after(0, lambda: fn(*args))

    def _append_log(self, message: str) -> None:
        def update() -> None:
            self.system_box.configure(state="normal")
            self.system_box.insert("end", f"{message}\n")
            self.system_box.see("end")
            self.system_box.configure(state="disabled")

        self._ui(update)

    def _set_busy(self, busy: bool) -> None:
        def update() -> None:
            if busy:
                self.progress.start(12)
            else:
                self.progress.stop()

            state = "disabled" if busy else "normal"
            self.repair_button.configure(state=state)
            self.open_button.configure(state="normal")
            self.play_button.configure(state="normal" if self.ready_to_play and not busy else "disabled")

        self._ui(update)

    def _set_status(self, title: str, detail: str, color: str | None = None) -> None:
        def update() -> None:
            self.status_var.set(title)
            self.detail_var.set(detail)
            if color:
                self.play_button.configure(activebackground=color)

        self._ui(update)

    def _refresh_runtime_info(self) -> None:
        source_version = read_text(SOURCE_VERSION, "No disponible")
        installed_version = read_text(INSTALL_VERSION, "No instalado")
        target = detect_launch_target()
        self.launch_target = target
        self.ready_to_play = target is not None

        runtime_name = "Sin objetivo detectado"
        if target:
            runtime_name = f"{target.mode.upper()} | {target.path}"

        notes = self.notes or [
            "Instala o actualiza desde los archivos locales del proyecto.",
            "Si existe un .exe empaquetado se usa primero.",
            "Si no, el launcher arranca main.py con tu Python actual.",
        ]

        self._ui(self.version_var.set, f"Juego local: {source_version}\nJuego instalado: {installed_version}")
        self._ui(self.path_var.set, runtime_name)
        self._ui(self.notes_var.set, "\n".join(f"- {note}" for note in notes))
        self._ui(self.install_var.set, str(INSTALL_GAME_DIR))
        self._set_busy(False)

    def _bootstrap(self) -> None:
        ensure_dir(INSTALL_ROOT)
        ensure_dir(INSTALL_GAME_DIR)
        ensure_dir(INSTALL_LAUNCHER_DIR)

        self._append_log(f"Launcher root: {ROOT_DIR}")
        self._append_log(f"Install dir: {INSTALL_GAME_DIR}")

        if not SOURCE_MAIN.exists():
            self._set_status("Falta el juego", "No se encontro main.py en el proyecto actual.", ERROR)
            self._append_log("Error: main.py no existe en la raiz del proyecto.")
            self._refresh_runtime_info()
            return

        source_version = read_text(SOURCE_VERSION, "0.0.0")
        installed_version = read_text(INSTALL_VERSION, "0.0.0")
        self._append_log(f"Version fuente: {source_version}")
        self._append_log(f"Version instalada: {installed_version}")

        if parse_version(installed_version) < parse_version(source_version) or not INSTALL_MAIN.exists():
            self._set_status("Instalando juego", "Copiando la build local a la carpeta de instalacion...", PRIMARY)
            try:
                version, copied_items = install_local_build()
                self._append_log(f"Instalacion completada: {copied_items}")
                self._append_log(f"Version instalada ahora: {version}")
                self.state_data["last_installed_version"] = version
                write_json(STATE_FILE, self.state_data)
            except Exception as exc:
                self._set_status("Instalacion fallida", f"No se pudo copiar el juego: {exc}", ERROR)
                self._append_log(f"Error de instalacion: {exc}")
                self._refresh_runtime_info()
                return
        else:
            self._append_log("La instalacion ya estaba al dia.")

        if not has_pygame() and detect_launch_target() and detect_launch_target().mode == "python":
            self._append_log("Aviso: pygame no parece estar instalado en este Python.")
            self._set_status(
                "Dependencia pendiente",
                "El launcher esta listo, pero para arrancar main.py necesitas pygame instalado.",
                WARNING,
            )
        else:
            self._set_status("Launcher listo", "Juego instalado y preparado para arrancar.", SUCCESS)

        self._refresh_runtime_info()

    def repair_install(self) -> None:
        self._set_busy(True)
        self._set_status("Reparando instalacion", "Reinstalando archivos del juego desde el proyecto actual...", PRIMARY)
        threading.Thread(target=self._repair_install_worker, daemon=True).start()

    def _repair_install_worker(self) -> None:
        try:
            version, copied_items = install_local_build()
            self._append_log(f"Reparacion completada: {copied_items}")
            self.state_data["last_repair_version"] = version
            write_json(STATE_FILE, self.state_data)
            self._set_status("Reparacion completada", f"Juego reinstalado correctamente: {version}", SUCCESS)
        except Exception as exc:
            self._append_log(f"Error en reparacion: {exc}")
            self._set_status("Reparacion fallida", str(exc), ERROR)
        self._refresh_runtime_info()

    def open_install_folder(self) -> None:
        ensure_dir(INSTALL_GAME_DIR)
        try:
            os.startfile(INSTALL_GAME_DIR)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"No se pudo abrir la carpeta:\n{exc}")

    def launch_game(self) -> None:
        self.launch_target = detect_launch_target()
        if not self.launch_target:
            messagebox.showerror(APP_NAME, "No se encontro ningun ejecutable ni main.py para iniciar el juego.")
            return

        if self.launch_target.mode == "python" and not has_pygame():
            messagebox.showwarning(
                APP_NAME,
                "No se detecto pygame en este Python. Instala la dependencia antes de arrancar el juego.",
            )
            return

        try:
            if self.launch_target.mode == "exe":
                subprocess.Popen([str(self.launch_target.path)], cwd=self.launch_target.working_directory)
            else:
                subprocess.Popen(
                    [sys.executable, str(self.launch_target.path)],
                    cwd=self.launch_target.working_directory,
                )
            self._append_log(f"Juego iniciado desde: {self.launch_target.path}")
            self.state_data["last_launch_target"] = str(self.launch_target.path)
            write_json(STATE_FILE, self.state_data)
            self.destroy()
        except Exception as exc:
            self._append_log(f"Error al iniciar el juego: {exc}")
            messagebox.showerror(APP_NAME, f"No se pudo iniciar el juego:\n{exc}")


if __name__ == "__main__":
    app = DriftLauncher()
    app.mainloop()
