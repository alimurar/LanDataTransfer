#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LAN Transfer - Web Tabanlı Yerel Ağ Dosya Paylaşım Sunucusu
Harici kütüphane gerektirmez (Pure Python Standard Library).
Diğer bilgisayara herhangi bir program yüklemeden, sadece tarayıcı (Chrome/Edge vb.)
üzerinden dosya gönderip almanızı sağlar.
"""

import os
import sys
import json
import time
import socket
import urllib.parse
import zipfile
import io
import mimetypes
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading

# Windows Türkçe CP1254 terminalinde Unicode hatalarını önle
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_PORT = 8990
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "Paylasilan_Dosyalar")
os.makedirs(SHARED_DIR, exist_ok=True)

# Paylaşılan pano metni
CLIPBOARD_TEXT = ""
CLIPBOARD_LOCK = threading.Lock()
ACTIVE_PORT = DEFAULT_PORT

def find_free_port(start_port=DEFAULT_PORT, max_attempts=50):
    """Kullanılabilir, boş bir port bulur."""
    for p in range(start_port, start_port + max_attempts):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", p))
            s.listen(1)
            s.close()
            return p
        except Exception:
            continue
    raise RuntimeError("Uygun bir port bulunamadı!")

def get_all_local_ips():
    """Cihazın tüm yerel IPv4 adreslerini tespit eder; birincil LAN IP'sini en başa koyar."""
    primary = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        primary = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    other_ips = set()
    try:
        host_info = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        for item in host_info:
            ip = item[4][0]
            # 127.x.x.x ve 169.254.x.x (APIPA) adreslerini yoksay
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                if ip != primary:
                    other_ips.add(ip)
    except Exception:
        pass

    result = []
    if primary and not primary.startswith("127."):
        result.append(primary)
    result.extend(sorted(list(other_ips)))
    if not result:
        result.append("127.0.0.1")
    return result

def format_bytes(size):
    """Bayt değerini okunabilir formata dönüştürür."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} PB"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⚡ LAN Transfer - Yerel Ağ Paylaşımı</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
            --accent: #8b5cf6;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px 16px;
        }
        .container {
            max-width: 960px;
            margin: 0 auto;
        }
        header {
            text-align: center;
            margin-bottom: 30px;
        }
        header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        .ip-badge-container {
            display: inline-flex;
            gap: 10px;
            align-items: center;
            background: #1e293b;
            padding: 8px 16px;
            border-radius: 9999px;
            border: 1px solid var(--card-border);
            margin-top: 10px;
        }
        .ip-badge {
            font-family: monospace;
            font-size: 1rem;
            color: #38bdf8;
            font-weight: 600;
        }
        .btn-copy {
            background: #334155;
            color: #f8fafc;
            border: none;
            padding: 4px 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.8rem;
            transition: 0.2s;
        }
        .btn-copy:hover { background: #475569; }
        .grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 24px;
        }
        @media (min-width: 768px) {
            .grid { grid-template-columns: 1fr 1fr; }
            .col-span-full { grid-column: span 2; }
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }
        .card h2 {
            font-size: 1.25rem;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .dropzone {
            border: 2px dashed #475569;
            border-radius: 12px;
            padding: 36px 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s ease;
            background: rgba(15, 23, 42, 0.4);
        }
        .dropzone:hover, .dropzone.dragover {
            border-color: var(--primary);
            background: rgba(59, 130, 246, 0.1);
        }
        .dropzone svg {
            width: 48px;
            height: 48px;
            stroke: var(--text-muted);
            margin-bottom: 12px;
        }
        .dropzone.dragover svg { stroke: var(--primary); }
        .dropzone-buttons {
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 16px;
        }
        .btn {
            background: var(--primary);
            color: white;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
            font-size: 0.95rem;
        }
        .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
        .btn-secondary { background: #334155; color: #f8fafc; }
        .btn-secondary:hover { background: #475569; }
        .btn-danger { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
        .btn-danger:hover { background: var(--danger); color: white; }
        .btn-success { background: var(--success); }
        .btn-success:hover { background: #059669; }
        
        /* Upload Progress */
        .progress-container {
            margin-top: 20px;
            display: none;
        }
        .progress-bar-bg {
            background: #334155;
            border-radius: 9999px;
            height: 10px;
            overflow: hidden;
            margin-bottom: 8px;
        }
        .progress-bar {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #3b82f6, #10b981);
            transition: width 0.15s ease;
        }
        .progress-meta {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        /* File List Table */
        .file-list-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 10px;
        }
        .search-box {
            background: #0f172a;
            border: 1px solid var(--card-border);
            padding: 8px 14px;
            border-radius: 8px;
            color: white;
            font-size: 0.9rem;
            outline: none;
            width: 200px;
        }
        .file-table {
            width: 100%;
            border-collapse: collapse;
        }
        .file-table th {
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid var(--card-border);
            color: var(--text-muted);
            font-size: 0.85rem;
            text-transform: uppercase;
        }
        .file-table td {
            padding: 12px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
            font-size: 0.95rem;
        }
        .file-table tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }
        .file-name-cell {
            display: flex;
            align-items: center;
            gap: 10px;
            word-break: break-all;
        }
        .file-actions {
            display: flex;
            gap: 8px;
            justify-content: flex-end;
        }
        .empty-state {
            text-align: center;
            padding: 30px;
            color: var(--text-muted);
        }
        
        /* Clipboard Card */
        textarea.clipboard-box {
            width: 100%;
            background: #0f172a;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 12px;
            color: #f8fafc;
            font-family: monospace;
            resize: vertical;
            min-height: 100px;
            outline: none;
            margin-bottom: 12px;
        }
        .clipboard-actions {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: #1e293b;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            border: 1px solid var(--primary);
            box-shadow: 0 8px 20px rgba(0,0,0,0.4);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 9999;
        }
        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ LAN Transfer</h1>
            <p style="color: var(--text-muted);">2 Windows bilgisayar arasında süper hızlı yerel ağ transferi</p>
            <div class="ip-badge-container">
                <span>🌐 Sunucu Adresi:</span>
                <span class="ip-badge" id="hostAddress">__HOST_URL__</span>
                <button class="btn-copy" onclick="copyHostUrl()">📋 Kopyala</button>
            </div>
        </header>

        <div class="grid">
            <!-- Dosya Yükleme Kartı -->
            <div class="card">
                <h2>📤 Dosya Gönder</h2>
                <div class="dropzone" id="dropzone">
                    <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                        <polyline points="17 8 12 3 7 8"></polyline>
                        <line x1="12" y1="3" x2="12" y2="15"></line>
                    </svg>
                    <p style="font-weight: 600; font-size: 1.1rem; margin-bottom: 6px;">Dosyaları buraya sürükleyin</p>
                    <p style="color: var(--text-muted); font-size: 0.9rem;">veya aşağıdaki butonlarla seçin</p>
                    <div class="dropzone-buttons">
                        <button class="btn" onclick="document.getElementById('fileInput').click()">Dosya Seç</button>
                        <button class="btn btn-secondary" onclick="document.getElementById('folderInput').click()">Klasör Seç</button>
                    </div>
                </div>
                <input type="file" id="fileInput" multiple style="display: none;">
                <input type="file" id="folderInput" webkitdirectory directory multiple style="display: none;">

                <div class="progress-container" id="progressContainer">
                    <div class="progress-bar-bg">
                        <div class="progress-bar" id="progressBar"></div>
                    </div>
                    <div class="progress-meta">
                        <span id="progressFile">Gönderiliyor...</span>
                        <span id="progressPercent">0%</span>
                    </div>
                    <div class="progress-meta" style="margin-top: 4px;">
                        <span id="progressSpeed">0 MB/s</span>
                        <span id="progressRemaining">Kalan: Hesaplanıyor...</span>
                    </div>
                </div>
            </div>

            <!-- Paylaşılan Pano / Not Kartı -->
            <div class="card">
                <h2>📝 Hızlı Pano & Not Paylaşımı</h2>
                <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 10px;">
                    Bilgisayarlar arasında link, kod veya şifre gibi metinleri anında aktarın.
                </p>
                <textarea class="clipboard-box" id="clipboardText" placeholder="Buraya bir metin veya bağlantı yapıştırıp 'Kaydet' butonuna basın..."></textarea>
                <div class="clipboard-actions">
                    <button class="btn btn-secondary" onclick="copyClipboardText()">📋 Metni Kopyala</button>
                    <button class="btn btn-primary" onclick="saveClipboardText()">💾 Gönder / Güncelle</button>
                </div>
            </div>

            <!-- İndirilebilir Dosyalar Kartı (Tam Genişlik) -->
            <div class="card col-span-full">
                <div class="file-list-header">
                    <h2>📁 İndirilebilir Dosyalar (<span id="fileCount">0</span>)</h2>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <input type="text" class="search-box" id="searchBox" placeholder="Dosya ara..." oninput="filterFiles()">
                        <button class="btn btn-secondary" onclick="fetchFiles()">🔄 Yenile</button>
                        <button class="btn btn-success" id="btnDownloadAll" onclick="downloadAllZip()">📦 Tümünü ZIP Olarak İndir</button>
                    </div>
                </div>

                <div style="overflow-x: auto;">
                    <table class="file-table">
                        <thead>
                            <tr>
                                <th>Dosya Adı</th>
                                <th>Boyut</th>
                                <th>Tarih</th>
                                <th style="text-align: right;">İşlemler</th>
                            </tr>
                        </thead>
                        <tbody id="fileTableBody">
                            <tr><td colspan="4" class="empty-state">Yükleniyor...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div class="toast" id="toast">Bildirim mesajı</div>

    <script>
        let allFiles = [];

        function showToast(msg) {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }

        function copyHostUrl() {
            const url = document.getElementById('hostAddress').textContent;
            navigator.clipboard.writeText(url).then(() => showToast('Adres panoya kopyalandı!'));
        }

        // Dosya listesi getirme
        async function fetchFiles() {
            try {
                const res = await fetch('/api/files');
                allFiles = await res.json();
                renderFiles(allFiles);
            } catch (err) {
                console.error(err);
            }
        }

        function renderFiles(files) {
            const tbody = document.getElementById('fileTableBody');
            document.getElementById('fileCount').textContent = files.length;
            if (files.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Henüz paylaşılan dosya yok. Yukarıdan sürükleyip bırakabilirsiniz!</td></tr>';
                return;
            }
            tbody.innerHTML = files.map(f => `
                <tr>
                    <td>
                        <div class="file-name-cell">
                            <span>📄</span>
                            <strong>${escapeHtml(f.name)}</strong>
                        </div>
                    </td>
                    <td>${f.size_formatted}</td>
                    <td style="color: var(--text-muted); font-size: 0.85rem;">${f.mtime_formatted}</td>
                    <td>
                        <div class="file-actions">
                            <a class="btn" style="padding: 6px 12px; font-size: 0.85rem; text-decoration: none;" href="/api/download?filename=${encodeURIComponent(f.name)}" download>⬇️ İndir</a>
                            <button class="btn btn-danger" style="padding: 6px 12px; font-size: 0.85rem;" onclick="deleteFile('${escapeHtml(f.name)}')">🗑️ Sil</button>
                        </div>
                    </td>
                </tr>
            `).join('');
        }

        function filterFiles() {
            const q = document.getElementById('searchBox').value.toLowerCase();
            const filtered = allFiles.filter(f => f.name.toLowerCase().includes(q));
            renderFiles(filtered);
        }

        async function deleteFile(name) {
            if (!confirm(`"${name}" dosyasını silmek istediğinize emin misiniz?`)) return;
            try {
                const res = await fetch(`/api/delete?filename=${encodeURIComponent(name)}`, { method: 'POST' });
                if (res.ok) {
                    showToast('Dosya silindi');
                    fetchFiles();
                }
            } catch (err) {
                showToast('Dosya silinirken hata oluştu');
            }
        }

        function downloadAllZip() {
            window.location.href = '/api/download_all';
        }

        // Pano / Clipboard
        async function fetchClipboard() {
            try {
                const res = await fetch('/api/clipboard');
                const data = await res.json();
                document.getElementById('clipboardText').value = data.text || '';
            } catch (err) {}
        }

        async function saveClipboardText() {
            const text = document.getElementById('clipboardText').value;
            try {
                await fetch('/api/clipboard', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ text })
                });
                showToast('Pano metni kaydedildi!');
            } catch (err) {
                showToast('Kayıt başarısız!');
            }
        }

        function copyClipboardText() {
            const text = document.getElementById('clipboardText').value;
            navigator.clipboard.writeText(text).then(() => showToast('Metin panoya kopyalandı!'));
        }

        // Sürükle ve Bırak Olayları
        const dropzone = document.getElementById('dropzone');
        ['dragenter', 'dragover'].forEach(eName => {
            dropzone.addEventListener(eName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('dragover');
            });
        });
        ['dragleave', 'drop'].forEach(eName => {
            dropzone.addEventListener(eName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove('dragover');
            });
        });

        dropzone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) uploadFiles(files);
        });

        document.getElementById('fileInput').addEventListener('change', (e) => {
            if (e.target.files.length > 0) uploadFiles(e.target.files);
        });
        document.getElementById('folderInput').addEventListener('change', (e) => {
            if (e.target.files.length > 0) uploadFiles(e.target.files);
        });

        // Dosya Yükleme (Streaming / Chunked Upload)
        async function uploadFiles(fileList) {
            const files = Array.from(fileList);
            if (files.length === 0) return;

            const progressContainer = document.getElementById('progressContainer');
            const progressBar = document.getElementById('progressBar');
            const progressFile = document.getElementById('progressFile');
            const progressPercent = document.getElementById('progressPercent');
            const progressSpeed = document.getElementById('progressSpeed');
            const progressRemaining = document.getElementById('progressRemaining');

            progressContainer.style.display = 'block';

            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const uploadName = file.webkitRelativePath || file.name;
                progressFile.textContent = `[${i + 1}/${files.length}] ${uploadName}`;

                await new Promise((resolve, reject) => {
                    const xhr = new XMLHttpRequest();
                    const startTime = Date.now();
                    let lastLoaded = 0;
                    let lastTime = startTime;

                    xhr.open('POST', `/api/upload?filename=${encodeURIComponent(uploadName)}`);

                    xhr.upload.onprogress = (e) => {
                        if (e.lengthComputable) {
                            const percent = Math.round((e.loaded / e.total) * 100);
                            progressBar.style.width = percent + '%';
                            progressPercent.textContent = percent + '%';

                            const now = Date.now();
                            const elapsed = (now - lastTime) / 1000;
                            if (elapsed >= 0.5 || e.loaded === e.total) {
                                const bytesPerSec = (e.loaded - lastLoaded) / (elapsed || 0.001);
                                const speedMB = (bytesPerSec / (1024 * 1024)).toFixed(1);
                                progressSpeed.textContent = `${speedMB} MB/s`;

                                const remainingBytes = e.total - e.loaded;
                                const secRemaining = bytesPerSec > 0 ? Math.round(remainingBytes / bytesPerSec) : 0;
                                progressRemaining.textContent = `Kalan: ${secRemaining} sn`;

                                lastLoaded = e.loaded;
                                lastTime = now;
                            }
                        }
                    };

                    xhr.onload = () => {
                        if (xhr.status === 200) resolve();
                        else reject(new Error('Yükleme hatası: ' + xhr.statusText));
                    };
                    xhr.onerror = () => reject(new Error('Ağ hatası oluştu'));
                    xhr.send(file);
                });
            }

            progressBar.style.width = '100%';
            progressPercent.textContent = '100%';
            showToast('Tüm dosyalar başarıyla yüklendi!');
            setTimeout(() => { progressContainer.style.display = 'none'; }, 2000);
            fetchFiles();
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // İlk yükleme ve periyodik güncelleme
        fetchFiles();
        fetchClipboard();
        setInterval(fetchFiles, 6000);
        setInterval(fetchClipboard, 8000);
    </script>
</body>
</html>
"""

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

class LanTransferHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Konsolu gereksiz isteklerle kirletmemek için temiz loglama
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            ips = get_all_local_ips()
            primary_ip = ips[0] if ips else "localhost"
            lan_url = f"http://{primary_ip}:{ACTIVE_PORT}"
            content = HTML_TEMPLATE.replace("__HOST_URL__", lan_url)
            content_bytes = content.encode("utf-8")
            self.send_header("Content-Length", str(len(content_bytes)))
            self.end_headers()
            self.wfile.write(content_bytes)
            return

        elif path == "/api/files":
            files = []
            try:
                for entry in os.scandir(SHARED_DIR):
                    if entry.is_file():
                        stat = entry.stat()
                        files.append({
                            "name": entry.name,
                            "size": stat.st_size,
                            "size_formatted": format_bytes(stat.st_size),
                            "mtime": stat.st_mtime,
                            "mtime_formatted": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
                        })
            except Exception as e:
                pass

            files.sort(key=lambda x: x["mtime"], reverse=True)
            data = json.dumps(files).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/clipboard":
            with CLIPBOARD_LOCK:
                data = json.dumps({"text": CLIPBOARD_TEXT}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        elif path == "/api/download":
            qs = urllib.parse.parse_qs(parsed.query)
            filename = qs.get("filename", [None])[0]
            if not filename:
                self.send_error(400, "Dosya adi belirtilmedi")
                return

            safe_name = os.path.basename(filename)
            file_path = os.path.join(SHARED_DIR, safe_name)
            if not os.path.isfile(file_path):
                self.send_error(404, "Dosya bulunamadi")
                return

            try:
                file_size = os.path.getsize(file_path)
                mime_type, _ = mimetypes.guess_type(file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"

                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(file_size))
                encoded_name = urllib.parse.quote(safe_name)
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{encoded_name}')
                self.end_headers()

                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 512)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (ConnectionResetError, BrokenPipeError):
                pass
            except Exception as e:
                self.send_error(500, f"Indirme hatasi: {e}")
            return

        elif path == "/api/download_all":
            # Tüm dosyaları anında zip olarak paketleyip gönderir
            try:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for entry in os.scandir(SHARED_DIR):
                        if entry.is_file():
                            zip_file.write(entry.path, arcname=entry.name)

                zip_data = zip_buffer.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="tum_dosyalar.zip"')
                self.send_header("Content-Length", str(len(zip_data)))
                self.end_headers()
                self.wfile.write(zip_data)
            except Exception as e:
                self.send_error(500, f"Zip olusturulamadi: {e}")
            return

        self.send_error(404, "Sayfa bulunamadi")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/upload":
            qs = urllib.parse.parse_qs(parsed.query)
            filename = qs.get("filename", [None])[0]
            if not filename:
                self.send_error(400, "Dosya adi eksik")
                return

            # Dizin geçişlerini (directory traversal) engelle
            safe_name = os.path.basename(filename)
            dest_path = os.path.join(SHARED_DIR, safe_name)

            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self.send_error(400, "Gecersiz dosya boyutu")
                return

            print(f"📥 Dosya aliniyor: {safe_name} ({format_bytes(content_length)})")

            bytes_read = 0
            chunk_size = 1024 * 1024  # 1 MB chunk
            try:
                with open(dest_path, "wb") as f:
                    while bytes_read < content_length:
                        to_read = min(chunk_size, content_length - bytes_read)
                        chunk = self.rfile.read(to_read)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_read += len(chunk)

                print(f"✅ Dosya kaydedildi: {safe_name}")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "success"}')
            except Exception as e:
                print(f"❌ Yukleme hatasi: {e}")
                self.send_error(500, f"Kayit hatasi: {e}")
            return

        elif path == "/api/delete":
            qs = urllib.parse.parse_qs(parsed.query)
            filename = qs.get("filename", [None])[0]
            if not filename:
                self.send_error(400, "Dosya adi eksik")
                return

            safe_name = os.path.basename(filename)
            target = os.path.join(SHARED_DIR, safe_name)
            if os.path.isfile(target):
                try:
                    os.remove(target)
                    print(f"🗑️ Dosya silindi: {safe_name}")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "deleted"}')
                    return
                except Exception as e:
                    self.send_error(500, f"Silme hatasi: {e}")
                    return
            self.send_error(404, "Dosya bulunamadi")
            return

        elif path == "/api/clipboard":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body.decode("utf-8"))
                global CLIPBOARD_TEXT
                with CLIPBOARD_LOCK:
                    CLIPBOARD_TEXT = data.get("text", "")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            except Exception as e:
                self.send_error(400, "Gecersiz veri")
            return

        self.send_error(404, "Islem bulunamadi")

def start_server(port=None):
    global ACTIVE_PORT
    if port is None:
        port = find_free_port(DEFAULT_PORT)
    ACTIVE_PORT = port

    ips = get_all_local_ips()
    server = ThreadedHTTPServer(("0.0.0.0", port), LanTransferHandler)

    print("=" * 65)
    print("🚀 LAN TRANSFER WEB SUNUCUSU BAŞLATILDI!")
    print("=" * 65)
    print(f"📂 Paylaşılan Dosyalar Klasörü: {SHARED_DIR}")
    print("-" * 65)
    print("🌐 Aynı Wi-Fi veya LAN'daki diğer Windows bilgisayarınızdan")
    print("   tarayıcınızı (Chrome / Edge) açıp aşağıdaki adrese girin:\n")
    for ip in ips:
        print(f"   👉 http://{ip}:{port}")
    print(f"\n   (Bu bilgisayardan test için: http://localhost:{port})")
    print("=" * 65)
    print("Durdurmak için Ctrl + C tuşlarına basın...\n")

    # Tarayıcıyı bu bilgisayarda otomatik aç
    threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(f"http://localhost:{port}")), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Sunucu durduruldu.")
        server.server_close()

if __name__ == "__main__":
    start_server()
