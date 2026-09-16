import os
import re
import uuid
import threading
import glob as globmod
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

COOKIE_FILE = os.path.join(BASE_DIR, "cookies.txt")
if os.getenv("YOUTUBE_COOKIES") and not os.path.exists(COOKIE_FILE):
    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as _cf:
            _cf.write(os.getenv("YOUTUBE_COOKIES"))
    except Exception:
        pass


def _inject_cookies(opts):
    if os.path.exists(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE
    return opts

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

_active_downloads = {}
_download_lock = threading.Lock()


def _safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _extract_info(url):
ydl_opts = _inject_cookies({
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios"]
            }
        }
    })
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if "entries" in info:
            info = next(iter(info["entries"]), info)
        formats = []
        seen = set()
        for f in info.get("formats") or []:
            height = f.get("height")
            ext = f.get("ext")
            fid = f.get("format_id")
            if height and ext in ("mp4", "webm", "mov") and height not in seen:
                seen.add(height)
                formats.append({
                    "format_id": fid,
                    "height": height,
                    "ext": ext,
                    "filesize": f.get("filesize") or f.get("filesize_approx"),
                    "label": f"{height}p",
                })
        formats.sort(key=lambda x: x["height"], reverse=True)
        if not formats:
            formats = [{"format_id": "best", "height": 0, "ext": "mp4", "label": "Best"}]
        return {
            "url": url,
            "title": info.get("title") or "Untitled",
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "extractor": info.get("extractor_key"),
            "formats": formats,
        }


def _download_task(task_id, url, quality, mode):
    try:
        with _download_lock:
            _active_downloads[task_id]["status"] = "downloading"
            _active_downloads[task_id]["progress"] = 0

        def hook(d):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = int(downloaded * 100 / total) if total else 0
                with _download_lock:
                    _active_downloads[task_id]["progress"] = pct
            elif d.get("status") == "finished":
                with _download_lock:
                    _active_downloads[task_id]["progress"] = 100

        tmpl = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
        if mode == "audio":
            ydl_opts = _inject_cookies({
                "format": "bestaudio/best",
                "outtmpl": tmpl,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "extractor_args": {
    "youtube": {
        "player_client": ["android", "ios"]
    }
}
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                "progress_hooks": [hook],
            })
        else:
            if quality and quality != "best" and str(quality).isdigit():
                fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
            else:
                fmt = "bestvideo+bestaudio/best"
            ydl_opts = _inject_cookies({
                "format": fmt,
                "outtmpl": tmpl,
                "quiet": True,
                "no_warnings": True,
                "extractor_args": {
    "youtube": {
        "player_client": ["android", "ios"]
    }
}
                "noplaylist": True,
                "merge_output_format": "mp4",
                "progress_hooks": [hook],
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if mode == "audio":
                base = os.path.splitext(filename)[0]
                mp3 = base + ".mp3"
                if os.path.exists(mp3):
                    filename = mp3
            else:
                if not os.path.exists(filename):
                    cand = globmod.glob(os.path.join(DOWNLOAD_DIR, _safe_filename(info.get("title", "")) + ".*"))
                    if cand:
                        filename = cand[0]
            fname = os.path.basename(filename)
            with _download_lock:
                _active_downloads[task_id]["status"] = "completed"
                _active_downloads[task_id]["filename"] = fname
                _active_downloads[task_id]["progress"] = 100
    except Exception as e:
        with _download_lock:
            _active_downloads[task_id]["status"] = "error"
            _active_downloads[task_id]["error"] = str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True) or {}
    urls = data.get("urls") or ([data.get("url")] if data.get("url") else [])
    if isinstance(urls, str):
        urls = [urls]
    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
    results = []
    for url in urls:
        try:
            info = _extract_info(url)
            results.append({**info, "status": "ok"})
        except Exception as e:
            results.append({"url": url, "status": "error", "error": str(e)})
    return jsonify({"results": results})


def _start_download(url, quality, mode):
    task_id = uuid.uuid4().hex[:12]
    with _download_lock:
        _active_downloads[task_id] = {"status": "queued", "progress": 0, "url": url, "mode": mode, "quality": quality}
    t = threading.Thread(target=_download_task, args=(task_id, url, quality, mode), daemon=True)
    t.start()
    return task_id


@app.route("/api/download/video", methods=["POST"])
def download_video():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    quality = str(data.get("quality") or "best")
    task_id = _start_download(url, quality, "video")
    return jsonify({"task_id": task_id})


@app.route("/api/download/audio", methods=["POST"])
def download_audio():
    data = request.get_json(force=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    task_id = _start_download(url, "best", "audio")
    return jsonify({"task_id": task_id})


@app.route("/api/download/all", methods=["POST"])
def download_all():
    data = request.get_json(force=True) or {}
    urls = data.get("urls") or []
    if isinstance(urls, str):
        urls = [urls]
    urls = [u.strip() for u in urls if u and u.strip()]
    if not urls:
        return jsonify({"error": "urls required"}), 400
    quality = str(data.get("quality") or "best")
    mode = data.get("mode") or "video"
    if mode not in ("video", "audio"):
        mode = "video"
    task_ids = []
    for url in urls:
        q = quality if mode == "video" else "best"
        task_ids.append({"url": url, "task_id": _start_download(url, q, mode)})
    return jsonify({"tasks": task_ids})


@app.route("/api/download/status/<task_id>")
def download_status(task_id):
    with _download_lock:
        info = _active_downloads.get(task_id)
        if not info:
            return jsonify({"error": "task not found"}), 404
        return jsonify({"task_id": task_id, **info})


@app.route("/api/downloads")
def list_downloads():
    files = []
    for f in os.listdir(DOWNLOAD_DIR):
        fp = os.path.join(DOWNLOAD_DIR, f)
        if os.path.isfile(fp):
            files.append({"filename": f, "size": os.path.getsize(fp)})
    files.sort(key=lambda x: x["filename"])
    return jsonify({"files": files})


@app.route("/api/downloads/<path:filename>")
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)