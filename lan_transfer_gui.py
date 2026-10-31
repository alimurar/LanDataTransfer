#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LAN Transfer - Masaüstü Grafik Arayüzlü (GUI) Dosya Transfer Programı
Harici kütüphane gerektirmez (Python Tkinter & Socket).
2 Windows bilgisayar arasında doğrudan, yüksek hızlı TCP soket transferi sağlar.
Otomatik cihaz bulma (UDP Discovery) ve klasör aktarım desteği içerir.
"""

import os
import sys
import time
import json
import struct
import socket
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Varsayılan Yapılandırma (Windows Hyper-V engelli 50000-50059 dışındaki güvenli portlar)
DEFAULT_TCP_PORT = 39000
DEFAULT_UDP_PORT = 39005
BUFFER_SIZE = 1024 * 1024  # 1 MB chunk

def get_local_ip():
    """Cihazın yerel ağ IP adresini döndürür."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def format_bytes(size):
    """Bayt değerini okunabilir formata dönüştürür."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} PB"

def format_time(seconds):
    """Saniyeyi dakika/saniye formatına çevirir."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} sn"
    mins, secs = divmod(seconds, 60)
    return f"{mins} dk {secs} sn"

class NetworkProtocol:
    """TCP üzerinden güvenilir JSON ve binary veri transfer protokolü."""
    @staticmethod
    def recv_exact(sock, length):
        data = bytearray()
        while len(data) < length:
            packet = sock.recv(length - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)

    @staticmethod
    def send_json(sock, data):
        payload = json.dumps(data).encode('utf-8')
        sock.sendall(struct.pack('>I', len(payload)) + payload)

    @staticmethod
    def recv_json(sock):
        raw_len = NetworkProtocol.recv_exact(sock, 4)
        if not raw_len:
            return None
        length = struct.unpack('>I', raw_len)[0]
        payload = NetworkProtocol.recv_exact(sock, length)
        if not payload:
            return None
        return json.loads(payload.decode('utf-8'))


class LanTransferApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("⚡ LAN Transfer - Windows Hızlı Veri Aktarımı")
        self.geometry("780x620")
        self.minsize(700, 550)

        # Varsayılan İndirme Klasörü
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.save_folder = os.path.join(self.base_dir, "Gelen_Dosyalar")
        os.makedirs(self.save_folder, exist_ok=True)

        self.local_ip = get_local_ip()
        self.hostname = socket.gethostname()

        # Alıcı thread durumları
        self.receiver_running = False
        self.receiver_sock = None
        self.udp_listener_sock = None
        self.active_tcp_port = DEFAULT_TCP_PORT

        # Gönderici durumları
        self.send_queue = []  # list of dict: {name, path, rel_path, size, is_dir}
        self.transfer_cancelled = False

        self._configure_styles()
        self._build_ui()

        # Otomatik olarak Alıcı modunu arka planda başlat
        self.start_receiver()

    def _configure_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # Renk paleti
        self.bg_color = "#0f172a"
        self.card_bg = "#1e293b"
        self.text_color = "#f8fafc"
        self.primary_color = "#3b82f6"

        self.configure(bg=self.bg_color)

        self.style.configure(".", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 9))
        self.style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#334155", foreground="#cbd5e1", padding=[20, 8], font=("Segoe UI", 10, "bold"))
        self.style.map("TNotebook.Tab",
                       background=[("selected", self.primary_color)],
                       foreground=[("selected", "#ffffff")])

        self.style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        self.style.configure("TLabel", background=self.card_bg, foreground=self.text_color)
        self.style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground="#60a5fa")
        self.style.configure("Action.TButton", font=("Segoe UI", 9, "bold"), background=self.primary_color, foreground="white", borderwidth=0)
        self.style.map("Action.TButton", background=[("active", "#2563eb")])

        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), background="#475569", foreground="white", borderwidth=0)
        self.style.map("Secondary.TButton", background=[("active", "#64748b")])

        self.style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), background="#10b981", foreground="white", borderwidth=0)
        self.style.map("Success.TButton", background=[("active", "#059669")])

        self.style.configure("Danger.TButton", font=("Segoe UI", 9), background="#ef4444", foreground="white", borderwidth=0)
        self.style.map("Danger.TButton", background=[("active", "#dc2626")])

        self.style.configure("Custom.Horizontal.TProgressbar", thickness=14, troughcolor="#334155", background="#3b82f6")

    def _build_ui(self):
        # Üst Başlık ve IP Bilgi Barı
        top_frame = tk.Frame(self, bg=self.bg_color, pady=12, padx=16)
        top_frame.pack(fill="x")

        title_lbl = tk.Label(top_frame, text="⚡ LAN Transfer", font=("Segoe UI", 16, "bold"), bg=self.bg_color, fg="#38bdf8")
        title_lbl.pack(side="left")

        ip_container = tk.Frame(top_frame, bg="#1e293b", padx=12, pady=4, relief="ridge", bd=1)
        ip_container.pack(side="right")

        tk.Label(ip_container, text=f"Cihaz: {self.hostname} | Yerel IP: ", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9)).pack(side="left")
        self.ip_display = tk.Label(ip_container, text=self.local_ip, bg="#1e293b", fg="#10b981", font=("Segoe UI", 10, "bold"))
        self.ip_display.pack(side="left", padx=4)

        copy_btn = tk.Button(ip_container, text="Kopyala", bg="#334155", fg="white", font=("Segoe UI", 8),
                             relief="flat", cursor="hand2", command=self.copy_ip)
        copy_btn.pack(side="left", padx=4)

        # Sekmeler (Notebook)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=8)

        # Tab 1: Alıcı Modu
        self.tab_recv = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_recv, text="📥  Dosya Al (Alıcı Modu)")
        self._build_receiver_tab()

        # Tab 2: Gönderici Modu
        self.tab_send = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_send, text="📤  Dosya Gönder (Gönderici Modu)")
        self._build_sender_tab()

    def copy_ip(self):
        self.clipboard_clear()
        self.clipboard_append(self.local_ip)
        messagebox.showinfo("Kopyalandı", f"IP Adresi ({self.local_ip}) panoya kopyalandı!")

    # =========================================================================
    # TAB 1: ALICI MODU
    # =========================================================================
    def _build_receiver_tab(self):
        frame = tk.Frame(self.tab_recv, bg=self.card_bg, padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        # Alıcı Durum & Klasör Seçimi
        settings_frame = tk.Frame(frame, bg="#273549", padx=14, pady=12, relief="flat")
        settings_frame.pack(fill="x", pady=(0, 12))

        # 1. Satır: Kayıt Klasörü
        row1 = tk.Frame(settings_frame, bg="#273549")
        row1.pack(fill="x", pady=4)
        tk.Label(row1, text="📁 Kayıt Yeri:", bg="#273549", fg="#cbd5e1", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.recv_folder_lbl = tk.Label(row1, text=self.save_folder, bg="#273549", fg="#38bdf8", anchor="w")
        self.recv_folder_lbl.pack(side="left", padx=8, fill="x", expand=True)

        btn_ch_folder = ttk.Button(row1, text="Klasörü Değiştir", style="Secondary.TButton", command=self.choose_save_folder)
        btn_ch_folder.pack(side="right", padx=4)

        btn_open_folder = ttk.Button(row1, text="Klasörü Aç", style="Secondary.TButton", command=self.open_save_folder)
        btn_open_folder.pack(side="right")

        # 2. Satır: Durum Göstergesi ve Kontrol Butonu
        row2 = tk.Frame(settings_frame, bg="#273549")
        row2.pack(fill="x", pady=(8, 4))

        self.recv_status_lbl = tk.Label(row2, text="🟢 Alıcı Aktif - Diğer bilgisayardan dosya bekleniyor...",
                                        bg="#273549", fg="#10b981", font=("Segoe UI", 9, "bold"))
        self.recv_status_lbl.pack(side="left")

        self.btn_toggle_recv = ttk.Button(row2, text="Alıcıyı Durdur", style="Danger.TButton", command=self.toggle_receiver)
        self.btn_toggle_recv.pack(side="right")

        # Canlı İlerleme Çubuğu (Alıcı)
        progress_box = tk.Frame(frame, bg="#1e293b", pady=8)
        progress_box.pack(fill="x")

        self.recv_progress_lbl = tk.Label(progress_box, text="Bekleniyor...", bg="#1e293b", fg="#cbd5e1", font=("Segoe UI", 9))
        self.recv_progress_lbl.pack(anchor="w")

        self.recv_progressbar = ttk.Progressbar(progress_box, style="Custom.Horizontal.TProgressbar", mode="determinate")
        self.recv_progressbar.pack(fill="x", pady=6)

        self.recv_speed_lbl = tk.Label(progress_box, text="0 MB/s", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8))
        self.recv_speed_lbl.pack(anchor="e")

        # Log Penceresi
        tk.Label(frame, text="📜 Transfer ve Bağlantı Geçmişi:", bg=self.card_bg, fg="#94a3b8", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 4))

        self.recv_log = tk.Text(frame, bg="#0f172a", fg="#f8fafc", font=("Consolas", 9), relief="flat", height=10)
        self.recv_log.pack(fill="both", expand=True)

    def safe_after(self, delay, callback):
        try:
            if self.winfo_exists():
                self.after(delay, callback)
        except Exception:
            pass

    def log_recv(self, text):
        def _append():
            try:
                timestamp = time.strftime("[%H:%M:%S] ")
                self.recv_log.insert("end", timestamp + text + "\n")
                self.recv_log.see("end")
            except Exception:
                pass
        self.safe_after(0, _append)

    def choose_save_folder(self):
        folder = filedialog.askdirectory(initialdir=self.save_folder)
        if folder:
            self.save_folder = folder
            self.recv_folder_lbl.config(text=self.save_folder)
            self.log_recv(f"Kayıt klasörü değiştirildi: {self.save_folder}")

    def open_save_folder(self):
        if os.path.exists(self.save_folder):
            os.startfile(self.save_folder)

    def toggle_receiver(self):
        if self.receiver_running:
            self.stop_receiver()
        else:
            self.start_receiver()

    def start_receiver(self):
        if self.receiver_running:
            return
        self.receiver_running = True
        self.recv_status_lbl.config(text="🟢 Alıcı Aktif - Diğer bilgisayardan dosya bekleniyor...", fg="#10b981")
        self.btn_toggle_recv.config(text="Alıcıyı Durdur", style="Danger.TButton")

        # 1. TCP Listener Thread
        threading.Thread(target=self._run_tcp_server, daemon=True).start()
        # 2. UDP Discovery Responder Thread
        threading.Thread(target=self._run_udp_responder, daemon=True).start()

    def stop_receiver(self):
        self.receiver_running = False
        try:
            if self.receiver_sock:
                self.receiver_sock.close()
            if self.udp_listener_sock:
                self.udp_listener_sock.close()
        except Exception:
            pass
        self.recv_status_lbl.config(text="🔴 Alıcı Durduruldu", fg="#ef4444")
        self.btn_toggle_recv.config(text="Alıcıyı Başlat", style="Action.TButton")
        self.log_recv("Alıcı sunucusu durduruldu.")

    def _run_udp_responder(self):
        """Ağdaki göndericilerden gelen keşif yayınlarını yanıtlar."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DEFAULT_UDP_PORT))
            self.udp_listener_sock = sock

            while self.receiver_running:
                try:
                    data, addr = sock.recvfrom(1024)
                    if data == b"LAN_DISCOVER":
                        reply = f"LAN_OFFER:{self.hostname}:{self.active_tcp_port}".encode("utf-8")
                        sock.sendto(reply, addr)
                except Exception:
                    break
        except Exception as e:
            self.log_recv(f"⚠️ Otomatik arama (UDP) başlatılamadı: {e}. Manuel IP ile bağlanabilirsiniz.")

    def _run_tcp_server(self):
        """Gelen dosya transfer bağlantılarını dinler ve işler."""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            actual_port = DEFAULT_TCP_PORT
            bound = False
            for p in range(DEFAULT_TCP_PORT, DEFAULT_TCP_PORT + 50):
                try:
                    server.bind(("0.0.0.0", p))
                    actual_port = p
                    bound = True
                    break
                except Exception:
                    continue

            if not bound:
                self.log_recv("❌ Uygun bir TCP portu bulunamadı!")
                return

            self.active_tcp_port = actual_port
            server.listen(5)
            self.receiver_sock = server

            self.log_recv(f"Alıcı sunucusu hazır ve dinliyor (Port: {actual_port})")
            self.safe_after(0, lambda p=actual_port: self.ip_display.config(text=f"{self.local_ip}:{p}"))

            while self.receiver_running:
                try:
                    client, addr = server.accept()
                except Exception:
                    break

                self.log_recv(f"Bağlantı kabul edildi: {addr[0]}")
                threading.Thread(target=self._handle_incoming_transfer, args=(client, addr), daemon=True).start()
        except Exception as e:
            self.log_recv(f"Sunucu hatası: {e}")

    def _handle_incoming_transfer(self, client, addr):
        try:
            # 1. Başlangıç el sıkışması
            init_msg = NetworkProtocol.recv_json(client)
            if not init_msg or init_msg.get("action") != "TRANSFER_START":
                client.close()
                return

            total_files = init_msg.get("total_files", 0)
            total_size = init_msg.get("total_size", 0)
            sender_name = init_msg.get("sender", addr[0])

            self.log_recv(f"'{sender_name}' toplam {total_files} dosya ({format_bytes(total_size)}) gönderiyor...")
            NetworkProtocol.send_json(client, {"status": "READY"})

            received_total_bytes = 0
            start_time = time.time()
            last_time = start_time
            last_bytes = 0

            # Dosyaları sırayla al
            for file_idx in range(total_files):
                file_hdr = NetworkProtocol.recv_json(client)
                if not file_hdr or file_hdr.get("action") != "FILE_HEADER":
                    break

                rel_path = file_hdr["rel_path"]
                file_size = file_hdr["size"]

                target_file_path = os.path.join(self.save_folder, rel_path)
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)

                self.safe_after(0, lambda name=os.path.basename(rel_path), idx=file_idx + 1:
                           self.recv_progress_lbl.config(text=f"Alınıyor ({idx}/{total_files}): {name}"))

                NetworkProtocol.send_json(client, {"status": "OK"})

                # Veri akışını alıp dosyaya yaz
                file_bytes_read = 0
                with open(target_file_path, "wb") as f:
                    while file_bytes_read < file_size:
                        chunk_size = min(BUFFER_SIZE, file_size - file_bytes_read)
                        chunk = client.recv(chunk_size)
                        if not chunk:
                            raise ConnectionError("Bağlantı beklenmedik şekilde koptu.")
                        f.write(chunk)
                        file_bytes_read += len(chunk)
                        received_total_bytes += len(chunk)

                        # Hız & İlerleme hesaplama
                        now = time.time()
                        if now - last_time >= 0.3 or received_total_bytes == total_size:
                            speed = (received_total_bytes - last_bytes) / (now - last_time or 0.001)
                            speed_mb = speed / (1024 * 1024)
                            pct = (received_total_bytes / total_size) * 100 if total_size > 0 else 100

                            self.safe_after(0, lambda p=pct, s=speed_mb: self._update_recv_ui(p, s))
                            last_time = now
                            last_bytes = received_total_bytes

                NetworkProtocol.send_json(client, {"status": "FILE_OK"})
                self.log_recv(f"  ✓ {rel_path} alındı ({format_bytes(file_size)})")

            # Bitiş onayı
            end_msg = NetworkProtocol.recv_json(client)
            if end_msg and end_msg.get("action") == "TRANSFER_END":
                NetworkProtocol.send_json(client, {"status": "COMPLETE"})
                self.log_recv(f"🎉 Tüm transfer başarıyla tamamlandı! ({format_bytes(received_total_bytes)})")
                self.safe_after(0, lambda: self._recv_finished())

        except Exception as e:
            self.log_recv(f"❌ Transfer hatası: {e}")
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _update_recv_ui(self, pct, speed_mb):
        self.recv_progressbar["value"] = pct
        self.recv_speed_lbl.config(text=f"{speed_mb:.1f} MB/s | %{int(pct)}")

    def _recv_finished(self):
        self.recv_progressbar["value"] = 100
        self.recv_progress_lbl.config(text="Transfer tamamlandı!")
        self.recv_speed_lbl.config(text="Tamamlandı ✓")
        messagebox.showinfo("Transfer Tamamlandı", f"Dosyalar başarıyla alındı!\nKonum: {self.save_folder}")

    # =========================================================================
    # TAB 2: GÖNDERİCİ MODU
    # =========================================================================
    def _build_sender_tab(self):
        frame = tk.Frame(self.tab_send, bg=self.card_bg, padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        # Hedef IP ve Port Seçimi
        target_frame = tk.Frame(frame, bg="#273549", padx=14, pady=10)
        target_frame.pack(fill="x", pady=(0, 10))

        tk.Label(target_frame, text="🎯 Alıcı Bilgisayar:", bg="#273549", fg="#cbd5e1", font=("Segoe UI", 9, "bold")).pack(side="left")

        tk.Label(target_frame, text="IP:", bg="#273549", fg="#94a3b8").pack(side="left", padx=(10, 4))
        self.target_ip_entry = tk.Entry(target_frame, bg="#0f172a", fg="white", insertbackground="white", width=18, font=("Segoe UI", 9))
        self.target_ip_entry.pack(side="left", padx=4)

        tk.Label(target_frame, text="Port:", bg="#273549", fg="#94a3b8").pack(side="left", padx=(8, 4))
        self.target_port_entry = tk.Entry(target_frame, bg="#0f172a", fg="white", insertbackground="white", width=6, font=("Segoe UI", 9))
        self.target_port_entry.insert(0, str(DEFAULT_TCP_PORT))
        self.target_port_entry.pack(side="left", padx=4)

        btn_scan = ttk.Button(target_frame, text="🔍 Alıcıları Otomatik Bul", style="Secondary.TButton", command=self.discover_receivers)
        btn_scan.pack(side="left", padx=12)

        # Dosya Ekleme Butonları & Dosya Listesi
        list_header = tk.Frame(frame, bg=self.card_bg)
        list_header.pack(fill="x", pady=(4, 6))

        tk.Label(list_header, text="📦 Gönderilecek Dosyalar / Klasörler:", bg=self.card_bg, fg="#94a3b8", font=("Segoe UI", 9, "bold")).pack(side="left")

        btn_add_file = ttk.Button(list_header, text="➕ Dosya Ekle", style="Action.TButton", command=self.add_files_to_send)
        btn_add_file.pack(side="right", padx=4)

        btn_add_folder = ttk.Button(list_header, text="📁 Klasör Ekle", style="Action.TButton", command=self.add_folder_to_send)
        btn_add_folder.pack(side="right", padx=4)

        btn_clear = ttk.Button(list_header, text="🗑️ Temizle", style="Danger.TButton", command=self.clear_send_queue)
        btn_clear.pack(side="right", padx=4)

        # Tablo (Treeview)
        cols = ("name", "type", "size", "path")
        self.tree_send = ttk.Treeview(frame, columns=cols, show="headings", height=8, selectmode="browse")
        self.tree_send.heading("name", text="Öğe Adı")
        self.tree_send.heading("type", text="Tür")
        self.tree_send.heading("size", text="Boyut")
        self.tree_send.heading("path", text="Tam Yol")

        self.tree_send.column("name", width=220)
        self.tree_send.column("type", width=70, anchor="center")
        self.tree_send.column("size", width=90, anchor="e")
        self.tree_send.column("path", width=300)
        self.tree_send.pack(fill="both", expand=True)

        # İstatistikler ve Gönder Butonu Barı
        action_bar = tk.Frame(frame, bg=self.card_bg, pady=10)
        action_bar.pack(fill="x")

        self.send_summary_lbl = tk.Label(action_bar, text="0 öğe seçildi (Toplam: 0 B)", bg=self.card_bg, fg="#94a3b8", font=("Segoe UI", 9, "bold"))
        self.send_summary_lbl.pack(side="left")

        self.btn_send_now = ttk.Button(action_bar, text="🚀 Gönderimi Başlat", style="Success.TButton", command=self.start_sending)
        self.btn_send_now.pack(side="right", padx=6)

        # Gönderici İlerleme Göstergeleri
        send_prog_frame = tk.Frame(frame, bg="#1e293b", pady=6)
        send_prog_frame.pack(fill="x")

        meta_frame = tk.Frame(send_prog_frame, bg="#1e293b")
        meta_frame.pack(fill="x")

        self.send_status_lbl = tk.Label(meta_frame, text="Hazır", bg="#1e293b", fg="#cbd5e1", font=("Segoe UI", 9))
        self.send_status_lbl.pack(side="left")

        self.send_speed_lbl = tk.Label(meta_frame, text="0 MB/s", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold"))
        self.send_speed_lbl.pack(side="right")

        self.send_progressbar = ttk.Progressbar(send_prog_frame, style="Custom.Horizontal.TProgressbar", mode="determinate")
        self.send_progressbar.pack(fill="x", pady=6)

    def discover_receivers(self):
        """Ağdaki açık alıcıları UDP ile tarar."""
        def _scan_thread():
            found = []
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(1.5)
                # Yayın gönder
                sock.sendto(b"LAN_DISCOVER", ("255.255.255.255", DEFAULT_UDP_PORT))

                start = time.time()
                while time.time() - start < 1.5:
                    try:
                        data, addr = sock.recvfrom(1024)
                        text = data.decode('utf-8', errors='ignore')
                        if text.startswith("LAN_OFFER:"):
                            parts = text.split(":")
                            hname = parts[1]
                            port = parts[2]
                            found.append((addr[0], port, hname))
                    except socket.timeout:
                        break
                sock.close()
            except Exception as e:
                pass

            self.safe_after(0, lambda: self._handle_scan_results(found))

        threading.Thread(target=_scan_thread, daemon=True).start()

    def _handle_scan_results(self, found):
        if not found:
            messagebox.showinfo("Cihaz Bulunamadı",
                                "Ağda açık alıcı bulunamadı!\n"
                                "1. Diğer bilgisayarda LAN Transfer programının açık ve 'Dosya Al' sekmesinde olduğundan emin olun.\n"
                                "2. Her iki bilgisayarın da aynı Wi-Fi/Modeme bağlı olduğunu kontrol edin.\n"
                                "3. İsterseniz diğer bilgisayarın IP adresini manuel olarak yazabilirsiniz.")
            return

        # Bulunan cihazları göster veya tek ise direkt seç
        if len(found) == 1:
            ip, port, hname = found[0]
            self.target_ip_entry.delete(0, "end")
            self.target_ip_entry.insert(0, ip)
            self.target_port_entry.delete(0, "end")
            self.target_port_entry.insert(0, port)
            messagebox.showinfo("Alıcı Bulundu", f"Hedef bilgisayar otomatik bağlandı:\n{hname} ({ip}:{port})")
        else:
            popup = tk.Toplevel(self)
            popup.title("Alıcı Seçin")
            popup.geometry("380x240")
            popup.configure(bg=self.card_bg)

            tk.Label(popup, text="Ağda bulunan alıcılar:", bg=self.card_bg, fg="white", font=("Segoe UI", 10, "bold")).pack(pady=10)
            listbox = tk.Listbox(popup, bg="#0f172a", fg="white", font=("Segoe UI", 9))
            listbox.pack(fill="both", expand=True, padx=16, pady=6)

            for ip, port, hname in found:
                listbox.insert("end", f"{hname} - {ip}:{port}")

            def _select():
                sel = listbox.curselection()
                if sel:
                    ip, port, _ = found[sel[0]]
                    self.target_ip_entry.delete(0, "end")
                    self.target_ip_entry.insert(0, ip)
                    self.target_port_entry.delete(0, "end")
                    self.target_port_entry.insert(0, port)
                    popup.destroy()

            tk.Button(popup, text="Seç ve Bağlan", bg=self.primary_color, fg="white", font=("Segoe UI", 9, "bold"),
                      relief="flat", command=_select).pack(pady=10)

    def add_files_to_send(self):
        files = filedialog.askopenfilenames()
        if not files:
            return
        for fpath in files:
            fpath = os.path.abspath(fpath)
            size = os.path.getsize(fpath)
            name = os.path.basename(fpath)
            self.send_queue.append({
                "name": name,
                "path": fpath,
                "rel_path": name,
                "size": size,
                "is_dir": False
            })
            self.tree_send.insert("", "end", values=(name, "Dosya", format_bytes(size), fpath))
        self._update_send_summary()

    def add_folder_to_send(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        folder = os.path.abspath(folder)
        folder_name = os.path.basename(folder)

        added_count = 0
        total_folder_size = 0
        for root, _, files in os.walk(folder):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.join(folder_name, os.path.relpath(full_path, folder))
                size = os.path.getsize(full_path)
                total_folder_size += size
                self.send_queue.append({
                    "name": file,
                    "path": full_path,
                    "rel_path": rel_path,
                    "size": size,
                    "is_dir": False
                })
                added_count += 1

        self.tree_send.insert("", "end", values=(f"📁 {folder_name} (Klasör)", "Klasör", format_bytes(total_folder_size), folder))
        self._update_send_summary()

    def clear_send_queue(self):
        self.send_queue.clear()
        for item in self.tree_send.get_children():
            self.tree_send.delete(item)
        self._update_send_summary()

    def _update_send_summary(self):
        total_size = sum(item["size"] for item in self.send_queue)
        count = len(self.send_queue)
        self.send_summary_lbl.config(text=f"{count} dosya seçildi (Toplam: {format_bytes(total_size)})")

    def start_sending(self):
        target_ip = self.target_ip_entry.get().strip()
        port_str = self.target_port_entry.get().strip()

        if not target_ip:
            messagebox.showwarning("Eksik Bilgi", "Lütfen alıcı bilgisayarın IP adresini girin veya 'Alıcıları Otomatik Bul' butonuna basın.")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Hata", "Geçersiz Port numarası!")
            return

        if not self.send_queue:
            messagebox.showwarning("Dosya Seçilmedi", "Lütfen gönderilecek en az bir dosya veya klasör ekleyin.")
            return

        self.btn_send_now.config(state="disabled")
        self.send_status_lbl.config(text=f"{target_ip} adresine bağlanılıyor...")
        threading.Thread(target=self._run_sender_transfer, args=(target_ip, port), daemon=True).start()

    def _run_sender_transfer(self, target_ip, port):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(8.0)
            sock.connect((target_ip, port))
            sock.settimeout(None)

            total_files = len(self.send_queue)
            total_size = sum(item["size"] for item in self.send_queue)

            # 1. Başlangıç Bildirimi
            NetworkProtocol.send_json(sock, {
                "action": "TRANSFER_START",
                "total_files": total_files,
                "total_size": total_size,
                "sender": self.hostname
            })

            ready_resp = NetworkProtocol.recv_json(sock)
            if not ready_resp or ready_resp.get("status") != "READY":
                raise ConnectionError("Alıcı transferi başlatmayı reddetti.")

            sent_total_bytes = 0
            start_time = time.time()
            last_time = start_time
            last_bytes = 0

            # 2. Dosyaları sırayla gönder
            for idx, item in enumerate(self.send_queue):
                file_path = item["path"]
                rel_path = item["rel_path"]
                file_size = item["size"]

                self.safe_after(0, lambda n=item["name"], i=idx+1:
                           self.send_status_lbl.config(text=f"Gönderiliyor ({i}/{total_files}): {n}"))

                # Dosya Başlığı
                NetworkProtocol.send_json(sock, {
                    "action": "FILE_HEADER",
                    "rel_path": rel_path,
                    "size": file_size
                })

                file_ok_resp = NetworkProtocol.recv_json(sock)
                if not file_ok_resp or file_ok_resp.get("status") != "OK":
                    raise ConnectionError("Alıcı dosya başlığını onaylamadı.")

                # Dosya Baytlarını Gönder
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(BUFFER_SIZE)
                        if not chunk:
                            break
                        sock.sendall(chunk)
                        sent_total_bytes += len(chunk)

                        # Canlı İlerleme ve Hız
                        now = time.time()
                        if now - last_time >= 0.3 or sent_total_bytes == total_size:
                            speed = (sent_total_bytes - last_bytes) / (now - last_time or 0.001)
                            speed_mb = speed / (1024 * 1024)
                            pct = (sent_total_bytes / total_size) * 100 if total_size > 0 else 100

                            rem_bytes = total_size - sent_total_bytes
                            rem_sec = rem_bytes / speed if speed > 0 else 0

                            self.safe_after(0, lambda p=pct, s=speed_mb, r=rem_sec:
                                       self._update_send_ui(p, s, r))
                            last_time = now
                            last_bytes = sent_total_bytes

                # Dosya Bitiş Onayı
                ack = NetworkProtocol.recv_json(sock)
                if not ack or ack.get("status") != "FILE_OK":
                    raise ConnectionError("Dosya aktarımı tamamlanamadı.")

            # 3. Tüm Transfer Bitiş Bildirimi
            NetworkProtocol.send_json(sock, {"action": "TRANSFER_END"})
            complete_resp = NetworkProtocol.recv_json(sock)

            elapsed = time.time() - start_time
            avg_speed = (total_size / (1024 * 1024)) / (elapsed or 0.001)

            self.safe_after(0, lambda: self._send_finished(total_size, avg_speed, elapsed))

        except Exception as e:
            self.safe_after(0, lambda err=str(e): self._send_error(err))
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
            self.safe_after(0, lambda: self.btn_send_now.config(state="normal"))

    def _update_send_ui(self, pct, speed_mb, rem_sec):
        self.send_progressbar["value"] = pct
        self.send_speed_lbl.config(text=f"{speed_mb:.1f} MB/s | Kalan: {format_time(rem_sec)} | %{int(pct)}")

    def _send_finished(self, total_size, avg_speed, elapsed):
        self.send_progressbar["value"] = 100
        self.send_status_lbl.config(text="Transfer başarıyla tamamlandı!")
        self.send_speed_lbl.config(text="Tamamlandı ✓")
        messagebox.showinfo("Başarılı",
                            f"Tüm dosyalar başarıyla gönderildi!\n\n"
                            f"Toplam Boyut: {format_bytes(total_size)}\n"
                            f"Geçen Süre: {format_time(elapsed)}\n"
                            f"Ortalama Hız: {avg_speed:.1f} MB/s")

    def _send_error(self, err):
        self.send_status_lbl.config(text="Hata oluştu!")
        self.send_speed_lbl.config(text="Başarısız ❌")
        messagebox.showerror("Transfer Hatası",
                             f"Dosya gönderilirken bir hata oluştu:\n{err}\n\n"
                             f"İpuçları:\n"
                             f"1. Hedef bilgisayarda uygulamanın açık ve dinlemede olduğunu kontrol edin.\n"
                             f"2. IP adresinin doğruluğundan emin olun.\n"
                             f"3. Windows Güvenlik Duvarı izinlerini kontrol edin.")


if __name__ == "__main__":
    app = LanTransferApp()
    app.mainloop()
