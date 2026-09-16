# Paste link Get video

Paste a link, get your video — simple, fast media downloader.

## Features
- Paste any supported URL → analyze & preview
- Download as **Video (MP4)** or **Audio (MP3)**
- Quality selection, batch links, polling progress
- Flask + yt-dlp backend, vanilla JS frontend

## Quick Start

### Backend (Flask)
```bash
cd server
pip install -r requirements.txt
python app.py
# http://localhost:5000
```
Requires `ffmpeg` for MP3 extraction.

Or with Docker:
```bash
cd server
docker compose up
# or
docker build -t paste-link-get-video . && docker run -p 5000:5000 -v ./downloads:/app/downloads paste-link-get-video
```

### API
- `POST /api/analyze` - `{ url }` or `{ urls: [] }`
- `POST /api/download/video` - `{ url, quality }`
- `POST /api/download/audio` - `{ url }`
- `POST /api/download/all` - `{ urls, quality, mode }`
- `GET /api/download/status/<task_id>`
- `GET /api/downloads` / `GET /api/downloads/<filename>`

## Project Structure
```
server/
  app.py
  requirements.txt
  Dockerfile
  docker-compose.yml
  templates/index.html
  static/{app.js,style.css}
  downloads/  # gitignored
```

## License
MIT
