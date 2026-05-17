#!/usr/bin/env python3
"""
Backend Flask para Music Downloader Pro
VERSIÓN 5.8 - SOLUCIÓN FINAL CON INVIDIOUS
Usa YouTube normalmente, pero si falla → Usa Invidious
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import os
import json
from pathlib import Path
from datetime import datetime
import logging
import shutil
import time

app = Flask(__name__)
CORS(app)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de directorios
BASE_DIR = os.path.join(os.path.expanduser("~"), ".music_downloader")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

# Crear directorios
try:
    Path(BASE_DIR).mkdir(parents=True, exist_ok=True)
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ Carpetas creadas: {DOWNLOAD_DIR}")
except Exception as e:
    logger.error(f"❌ Error creando carpetas: {e}")

METADATA_FILE = os.path.join(BASE_DIR, "downloads_metadata.json")

# Estado global
download_progress = {"status": "idle", "percentage": 0, "title": ""}
downloads_history = []

# Servidores Invidious gratuitos (fallback)
INVIDIOUS_SERVERS = [
    "https://invidious.jing.rocks",
    "https://invidious.nerdvpn.de",
    "https://invidious.silkky.cloud",
    "https://inv.riverside.rocks",
    "https://yt.artemislena.eu",
]


def load_downloads_history():
    """Cargar historial de descargas"""
    global downloads_history
    try:
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, 'r') as f:
                downloads_history = json.load(f)
    except:
        downloads_history = []


def save_downloads_history():
    """Guardar historial de descargas"""
    try:
        with open(METADATA_FILE, 'w') as f:
            json.dump(downloads_history, f, indent=2)
    except Exception as e:
        logger.error(f"Error guardando historial: {e}")


def progress_hook(d):
    """Hook para actualizar progreso"""
    global download_progress

    if d['status'] == 'downloading':
        if 'total_bytes' in d and d['total_bytes'] > 0:
            percentage = (d['downloaded_bytes'] / d['total_bytes']) * 100
            download_progress = {
                "status": "downloading",
                "percentage": round(percentage, 1),
                "title": d.get('_filename', 'Descargando...')
            }
            logger.info(f"Progreso: {download_progress['percentage']}%")

    elif d['status'] == 'finished':
        logger.info("Descarga completada, procesando...")
        download_progress = {
            "status": "processing",
            "percentage": 95,
            "title": "Procesando audio..."
        }


def extract_video_id(url):
    """Extraer video ID de URL de YouTube"""
    try:
        if 'youtube.com' in url:
            return url.split('v=')[1].split('&')[0]
        elif 'youtu.be' in url:
            return url.split('youtu.be/')[1].split('?')[0]
    except:
        return None
    return None


def get_invidious_url(video_id, server):
    """Construir URL de Invidious"""
    return f"{server}/watch?v={video_id}"


@app.route('/')
def home():
    """Ruta principal"""
    return jsonify({
        "status": "online",
        "message": "Music Downloader Backend funcionando",
        "version": "5.8"
    })


@app.route('/health', methods=['GET'])
def health():
    """Verificar que el servidor está funcionando"""
    try:
        space_mb = os.statvfs(TEMP_DIR).f_bavail * os.statvfs(TEMP_DIR).f_frsize // (1024 * 1024)
    except:
        space_mb = 0
    
    return jsonify({
        "status": "ok",
        "version": "5.8",
        "mode": "cloud",
        "download_dir": DOWNLOAD_DIR,
        "temp_dir": TEMP_DIR,
        "space_available_mb": space_mb
    })


def try_download_with_config(url, ydl_opts, format_type):
    """Intentar descargar con configuración específica. Retorna respuesta JSON o None."""
    global download_progress
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            title = info.get('title', 'Sin título')
            clean_title = "".join(
                c for c in title
                if c.isalnum() or c in (' ', '-', '_')
            ).strip()

            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            uploader = info.get('uploader', 'Desconocido')

            # Buscar archivo descargado
            downloaded_file = None
            for ext in [format_type, 'mp3', 'mp4', 'm4a', 'webm', 'wav']:
                potential_path = os.path.join(TEMP_DIR, f"{title}.{ext}")
                if os.path.exists(potential_path):
                    downloaded_file = potential_path
                    break

            if not downloaded_file:
                try:
                    files = sorted(
                        [os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR)],
                        key=os.path.getctime,
                        reverse=True
                    )
                    if files:
                        downloaded_file = files[0]
                except:
                    pass

            if not downloaded_file or not os.path.exists(downloaded_file):
                logger.error("Archivo no encontrado después de descarga")
                return None

            # Nombre final
            final_filename = f"{clean_title}.{format_type}"
            final_path = os.path.join(DOWNLOAD_DIR, final_filename)

            # Verificar tamaño
            file_size = os.path.getsize(downloaded_file)

            if file_size == 0:
                logger.error("Archivo vacío después de descarga")
                try:
                    os.remove(downloaded_file)
                except:
                    pass
                return None

            logger.info(f"✅ Archivo descargado: {file_size / (1024 * 1024):.2f} MB")

            # Guardar archivo
            download_progress = {
                "status": "saving",
                "percentage": 90,
                "title": "Guardando archivo..."
            }

            try:
                shutil.move(downloaded_file, final_path)
                logger.info(f"✅ Archivo guardado: {final_path}")
            except Exception as e:
                logger.error(f"Error guardando archivo: {e}")
                return None

            # Guardar en historial
            download_record = {
                "title": title,
                "filename": final_filename,
                "path": final_path,
                "size_mb": round(file_size / (1024 ** 2), 2),
                "duration": duration,
                "uploader": uploader,
                "format": format_type,
                "thumbnail": thumbnail,
                "downloaded_at": datetime.now().isoformat()
            }

            downloads_history.append(download_record)
            save_downloads_history()

            download_progress = {
                "status": "completed",
                "percentage": 100,
                "title": title
            }

            return jsonify({
                "success": True,
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "uploader": uploader,
                "format": format_type,
                "file_size_mb": round(file_size / (1024 ** 2), 2),
                "filename": final_filename,
                "local_path": final_path,
                "timestamp": datetime.now().isoformat()
            })

    except Exception as e:
        logger.warning(f"❌ Descarga fallida: {str(e)[:50]}")
        return None


@app.route('/download', methods=['POST'])
def download():
    """Descargar audio de YouTube con fallback a Invidious"""
    global download_progress

    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp3').lower()
        audio_quality = data.get('audio_quality', '192')

        # Validación
        if not url:
            return jsonify({"error": "URL no proporcionada"}), 400

        if format_type not in ['mp3', 'mp4']:
            return jsonify({"error": "Formato inválido. Usa: mp3 o mp4"}), 400

        logger.info(f"🎵 Descargando: {url}")
        download_progress = {
            "status": "starting",
            "percentage": 5,
            "title": "Analizando video..."
        }

        # Configuración base para yt-dlp
        base_ydl_opts = {
            # ====== IDENTIDAD ======
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'es-ES,es;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Referer': 'https://www.youtube.com/',
            },
            
            # ====== SALIDA Y PROGRESO ======
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': False,
            'no_warnings': False,
            
            # ====== RED ======
            'socket_timeout': 60,
            'retries': 15,
            'fragment_retries': 15,
            'skip_unavailable_fragments': True,
            'concurrent_fragment_downloads': 1,
            
            # ====== BYPASS ======
            'nocheckcertificate': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'ignoreerrors': False,
            
            # ====== YOUTUBE CONFIG ======
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_client': ['web'],
                    'lang': ['es', 'en'],
                }
            },
            
            # ====== OPCIONES ======
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': False,
            'youtube_include_dash_manifest': False,
        }

        # Configuración por formato
        if format_type == 'mp3':
            base_ydl_opts.update({
                'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': audio_quality,
                }]
            })
        else:
            base_ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }]
            })

        # INTENTAR YOUTUBE PRIMERO
        logger.info("🔄 Intentando con YouTube directo...")
        result = try_download_with_config(url, base_ydl_opts, format_type)
        
        if result:
            return result

        # SI YOUTUBE FALLA → INTENTAR CON INVIDIOUS
        logger.warning("⚠️ YouTube bloqueó. Intentando con Invidious...")
        download_progress = {
            "status": "retrying",
            "percentage": 30,
            "title": "YouTube bloqueado. Usando Invidious..."
        }

        video_id = extract_video_id(url)
        if video_id:
            for server in INVIDIOUS_SERVERS:
                try:
                    logger.info(f"🔄 Intentando Invidious en {server}...")
                    invidious_url = get_invidious_url(video_id, server)
                    
                    # Crear configuración para Invidious
                    invidious_opts = base_ydl_opts.copy()
                    invidious_opts['extractor_args'] = {}
                    
                    result = try_download_with_config(invidious_url, invidious_opts, format_type)
                    
                    if result:
                        return result
                        
                except Exception as e:
                    logger.warning(f"❌ Invidious {server} falló: {str(e)[:50]}")
                    continue

        # SI TODO FALLA
        logger.error("❌ No se pudo descargar con YouTube ni Invidious")
        download_progress = {
            "status": "error",
            "percentage": 0,
            "title": "Error al descargar"
        }
        return jsonify({
            "error": "No se pudo descargar. Intenta en 5 minutos."
        }), 500

    except Exception as e:
        logger.error(f"❌ Error crítico: {str(e)}", exc_info=True)
        download_progress = {
            "status": "error",
            "percentage": 0,
            "title": f"Error: {str(e)}"
        }
        return jsonify({
            "error": f"Error crítico: {str(e)}"
        }), 500


@app.route('/progress', methods=['GET'])
def get_progress():
    """Obtener progreso actual de descarga"""
    return jsonify(download_progress)


@app.route('/history', methods=['GET'])
def get_history():
    """Obtener historial de descargas"""
    load_downloads_history()
    return jsonify({"history": downloads_history})


@app.route('/files', methods=['GET'])
def list_files():
    """Listar archivos descargados"""
    try:
        files = []
        if os.path.exists(DOWNLOAD_DIR):
            for f in os.listdir(DOWNLOAD_DIR):
                filepath = os.path.join(DOWNLOAD_DIR, f)
                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)
                    files.append({
                        "filename": f,
                        "path": filepath,
                        "size_mb": round(size / (1024 ** 2), 2)
                    })
        return jsonify({"files": files})
    except Exception as e:
        logger.error(f"Error listando archivos: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  🎧 Music Downloader Backend v5.8 - CLOUD                  ║")
    print("║  ✅ SOLUCIÓN FINAL - YouTube + Invidious Fallback          ║")
    print("║  ✅ Múltiples servidores Invidious gratuitos               ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    load_downloads_history()

    print(f"📂 Carpeta de descargas: {DOWNLOAD_DIR}")
    print(f"🎯 Servidores Invidious: {len(INVIDIOUS_SERVERS)}")
    print()
    print("🔗 Servidor en: http://0.0.0.0:5000")
    print()
    print("═" * 62)
    print()

    # Puerto dinámico
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
