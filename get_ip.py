import socket

def get_local_ip():
    """獲取本機的本地 IP 地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 連接到一個遠程地址（不會實際發送數據）
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    ip = get_local_ip()
    print(f"\n{'='*50}")
    print(f"你的本地 IP 地址是: {ip}")
    print(f"在手機瀏覽器中訪問: http://{ip}:5000")
    print(f"{'='*50}\n")


