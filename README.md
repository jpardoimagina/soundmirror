# SoundMirror - Tidal-Serato Sync

Herramienta de sincronización bidireccional entre crates de Serato y playlists de Tidal, con recuperación automática de archivos faltantes.

## Características

- 🔄 **Sincronización Bidireccional**: Sincroniza tus crates de Serato con playlists de Tidal
- 📥 **Recuperación de Archivos**: Descarga automáticamente canciones faltantes desde Tidal usando `tidal-dl-ng`
- 🎵 **Filtro de Calidad**: Sincroniza solo canciones por debajo de un bitrate específico
- 📊 **Base de Datos SQLite**: Mapeo persistente entre archivos locales y tracks de Tidal
- 🎛️ **Gestión de Carpetas**: Organiza tus playlists en carpetas de Tidal

## Instalación

```bash
pip install -e .
```

Esto instalará el paquete y creará el comando `soundmirror` en tu PATH.

### Instalación de tidal-dl-ng

Después de instalar el paquete, necesitas instalar `tidal-dl-ng` manualmente en un entorno Python 3.12+:

```bash
# Si usas pyenv, crea o activa un entorno Python 3.12+
pyenv virtualenv 3.12.11 musica
pyenv activate musica

# Instala tidal-dl-ng
pip install tidal-dl-ng
```

El sistema está configurado para usar automáticamente el binario de `tidal-dl-ng` desde el entorno `musica`.

## Uso

### Descubrir Crates

```bash
soundmirror discover
```

### Listar Crates Registrados

```bash
soundmirror list
```

### Activar un Crate para Sincronización

```bash
soundmirror add [ÍNDICE] --name "Nombre de la Playlist"
```

### Sincronizar

```bash
# Sincronización completa
soundmirror sync

# Solo canciones con bitrate ≤ 192kbps
soundmirror sync --max-bitrate 192
```

### Recuperar Archivos Faltantes

```bash
# Descarga con calidad LOSSLESS (por defecto)
soundmirror recover

# Descarga con calidad específica
soundmirror recover --quality HI_RES_LOSSLESS

# Modo dry-run (solo muestra lo que se descargaría)
soundmirror recover --dry
```

#### Opciones de Calidad

- `LOW` (96kbps)
- `NORMAL` (320kbps)
- `HIGH`
- `LOSSLESS` (CD Quality - Por defecto)
- `HI_RES_LOSSLESS` (Máxima calidad disponible)

## Requisitos

- Python 3.11+
- Cuenta de Tidal HiFi
- ffprobe (para análisis de bitrate)

## Licencia

MIT
