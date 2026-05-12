#!/usr/bin/env python3
"""
Backend Flask para Music Downloader Pro
Usa yt-dlp para descargas (versión Replit)
VERSIÓN 5.1 - Optimizado para despliegue en Replit/Railway/Render
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
import subprocess
import time

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "message": "Music Downloader Backend funcionando",
        "version": "5.1"
    })

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de directorios para servidor en nube
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

# Para guardar metadatos de descargas
METADATA_FILE = os.path.join(BASE_DIR, "downloads_metadata.json")

# Estado global
download_progress = {"status": "idle", "percentage": 0, "title": ""}
downloads_history = []


def load_downloads_history():
    """Cargar historial de descargas de archivo JSON"""
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

        logger.info(f"Progreso: {download_progress}")

    elif d['status'] == 'finished':
        logger.info("Descarga completada")
        download_progress = {
            "status": "processing",
            "percentage": 95,
            "title": "Procesando audio..."
        }


@app.route('/health', methods=['GET'])
def health():
    """Verificar que el servidor está funcionando"""
    return jsonify({
        "status": "ok",
        "version": "5.1",
        "mode": "cloud",
        "download_dir": DOWNLOAD_DIR,
        "temp_dir": TEMP_DIR,
        "space_available_mb": os.statvfs(TEMP_DIR).f_bavail * os.statvfs(TEMP_DIR).f_frsize // (1024 * 1024)
    })


@app.route('/download', methods=['POST'])
def download():
    """Descargar audio de YouTube"""
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

        logger.info(f"Descargando: {url}")

        download_progress = {
            "status": "starting",
            "percentage": 5,
            "title": "Analizando video..."
        }

        # Configuración yt-dlp
        ydl_opts = {
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'cookiefile': os.path.join(os.getcwd(), 'cookies.txt'),
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [progress_hook],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'geo_bypass': True,
            'noplaylist': True,
        }

        # MP3
        if format_type == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': audio_quality,
                }]
            })

        # MP4
        else:
            ydl_opts.update({
                'format': 'best',
                'noplaylist': True
            })
        # Descargar
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
                logger.error("Archivo no encontrado")
                return jsonify({
                    "error": "Archivo no encontrado después de descarga"
                }), 500

            # Nombre final
            final_filename = f"{clean_title}.{format_type}"
            final_path = os.path.join(DOWNLOAD_DIR, final_filename)

            # Verificar tamaño
            file_size = os.path.getsize(downloaded_file)

            if file_size == 0:
                logger.error("Archivo vacío")
                os.remove(downloaded_file)

                return jsonify({
                    "error": "El archivo está vacío"
                }), 500

            logger.info(f"✅ Archivo descargado: {file_size / (1024 * 1024):.2f} MB")

            # Guardar archivo
            download_progress = {
                "status": "saving",
                "percentage": 90,
                "title": "Guardando archivo..."
            }

            try:
                shutil.move(downloaded_file, final_path)
                logger.info(f"✅ Archivo movido a: {final_path}")

            except Exception as e:
                logger.error(f"Error moviendo archivo: {e}")

                return jsonify({
                    "error": f"Error al guardar: {str(e)}"
                }), 500

            # Historial
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
        logger.error(f"❌ Error: {str(e)}", exc_info=True)

        download_progress = {
            "status": "error",
            "percentage": 0,
            "title": str(e)
        }

        return jsonify({
            "error": f"Error: {str(e)}"
        }), 500


@app.route('/progress', methods=['GET'])
def get_progress():
    """Obtener progreso actual"""
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
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':

    print("╔════════════════════════════════════════════════════════════╗")
    print("║  🎧 Music Downloader Backend v5.1 - CLOUD                ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    load_downloads_history()

    print(f"📂 Carpeta de descargas: {DOWNLOAD_DIR}")
    print(f"📂 Carpeta temporal: {TEMP_DIR}")
    print()

    print("🔗 Servidor en: http://0.0.0.0:5000")
    print()

    print("═" * 62)
    print()

    # Puerto dinámico Render/Railway/Replit
    port = int(os.environ.get('PORT', 5000))

    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )
