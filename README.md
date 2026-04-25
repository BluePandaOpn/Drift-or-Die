# Drift or Die

`Drift or Die` es un juego arcade de conduccion hecho con `pygame`. Este repositorio incluye el juego principal, un launcher para instalar/actualizar y una estructura basica para material visual del proyecto.

## Componentes

- Juego principal: [main.py](/c:/Users/ADMIN/Documents/coche/main.py)
- Launcher: [Launcher/Launcher.py](/c:/Users/ADMIN/Documents/coche/Launcher/Launcher.py)
- Manifiesto de distribucion: [launcher_manifest.json](/c:/Users/ADMIN/Documents/coche/launcher_manifest.json)
- Manifiesto de musica remota: [music_manifest.json](/c:/Users/ADMIN/Documents/coche/music_manifest.json)
- Binario local opcional: `bin/Drift or Die.exe`

## Mejoras aplicadas al launcher

- Corrige la deteccion del ejecutable real del juego
- Soporta el formato nuevo del manifiesto y tambien formatos anteriores
- Instala desde `bin/` si el ejecutable ya existe localmente
- Puede abrir `main.py` en modo desarrollo si no hay `.exe`
- Mantiene arranque offline cuando existe una copia local valida

La logica principal del juego no se toca. Los cambios se concentran en instalacion, actualizacion y arranque.

## Musica remota

El juego ahora puede cargar audio desde GitHub al arrancar y usarlo segun el estado del coche.

- Musica de fondo
- Sonido de aceleracion
- Sonido de derrape
- Sonido de nitro

Funcionamiento:

1. El juego intenta leer `music_manifest.json` desde GitHub.
2. Si faltan archivos, crea la carpeta local `Documents/DriftOrDie/assets/music`.
3. Descarga ahi los audios remotos y los reutiliza desde esa ubicacion.
4. Si algun archivo o el mixer falla, el juego sigue funcionando sin bloquearse.

## Estructura recomendada

```text
coche/
|- main.py
|- version.txt
|- launcher_manifest.json
|- bin/
|  \- Drift or Die.exe
|- Launcher/
|  \- Launcher.py
\- assets/
   |- logo.png
   \- demo/
      |- demo-01.png
      |- demo-02.png
      \- demo-03.png
```

## Ejecucion

### Juego en desarrollo

```powershell
python main.py
```

### Launcher en desarrollo

```powershell
python Launcher\Launcher.py
```

## Publicacion e instalacion

1. Compila el juego y deja el ejecutable en `bin/Drift or Die.exe`.
2. Actualiza `version.txt`.
3. Ajusta `launcher_manifest.json` con la nueva version y las URLs publicas.
4. Sube el repositorio o los binarios a GitHub.

## Logo e imagenes de demo

Puedes subir material grafico del juego sin tocar codigo del gameplay.

- Logo principal: `assets/logo.png`
- Imagenes o capturas de demo: `assets/demo/demo-01.png`, `assets/demo/demo-02.png`, `assets/demo/demo-03.png`

Recomendaciones:

- Usa `PNG`
- Logo cuadrado o horizontal
- Capturas a `1280x720` o superior
- Mantiene nombres estables para no romper referencias en la documentacion

## Formato recomendado de `launcher_manifest.json`

```json
{
  "game": {
    "name": "Drift or Die",
    "version": "1.0.0",
    "url": "https://github.com/USUARIO/REPO/raw/main/bin/Drift%20or%20Die.exe",
    "notes": [
      "Mejoras de arranque.",
      "Instalacion mas robusta."
    ]
  },
  "launcher": {
    "name": "Drift Or Die Hub",
    "version": "1.2.0",
    "url": "https://github.com/USUARIO/REPO/raw/main/Launcher/DriftOrDieLauncher.exe",
    "notes": [
      "Compatibilidad con manifiesto antiguo y nuevo."
    ]
  },
  "assets": {
    "logo": "assets/logo.png",
    "demo_images": [
      "assets/demo/demo-01.png",
      "assets/demo/demo-02.png"
    ]
  }
}
```

## Dependencias

- `pygame`
- `customtkinter`
- `requests`

```powershell
pip install pygame customtkinter requests
```
