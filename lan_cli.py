#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LAN Transfer - Komut Satırı Arayüzü (CLI)
Masaüstü GUI uygulamasıyla (lan_transfer_gui.py) tam uyumludur.
Kullanım:
    python lan_cli.py receive [kayit_dizini] [--port 50000]
    python lan_cli.py send <hedef_ip> <dosya_veya_klasor> [--port 50000]
    python lan_cli.py scan
"""

import os
import sys
import time
import json
import struct
import socket
import argparse

# Windows Türkçe CP1254 terminalinde emoji yazdırma hatalarını önle
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_TCP_PORT = 39000
DEFAULT_UDP_PORT = 39005
BUFFER_SIZE = 1024 * 1024  # 1 MB

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} PB"

class NetworkProtocol:
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

def cmd_scan():
    print("🔍 Ağdaki açık alıcılar taranıyor (UDP 50001)...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(2.0)
    sock.sendto(b"LAN_DISCOVER", ("255.255.255.255", DEFAULT_UDP_PORT))

    found = []
    start = time.time()
    while time.time() - start < 2.0:
        try:
            data, addr = sock.recvfrom(1024)
            text = data.decode('utf-8', errors='ignore')
            if text.startswith("LAN_OFFER:"):
                parts = text.split(":")
                found.append((addr[0], parts[2], parts[1]))
        except socket.timeout:
            break
    sock.close()

    if not found:
        print("❌ Ağda aktif alıcı bulunamadı.")
    else:
        print(f"✅ {len(found)} adet alıcı bulundu:")
        for ip, port, hname in found:
            print(f"   👉 {hname} -> IP: {ip} | Port: {port}")

def cmd_receive(save_dir, port):
    os.makedirs(save_dir, exist_ok=True)
    local_ip = get_local_ip()
    hostname = socket.gethostname()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(1)

    print("=" * 60)
    print("📥 LAN TRANSFER - ALICI MODU (CLI)")
    print(f"🖥️ Cihaz: {hostname} | IP: {local_ip} | Port: {port}")
    print(f"📁 Kayıt Dizini: {os.path.abspath(save_dir)}")
    print("=" * 60)
    print("Bağlantı bekleniyor... (Durdurmak için Ctrl+C)")

    try:
        while True:
            client, addr = server.accept()
            print(f"\n🔗 Bağlantı kuruldu: {addr[0]}")
            try:
                init = NetworkProtocol.recv_json(client)
                if not init or init.get("action") != "TRANSFER_START":
                    client.close()
                    continue

                total_files = init["total_files"]
                total_size = init["total_size"]
                sender = init.get("sender", addr[0])

                print(f"🚀 Gönderici: {sender} | {total_files} dosya | Toplam: {format_bytes(total_size)}")
                NetworkProtocol.send_json(client, {"status": "READY"})

                for i in range(total_files):
                    hdr = NetworkProtocol.recv_json(client)
                    if not hdr or hdr.get("action") != "FILE_HEADER":
                        break

                    rel_path = hdr["rel_path"]
                    size = hdr["size"]
                    target = os.path.join(save_dir, rel_path)
                    os.makedirs(os.path.dirname(target), exist_ok=True)

                    print(f"  [{i+1}/{total_files}] Alınıyor: {rel_path} ({format_bytes(size)}) ...", end="", flush=True)
                    NetworkProtocol.send_json(client, {"status": "OK"})

                    bytes_read = 0
                    with open(target, "wb") as f:
                        while bytes_read < size:
                            chunk = client.recv(min(BUFFER_SIZE, size - bytes_read))
                            if not chunk:
                                raise ConnectionError("Bağlantı koptu!")
                            f.write(chunk)
                            bytes_read += len(chunk)

                    NetworkProtocol.send_json(client, {"status": "FILE_OK"})
                    print(" TAMAMLANDI ✓")

                end_msg = NetworkProtocol.recv_json(client)
                if end_msg and end_msg.get("action") == "TRANSFER_END":
                    NetworkProtocol.send_json(client, {"status": "COMPLETE"})
                    print("🎉 Tüm dosyalar başarıyla alındı!\n")
            except Exception as e:
                print(f"❌ Transfer hatası: {e}")
            finally:
                client.close()
    except KeyboardInterrupt:
        print("\nAlıcı kapatıldı.")
    finally:
        server.close()

def cmd_send(target_ip, path, port):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print(f"❌ Belirtilen dosya veya klasör bulunamadı: {path}")
        return

    items_to_send = []
    if os.path.isfile(path):
        items_to_send.append({
            "path": path,
            "rel_path": os.path.basename(path),
            "size": os.path.getsize(path)
        })
    else:
        folder_name = os.path.basename(path)
        for root, _, files in os.walk(path):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.join(folder_name, os.path.relpath(full, path))
                items_to_send.append({
                    "path": full,
                    "rel_path": rel,
                    "size": os.path.getsize(full)
                })

    total_files = len(items_to_send)
    total_size = sum(x["size"] for x in items_to_send)

    print("=" * 60)
    print("📤 LAN TRANSFER - GÖNDERİCİ (CLI)")
    print(f"🎯 Hedef: {target_ip}:{port}")
    print(f"📦 Gönderilecek: {total_files} dosya | Toplam: {format_bytes(total_size)}")
    print("=" * 60)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(10.0)
        sock.connect((target_ip, port))
        sock.settimeout(None)

        NetworkProtocol.send_json(sock, {
            "action": "TRANSFER_START",
            "total_files": total_files,
            "total_size": total_size,
            "sender": socket.gethostname()
        })

        resp = NetworkProtocol.recv_json(sock)
        if not resp or resp.get("status") != "READY":
            print("❌ Alıcı hazır değil veya bağlantıyı reddetti.")
            return

        start_time = time.time()
        for idx, item in enumerate(items_to_send):
            print(f"  [{idx+1}/{total_files}] Gönderiliyor: {item['rel_path']} ({format_bytes(item['size'])}) ...", end="", flush=True)

            NetworkProtocol.send_json(sock, {
                "action": "FILE_HEADER",
                "rel_path": item["rel_path"],
                "size": item["size"]
            })

            file_resp = NetworkProtocol.recv_json(sock)
            if not file_resp or file_resp.get("status") != "OK":
                print(" HATA!")
                return

            with open(item["path"], "rb") as f:
                while True:
                    chunk = f.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)

            ack = NetworkProtocol.recv_json(sock)
            if not ack or ack.get("status") != "FILE_OK":
                print(" İLETİM HATASI!")
                return
            print(" GÖNDERİLDİ ✓")

        NetworkProtocol.send_json(sock, {"action": "TRANSFER_END"})
        NetworkProtocol.recv_json(sock)

        elapsed = time.time() - start_time
        speed = (total_size / (1024 * 1024)) / (elapsed or 0.001)
        print(f"\n🎉 Gönderim Tamamlandı! Süre: {elapsed:.1f} sn | Ortalama Hız: {speed:.1f} MB/s")

    except Exception as e:
        print(f"\n❌ Bağlantı hatası: {e}")
    finally:
        sock.close()

def main():
    parser = argparse.ArgumentParser(description="LAN Dosya Transfer Aracı")
    subparsers = parser.add_subparsers(dest="command")

    # scan
    subparsers.add_parser("scan", help="Ağdaki açık alıcıları ara")

    # receive
    p_recv = subparsers.add_parser("receive", help="Alıcı modunu başlat")
    p_recv.add_argument("save_dir", nargs="?", default="Gelen_Dosyalar", help="Kayıt klasörü")
    p_recv.add_argument("--port", type=int, default=DEFAULT_TCP_PORT, help="TCP Portu")

    # send
    p_send = subparsers.add_parser("send", help="Dosya veya klasör gönder")
    p_send.add_argument("target_ip", help="Hedef bilgisayarın IP adresi")
    p_send.add_argument("path", help="Gönderilecek dosya veya klasör yolu")
    p_send.add_argument("--port", type=int, default=DEFAULT_TCP_PORT, help="TCP Portu")

    args = parser.parse_args()
    if args.command == "scan":
        cmd_scan()
    elif args.command == "receive":
        cmd_receive(args.save_dir, args.port)
    elif args.command == "send":
        cmd_send(args.target_ip, args.path, args.port)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
