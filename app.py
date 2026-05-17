#!/usr/bin/env python3
"""
Backend Flask para Music Downloader Pro
VERSIÓN 5.9 - ESTRATEGIA ALTERNATIVA DIRECTA
Descarga sin usar extractores de YouTube
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

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.expanduser("~"), ".music_downloader")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
TEMP_DIR = os.path.join(BASE_DIR, "temp")

try:
    Path(BASE_DIR).mkdir(parents=True, exist_ok=True)
    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ Carpetas creadas: {DOWNLOAD_DIR}")
except Exception as e:
    logger.error(f"❌ Error: {e}")

METADATA_FILE = os.path.join(BASE_DIR, "downloads_metadata.json")
download_progress = {"status": "idle", "percentage": 0, "title": ""}
downloads_history = []


def load_downloads_history():
    global downloads_history
    try:
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, 'r') as f:
                downloads_history = json.load(f)
    except:
        downloads_history = []


def save_downloads_history():
    try:
        with open(METADATA_FILE, 'w') as f:
            json.dump(downloads_history, f, indent=2)
    except Exception as e:
        logger.error(f"Error guardando historial: {e}")


def progress_hook(d):
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
        logger.info("Descarga completada")
        download_progress = {
            "status": "processing",
            "percentage": 95,
            "title": "Procesando audio..."
        }


@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "version": "5.9",
        "message": "Music Downloader Backend"
    })


@app.route('/health', methods=['GET'])
def health():
    try:
        space_mb = os.statvfs(TEMP_DIR).f_bavail * os.statvfs(TEMP_DIR).f_frsize // (1024 * 1024)
    except:
        space_mb = 0
    
    return jsonify({
        "status": "ok",
        "version": "5.9",
        "space_mb": space_mb
    })


@app.route('/download', methods=['POST'])
def download():
    global download_progress

    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_type = data.get('format', 'mp3').lower()
        audio_quality = data.get('audio_quality', '192')

        if not url:
            return jsonify({"error": "URL no proporcionada"}), 400

        if format_type not in ['mp3', 'mp4']:
            return jsonify({"error": "Formato inválido"}), 400

        logger.info(f"🎵 Descargando: {url}")
        download_progress = {
            "status": "starting",
            "percentage": 5,
            "title": "Analizando..."
        }

        # v5.9: Configuración SIMPLIFICADA y DIRECTA
        ydl_opts = {
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': False,
            'no_warnings': False,
            
            # Headers simples pero efectivos
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            },
            
            # Red
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            
            # Opciones de descarga
            'noplaylist': True,
            'quiet': False,
            'no_warnings': False,
            
            # IMPORTANTE: Ignorar errores y continuar
            'ignoreerrors': True,
            'skip': ['dash'],
        }

        if format_type == 'mp3':
            ydl_opts.update({
                'format': 'best[ext=m4a]/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            })
        else:
            ydl_opts.update({
                'format': 'best',
            })

        # Intentar descarga
        logger.info("🔄 Intentando descarga...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            title = info.get('title', 'Sin título')
            clean_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()

            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            uploader = info.get('uploader', 'Desconocido')

            # Buscar archivo
            downloaded_file = None
            for ext in [format_type, 'mp3', 'mp4', 'm4a', 'webm', 'wav', 'mkv']:
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
                return jsonify({"error": "Archivo no encontrado"}), 500

            final_filename = f"{clean_title}.{format_type}"
            final_path = os.path.join(DOWNLOAD_DIR, final_filename)

            file_size = os.path.getsize(downloaded_file)
            if file_size == 0:
                try:
                    os.remove(downloaded_file)
                except:
                    pass
                return jsonify({"error": "Archivo vacío"}), 500

            logger.info(f"✅ Descargado: {file_size / (1024 * 1024):.2f} MB")

            download_progress = {
                "status": "saving",
                "percentage": 90,
                "title": "Guardando..."
            }

            try:
                shutil.move(downloaded_file, final_path)
                logger.info(f"✅ Guardado: {final_path}")
            except Exception as e:
                logger.error(f"Error: {e}")
                return jsonify({"error": f"Error: {str(e)}"}), 500

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
            "title": f"Error: {str(e)}"
        }
        return jsonify({
            "error": f"Error: {str(e)}"
        }), 500


@app.route('/progress', methods=['GET'])
def get_progress():
    return jsonify(download_progress)


@app.route('/history', methods=['GET'])
def get_history():
    load_downloads_history()
    return jsonify({"history": downloads_history})


@app.route('/files', methods=['GET'])
def list_files():
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
    print("║  🎧 Music Downloader Backend v5.9                          ║")
    print("║  ✅ Estrategia directa simplificada                        ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()

    load_downloads_history()

    print(f"📂 Carpeta: {DOWNLOAD_DIR}")
    print(f"🔗 Puerto: 5000")
    print()

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
