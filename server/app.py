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

def _load_cookies_from_env():
    for _key in ("YOUTUBE_COOKIES", "YTDLP_COOKIES", "COOKIES"):
        _val = os.getenv(_key)
        if not _val:
            continue
        _val = _val.strip()
        if not _val:
            continue
        try:
            if os.path.isfile(_val):
                import shutil
                if os.path.abspath(_val) != os.path.abspath(COOKIE_FILE):
                    shutil.copyfile(_val, COOKIE_FILE)
                return
            looks_like_content = ("\n" in _val) or ("# Netscape" in _val) or ("# HTTP Cookie" in _val) or ("youtube.com" in _val)
            content = _val
            if not looks_like_content:
                try:
                    import base64
                    decoded = base64.b64decode(_val, validate=True).decode("utf-8", errors="ignore")
                    if "# Netscape" in decoded or "youtube.com" in decoded:
                        content = decoded
                        looks_like_content = True
                except Exception:
                    pass
            if looks_like_content or len(content) > 200:
                with open(COOKIE_FILE, "w", encoding="utf-8", newline="\n") as _cf:
                    _cf.write(content)
                return
            with open(COOKIE_FILE, "w", encoding="utf-8", newline="\n") as _cf:
                _cf.write(content)
            return
        except Exception:
            pass

_load_cookies_from_env()

def _is_bot_challenge(msg):
    m = (msg or "").lower()
    return any(s in m for s in ["sign in to confirm you’re not a bot", "sign in to confirm you're not a bot", "confirm you're not a bot", "confirm you’re not a bot", "use --cookies"])

def _has_valid_cookies():
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        if os.path.getsize(COOKIE_FILE) < 50:
            return False
        with open(COOKIE_FILE, "r", encoding="utf-8", errors="ignore") as _f:
            _txt = _f.read()
        _lines = [l for l in _txt.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not _lines:
            return False
        if "youtube.com" not in _txt and "google.com" not in _txt and "yt-dlp" not in _txt.lower():
            return False
        return True
    except Exception:
        return False

def _is_format_error(msg):
    m = (msg or "").lower()
    return "requested format is not available" in m or "format is not available" in m

def _friendly_bot_error():
    has_file = os.path.exists(COOKIE_FILE)
    has_valid = _has_valid_cookies()
    if not has_file:
        hint = "NO server/cookies.txt found and no YOUTUBE_COOKIES env var"
    elif not has_valid:
        hint = "server/cookies.txt exists but is PLACEHOLDER/invalid (only comments, no youtube.com cookies)"
    else:
        hint = "server/cookies.txt found but YouTube still blocks it (cookies expired or datacenter IP blocked)"
    return (
        "YouTube bot check failed (Sign in to confirm you’re not a bot). "
        f"YouTube is blocking datacenter IPs — {hint}. "
        "Fix: export REAL YouTube cookies (Netscape format) and provide them to the server: "
        "1) Install 'Get cookies.txt LOCALLY' extension, open youtube.com logged-in, Export -> paste content into server/cookies.txt (replace placeholder), "
        "OR 2) set env var YOUTUBE_COOKIES to the FULL file content (or base64) on your host (Render/Railway/etc), "
        "then redeploy + ensure yt-dlp is latest: pip install -U yt-dlp. "
        "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
    )

def _inject_cookies(opts):
    _load_cookies_from_env()
    if _has_valid_cookies():
        opts["cookiefile"] = COOKIE_FILE
    return opts

def _base_opts():
    return {
        "proxy": "http://qhmqqrbn:a6sflac3xvep@31.59.20.176:6754/",
        "geo_bypass": True,
        "retries": 2,
        "socket_timeout": 30,
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "mweb", "android"],
                "player_skip": ["webpage"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
        },
    }

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

_active_downloads = {}
_download_lock = threading.Lock()


def _safe_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def _extract_info(url):
    base = _base_opts()
    base.update({"skip_download": True})
    ydl_opts = _inject_cookies(base)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        if _is_bot_challenge(str(e)):
            raise RuntimeError(_friendly_bot_error()) from e
        raise
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
        base_common = _base_opts()
        base_common.update({"outtmpl": tmpl, "progress_hooks": [hook]})
        info = None
        filename = ""
        last_err = None
        if mode == "audio":
            base_common.update({
                "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            })
            ydl_opts = _inject_cookies(dict(base_common))
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
            except Exception as e:
                if _is_bot_challenge(str(e)):
                    raise RuntimeError(_friendly_bot_error()) from e
                raise
        else:
            q = str(quality or "best").strip().lower().replace("p", "")
            if q != "best" and q.isdigit():
                fmts = [
                    f"bestvideo[height<={q}]+bestaudio/best[height<={q}]/best",
                    "bestvideo+bestaudio/best",
                    "best",
                ]
            else:
                fmts = ["bestvideo+bestaudio/best", "best"]
            for fmt in fmts:
                try:
                    cur = dict(base_common)
                    cur.update({"format": fmt, "merge_output_format": "mp4"})
                    ydl_opts = _inject_cookies(cur)
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        filename = ydl.prepare_filename(info)
                    last_err = None
                    break
                except Exception as e:
                    if _is_bot_challenge(str(e)):
                        raise RuntimeError(_friendly_bot_error()) from e
                    if _is_format_error(str(e)):
                        last_err = e
                        if fmt != fmts[-1]:
                            continue
                        try:
                            fallback_opts = {"outtmpl": tmpl, "quiet": True, "no_warnings": True, "noplaylist": True, "format": "best", "progress_hooks": [hook]}
                            fallback_opts = _inject_cookies(fallback_opts)
                            with yt_dlp.YoutubeDL(fallback_opts) as ydl2:
                                info = ydl2.extract_info(url, download=True)
                                filename = ydl2.prepare_filename(info)
                            last_err = None
                            break
                        except Exception as e2:
                            if _is_bot_challenge(str(e2)):
                                raise RuntimeError(_friendly_bot_error()) from e2
                            raise e2
                    raise
            if last_err is not None and info is None:
                raise last_err
        try:
            info_title = info.get("title", "") if isinstance(info, dict) else ""
        except Exception:
            info_title = ""
        if mode == "audio":
            base_p = os.path.splitext(filename)[0]
            mp3 = base_p + ".mp3"
            if os.path.exists(mp3):
                filename = mp3
        else:
            if filename and not os.path.exists(filename):
                cand = globmod.glob(os.path.join(DOWNLOAD_DIR, _safe_filename(info_title) + ".*"))
                if cand:
                    filename = cand[0]
        fname = os.path.basename(filename) if filename else ""
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