#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  TITAN OMNISCALE X v18 — DIAGNOSTICO DE RED PARA TERMUX        ║
║  Termux + Datos Moviles + Cline Connectivity Fix                ║
║                                                                  ║
║  Este script diagnostica por que Cline no puede comunicarse     ║
║  con el servidor TITAN en Termux cuando usas datos moviles.     ║
║                                                                  ║
║  USO:                                                            ║
║    python3 termux_network_diag.py               # Diagnostico   ║
║    python3 termux_network_diag.py --fix          # Auto-fix     ║
║    python3 termux_network_diag.py --test-server  # Probar server║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import socket
import subprocess
import json
import time
import threading
import signal
from datetime import datetime

# Colores ANSI
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    BG_RED  = "\033[41m"
    BG_GRN  = "\033[42m"
    BG_YEL  = "\033[43m"


def print_header(text):
    print(f"\n{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {text}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}\n")


def print_ok(text):
    print(f"  {C.GREEN}✓{C.RESET} {text}")


def print_fail(text):
    print(f"  {C.RED}✗{C.RESET} {text}")


def print_warn(text):
    print(f"  {C.YELLOW}⚠{C.RESET} {text}")


def print_info(text):
    print(f"  {C.BLUE}ℹ{C.RESET} {text}")


def print_step(text):
    print(f"\n{C.BOLD}{C.WHITE}▸ {text}{C.RESET}")


# ════════════════════════════════════════════════════════════════════
#  1. DETECCION DE PLATAFORMA
# ════════════════════════════════════════════════════════════════════

def detect_platform():
    """Detectar si estamos en Termux, proot, o Linux nativo."""
    print_step("Detectando plataforma")

    is_termux = os.path.exists("/data/data/com.termux")
    is_proot = os.path.exists("/data/data/com.termux/files/usr/bin/proot")
    is_android = 'ANDROID_ARGUMENT' in os.environ
    termux_prefix = os.environ.get("TERMUX_PREFIX", "")
    termux_app = os.environ.get("TERMUX_APP_PID", "")

    platform_info = {
        "is_termux": is_termux,
        "is_proot": is_proot,
        "is_android": is_android,
        "termux_prefix": termux_prefix,
    }

    if is_termux:
        print_ok(f"Termux detectado (PREFIX={termux_prefix or '/data/data/com.termux/files/usr'})")
    else:
        print_info("No se detecta Termux")

    if is_proot:
        print_warn("proot-distro detectado — las interfaces de red pueden estar limitadas")
    elif is_termux:
        print_ok("Termux nativo (sin proot)")

    if is_android:
        print_info("Android environment detectado via ANDROID_ARGUMENT")

    # Verificar si tenemos acceso a comandos de red
    for cmd in ["ip", "ifconfig", "curl", "ping", "netstat", "ss"]:
        try:
            result = subprocess.run(
                ["which", cmd], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                print_ok(f"Comando '{cmd}' disponible: {result.stdout.strip()}")
            else:
                print_fail(f"Comando '{cmd}' NO disponible")
        except Exception:
            print_fail(f"Comando '{cmd}' NO disponible")

    return platform_info


# ════════════════════════════════════════════════════════════════════
#  2. DETECCION DE INTERFACES DE RED
# ════════════════════════════════════════════════════════════════════

def detect_network_interfaces():
    """Detectar todas las interfaces de red y sus IPs."""
    print_step("Detectando interfaces de red")

    interfaces = {}

    # Metodo 1: ip addr show
    try:
        result = subprocess.run(
            ["ip", "addr", "show"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            current_iface = None
            for line in result.stdout.splitlines():
                import re
                iface_match = re.match(r'^\d+:\s+(\S+):', line)
                if iface_match:
                    current_iface = iface_match.group(1)
                    interfaces[current_iface] = {
                        "ipv4": [], "ipv6": [], "state": "UNKNOWN"
                    }
                    # Detectar estado UP/DOWN
                    if "UP" in line:
                        interfaces[current_iface]["state"] = "UP"
                    elif "DOWN" in line:
                        interfaces[current_iface]["state"] = "DOWN"

                if current_iface:
                    # IPv4
                    ipv4_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+/\d+)', line)
                    if ipv4_match:
                        interfaces[current_iface]["ipv4"].append(ipv4_match.group(1))
                    # IPv6
                    ipv6_match = re.search(r'inet6\s+(\S+)', line)
                    if ipv6_match:
                        interfaces[current_iface]["ipv6"].append(ipv6_match.group(1))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print_fail("No se pudo ejecutar 'ip addr show'")

    # Metodo 2: ifconfig (fallback)
    if not interfaces:
        try:
            result = subprocess.run(
                ["ifconfig"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import re
                current_iface = None
                for line in result.stdout.splitlines():
                    iface_match = re.match(r'^(\S+):?\s+flags', line)
                    if not iface_match:
                        iface_match = re.match(r'^(\S+)\s+Link', line)
                    if iface_match:
                        current_iface = iface_match.group(1)
                        if current_iface not in interfaces:
                            interfaces[current_iface] = {
                                "ipv4": [], "ipv6": [], "state": "UNKNOWN"
                            }
                    if current_iface:
                        ipv4_match = re.search(r'inet\s+(?:addr:)?(\d+\.\d+\.\d+\.\d+)', line)
                        if ipv4_match:
                            interfaces[current_iface]["ipv4"].append(ipv4_match.group(1))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print_fail("No se pudo ejecutar 'ifconfig'")

    # Metodo 3: /proc/net/fib_trie (ultimo recurso)
    if not interfaces:
        try:
            with open("/proc/net/fib_trie", "r") as f:
                content = f.read()
            import re
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if "/32 host LOCAL" in line and i > 0:
                    prev = lines[i - 1].strip()
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', prev)
                    if ip_match:
                        ip = ip_match.group(1)
                        iface_name = "proc_fib_trie"
                        if iface_name not in interfaces:
                            interfaces[iface_name] = {
                                "ipv4": [ip], "ipv6": [], "state": "UNKNOWN"
                            }
        except (FileNotFoundError, PermissionError):
            pass

    # Mostrar resultados
    if not interfaces:
        print_fail("No se pudieron detectar interfaces de red!")
        return interfaces

    # Clasificar interfaces
    mobile_prefixes = ("rmnet", "ccmni", "rmnet_data")
    wifi_prefixes = ("wlan",)
    usb_prefixes = ("usb", "rndis", "eth")
    loopback = ("lo",)

    for name, info in interfaces.items():
        if any(name.startswith(p) for p in mobile_prefixes):
            iface_type = f"{C.MAGENTA}[DATOS MOVILES]{C.RESET}"
        elif any(name.startswith(p) for p in wifi_prefixes):
            iface_type = f"{C.GREEN}[WiFi]{C.RESET}"
        elif any(name.startswith(p) for p in usb_prefixes):
            iface_type = f"{C.BLUE}[USB]{C.RESET}"
        elif name in loopback:
            iface_type = f"{C.DIM}[LOOPBACK]{C.RESET}"
        else:
            iface_type = f"{C.YELLOW}[OTRO]{C.RESET}"

        state = info["state"]
        state_icon = C.GREEN if state == "UP" else C.RED

        print(f"  {iface_type} {C.BOLD}{name}{C.RESET} [{state_icon}{state}{C.RESET}]")
        for ip in info["ipv4"]:
            print(f"    IPv4: {C.CYAN}{ip}{C.RESET}")
        for ip in info["ipv6"]:
            ip_display = ip.split("%")[0] if "%" in ip else ip
            print(f"    IPv6: {C.DIM}{ip_display}{C.RESET}")

    return interfaces


# ════════════════════════════════════════════════════════════════════
#  3. TEST DE DETECCION IP (TITAN get_local_ip)
# ════════════════════════════════════════════════════════════════════

def test_ip_detection():
    """Probar todos los metodos de deteccion de IP del TITAN server."""
    print_step("Probando metodos de deteccion de IP (TITAN server)")

    # Importar las funciones del server
    try:
        from src.server.server import (
            get_local_ip, get_network_info,
            _ip_from_udp_connect, _ip_from_udp_connect_ipv6,
            _ip_from_env, _ip_from_ip_addr, _ip_from_proc_net,
            _ip_from_ifconfig, _ip_from_netifaces,
        )
    except ImportError as e:
        print_fail(f"No se pudieron importar funciones del server: {e}")
        print_info("Asegurate de ejecutar este script desde la raiz del proyecto")
        return None

    methods = [
        ("UDP connect (8.8.8.8)", _ip_from_udp_connect),
        ("UDP connect IPv6", _ip_from_udp_connect_ipv6),
        ("ENV TITAN_BIND_IP", _ip_from_env),
        ("ip addr (interfaces)", _ip_from_ip_addr),
        ("/proc/net/fib_trie", _ip_from_proc_net),
        ("ifconfig", _ip_from_ifconfig),
        ("netifaces library", _ip_from_netifaces),
    ]

    best_ip = None
    for name, fn in methods:
        try:
            ip = fn()
            if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                print_ok(f"{name}: {C.GREEN}{ip}{C.RESET}")
                if best_ip is None:
                    best_ip = ip
            elif ip == "127.0.0.1":
                print_warn(f"{name}: {ip} (loopback — no util para Cline)")
            else:
                print_fail(f"{name}: sin resultado")
        except Exception as e:
            print_fail(f"{name}: ERROR — {e}")

    # Resultado final de get_local_ip()
    final_ip = get_local_ip()
    print(f"\n  {C.BOLD}IP recomendada por get_local_ip(): {C.CYAN}{final_ip}{C.RESET}")

    if final_ip == "127.0.0.1":
        print_warn("get_local_ip() retorno 127.0.0.1 — Cline NO podra conectarse desde otro dispositivo")
        print_info("Solucion: Configura TITAN_BIND_IP en tu archivo .env")
    else:
        print_ok(f"Cline deberia conectarse a: http://{final_ip}:5000/v1")

    return final_ip


# ════════════════════════════════════════════════════════════════════
#  4. TEST DE CONECTIVIDAD LOCAL
# ════════════════════════════════════════════════════════════════════

def test_loopback_connectivity():
    """Verificar si el loopback (127.0.0.1) funciona correctamente."""
    print_step("Test de conectividad loopback (localhost)")

    # Test 1: Bind a 127.0.0.1
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        print_ok(f"Bind a 127.0.0.1 exitoso (puerto {port})")
        s.close()
    except Exception as e:
        print_fail(f"Bind a 127.0.0.1 FALLO: {e}")
        print_warn("Esto es un problema grave — loopback no disponible")
        print_info("Posible fix: Verifica que /etc/hosts tenga '127.0.0.1 localhost'")
        return False

    # Test 2: Bind a 0.0.0.0
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
        print_ok(f"Bind a 0.0.0.0 exitoso (puerto {port})")
        s.close()
    except Exception as e:
        print_fail(f"Bind a 0.0.0.0 FALLO: {e}")
        return False

    # Test 3: Socket pair (comunicacion interna)
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(("127.0.0.1", port))

        conn, addr = server.accept()
        client.send(b"HELLO_TITAN")
        data = conn.recv(1024)

        if data == b"HELLO_TITAN":
            print_ok("Comunicacion loopback completa (cliente→servidor)")
        else:
            print_warn(f"Datos recibidos incorrectos: {data}")

        client.close()
        conn.close()
        server.close()
    except Exception as e:
        print_fail(f"Test de comunicacion loopback FALLO: {e}")
        return False

    return True


# ════════════════════════════════════════════════════════════════════
#  5. TEST DEL SERVIDOR TITAN
# ════════════════════════════════════════════════════════════════════

def test_titan_server():
    """Verificar si el servidor TITAN esta corriendo y es accesible."""
    print_step("Test del servidor TITAN")

    # Probar en puertos comunes
    ports_to_test = [5000, 8000, 8080, 3000]
    found_server = False

    for port in ports_to_test:
        for host in ["127.0.0.1", "0.0.0.0", "localhost"]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((host if host != "0.0.0.0" else "127.0.0.1", port))
                s.close()

                print_ok(f"Puerto {port} ABIERTO en {host}")

                # Probar endpoint /v1/models
                try:
                    import urllib.request
                    url = f"http://127.0.0.1:{port}/v1/models"
                    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = resp.read().decode()
                        if "titan" in data.lower() or "model" in data.lower():
                            print_ok(f"Endpoint /v1/models responde en puerto {port}")
                            print_info(f"TITAN server activo en: http://127.0.0.1:{port}/v1")
                            found_server = True
                        else:
                            print_warn(f"Puerto {port} responde pero no parece ser TITAN")
                except Exception as e:
                    print_warn(f"Puerto {port} abierto pero /v1/models fallo: {e}")
                    # Podria ser otro servicio
                    try:
                        import urllib.request
                        url = f"http://127.0.0.1:{port}/"
                        with urllib.request.urlopen(url, timeout=3) as resp:
                            print_info(f"Respuesta en /: {resp.read().decode()[:100]}")
                    except Exception:
                        pass

                break  # No need to test other hosts for this port

            except (ConnectionRefusedError, socket.timeout, OSError):
                pass

    if not found_server:
        print_warn("No se encontro el servidor TITAN corriendo")
        print_info("Para iniciar el servidor:")
        print_info("  python3 main_headless.py          # Headless (recomendado para Cline)")
        print_info("  python3 main.py                   # TUI (interfaz grafica)")
        print_info("  python3 logger_debug.py           # Con diagnostico")


# ════════════════════════════════════════════════════════════════════
#  6. TEST DE CONECTIVIDAD CON CLINE
# ════════════════════════════════════════════════════════════════════

def test_cline_connectivity():
    """Simular lo que Cline haria para conectarse al servidor TITAN."""
    print_step("Simulando conexion de Cline")

    port = 5000

    # Test 1: HTTP request a /v1/models (lo primero que hace Cline)
    try:
        import urllib.request
        url = f"http://127.0.0.1:{port}/v1/models"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode()
            print_ok(f"Cline→TITAN /v1/models: {C.GREEN}OK{C.RESET}")
            print_info(f"Modelos: {data[:200]}")
    except urllib.error.URLError as e:
        print_fail(f"Cline→TITAN /v1/models: FALLO — {e.reason}")
        if "Connection refused" in str(e.reason):
            print_warn("El servidor TITAN no esta corriendo en puerto 5000")
        elif "timed out" in str(e.reason):
            print_warn("Timeout — el servidor esta colgado o sobrecargado")
    except ConnectionRefusedError:
        print_fail("Cline→TITAN: Conexion rechazada — servidor no esta corriendo")
    except Exception as e:
        print_fail(f"Cline→TITAN: ERROR — {e}")

    # Test 2: HTTP POST a /v1/chat/completions (request de chat)
    try:
        import urllib.request
        url = f"http://127.0.0.1:{port}/v1/chat/completions"
        payload = json.dumps({
            "model": "titan-omniscale-x",
            "messages": [{"role": "user", "content": "test ping"}],
            "stream": False,
            "max_tokens": 10,
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode()
            print_ok(f"Cline→TITAN /v1/chat/completions: {C.GREEN}OK{C.RESET}")
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else ''
        if e.code == 429:
            print_warn(f"Cline→TITAN: Rate limit (429) — muchas requests rapidas")
            print_info("Solucion: Aumenta TITAN_RATE_LIMIT_CONCURRENT en .env")
        elif e.code == 503:
            print_fail(f"Cline→TITAN: Servicio no disponible (503) — RAM critica o modelo descargado")
            print_info(f"Respuesta: {body[:200]}")
        else:
            print_warn(f"Cline→TITAN: HTTP {e.code} — {body[:200]}")
    except Exception as e:
        # No imprimir error si el servidor no esta corriendo
        if "Connection refused" not in str(e):
            print_warn(f"Cline→TITAN chat: {e}")


# ════════════════════════════════════════════════════════════════════
#  7. TEST DE DNS Y CONECTIVIDAD EXTERNA
# ════════════════════════════════════════════════════════════════════

def test_external_connectivity():
    """Verificar si hay salida a internet (necesario para APIs externas)."""
    print_step("Test de conectividad externa (internet)")

    targets = [
        ("DNS Google", "8.8.8.8", 53),
        ("DNS Cloudflare", "1.1.1.1", 53),
        ("HTTP Google", "8.8.8.8", 80),
        ("HTTP Cloudflare", "1.1.1.1", 80),
    ]

    for name, host, port in targets:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((host, port))
            s.close()
            print_ok(f"{name} ({host}:{port}): accesible")
        except socket.timeout:
            print_fail(f"{name} ({host}:{port}): TIMEOUT")
        except ConnectionRefusedError:
            print_warn(f"{name} ({host}:{port}): conexion rechazada")
        except OSError as e:
            print_fail(f"{name} ({host}:{port}): ERROR — {e}")

    # DNS resolution test
    try:
        ip = socket.gethostbyname("google.com")
        print_ok(f"DNS resolucion: google.com → {ip}")
    except socket.gaierror:
        print_fail("DNS resolucion fallo — no hay DNS")
        print_info("Esto puede causar que Cline no encuentre APIs externas")

    # HTTP test (si curl esta disponible)
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", "5", "https://api.openai.com"],
            capture_output=True, text=True, timeout=10
        )
        code = result.stdout.strip()
        if code:
            print_info(f"HTTP a api.openai.com: status {code}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ════════════════════════════════════════════════════════════════════
#  8. CHECK DE PERMISOS TERMUX
# ════════════════════════════════════════════════════════════════════

def check_termux_permissions():
    """Verificar permisos de red en Termux."""
    print_step("Verificando permisos de red en Termux")

    # Verificar /proc/net acceso
    proc_files = [
        "/proc/net/dev",
        "/proc/net/fib_trie",
        "/proc/net/route",
        "/proc/net/tcp",
    ]
    for f in proc_files:
        if os.path.exists(f):
            try:
                with open(f, "r") as fh:
                    _ = fh.read(100)
                print_ok(f"Lectura de {f}: OK")
            except PermissionError:
                print_fail(f"Lectura de {f}: PERMISO DENEGADO")
                print_info(f"  Esto impide detectar la IP automaticamente")
        else:
            print_warn(f"{f}: no existe")

    # Verificar si termux-storage-get esta disponible
    try:
        result = subprocess.run(
            ["which", "termux-storage-get"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            print_ok("termux-storage-get disponible")
        else:
            print_warn("termux-storage-get NO disponible")
            print_info("  Instala con: pkg install termux-api")
    except Exception:
        pass

    # Verificar permisos de storage
    storage_dir = os.path.expanduser("~/storage")
    if os.path.exists(storage_dir):
        print_ok(f"~/storage existe — permisos de storage activos")
    else:
        print_warn("~/storage NO existe")
        print_info("  Ejecuta: termux-setup-storage")

    # Verificar Android network security
    try:
        # En Android 9+, el trafico cleartext (HTTP) puede estar bloqueado
        result = subprocess.run(
            ["getprop", "ro.build.version.sdk"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            sdk = int(result.stdout.strip())
            print_info(f"Android SDK version: {sdk}")
            if sdk >= 28:
                print_warn("Android 9+ — el trafico HTTP (no-HTTPS) puede estar restringido")
                print_info("  TITAN server usa HTTP — debe funcionar en localhost")
                print_info("  Si Cline esta en otro dispositivo, necesitas HTTPS o configuracion especial")
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════
#  9. DIAGNOSTICO COMPLETO
# ════════════════════════════════════════════════════════════════════

def run_full_diagnostic():
    """Ejecutar diagnostico completo de red."""
    print(f"""
{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════════════╗
║  TITAN OMNISCALE X v18 — DIAGNOSTICO DE RED                     ║
║  Termux + Datos Moviles + Cline                                  ║
║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                            ║
╚══════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    # 1. Plataforma
    platform_info = detect_platform()

    # 2. Interfaces de red
    interfaces = detect_network_interfaces()

    # 3. Deteccion de IP
    detected_ip = test_ip_detection()

    # 4. Loopback
    loopback_ok = test_loopback_connectivity()

    # 5. Servidor TITAN
    test_titan_server()

    # 6. Conectividad Cline
    test_cline_connectivity()

    # 7. Conectividad externa
    test_external_connectivity()

    # 8. Permisos
    if platform_info.get("is_termux"):
        check_termux_permissions()

    # ═════════════════════════════════════════════════════════════════
    #  RESUMEN Y RECOMENDACIONES
    # ═════════════════════════════════════════════════════════════════

    print_header("RESUMEN Y RECOMENDACIONES")

    issues = []
    solutions = []

    # Analizar interfaces
    has_mobile = any(
        name.startswith(("rmnet", "ccmni"))
        for name in interfaces
    )
    has_wifi = any(
        name.startswith("wlan")
        for name in interfaces
    )
    has_non_loopback_ip = any(
        ip
        for name, info in interfaces.items()
        if name != "lo"
        for ip in info.get("ipv4", [])
        if not ip.startswith("127.")
    )

    if has_mobile and not has_wifi:
        issues.append("Solo datos moviles detectados (sin WiFi)")
        solutions.append("Cline en el MISMO telefono: usa http://127.0.0.1:5000/v1")

    if detected_ip == "127.0.0.1" and has_non_loopback_ip:
        issues.append("get_local_ip() no detecta la IP de datos moviles")
        solutions.append("Configura TITAN_BIND_IP en .env con tu IP")

    if not loopback_ok:
        issues.append("Loopback (127.0.0.1) no funciona")
        solutions.append("Verifica /etc/hosts y permisos de red")

    if not issues:
        print_ok("No se detectaron problemas de red!")
        print_info(f"IP recomendada para Cline: http://{detected_ip}:5000/v1")
    else:
        print_warn("Problemas detectados:")
        for i, issue in enumerate(issues, 1):
            print(f"  {C.RED}{i}.{C.RESET} {issue}")

        print(f"\n{C.BOLD}Soluciones:{C.RESET}")
        for i, sol in enumerate(solutions, 1):
            print(f"  {C.GREEN}{i}.{C.RESET} {sol}")

    # Recomendaciones especificas para datos moviles
    print(f"\n{C.BOLD}{C.CYAN}Configuracion recomendada para datos moviles:{C.RESET}")

    # Buscar IP de datos moviles
    mobile_ip = None
    for name, info in interfaces.items():
        if name.startswith(("rmnet", "ccmni")):
            for ip in info.get("ipv4", []):
                mobile_ip = ip.split("/")[0] if "/" in ip else ip
                break
        if mobile_ip:
            break

    if mobile_ip:
        print(f"""
  {C.GREEN}# En tu archivo .env, agrega:{C.RESET}
  TITAN_BIND_IP={mobile_ip}

  {C.GREEN}# Configura Cline con:{C.RESET}
  {C.CYAN}Base URL:{C.RESET} http://127.0.0.1:5000/v1    # Si Cline esta en el MISMO telefono
  {C.CYAN}Base URL:{C.RESET} http://{mobile_ip}:5000/v1  # Si Cline esta en OTRO dispositivo

  {C.GREEN}# Para conectar desde otro dispositivo en la misma red movil:{C.RESET}
  {C.YELLOW}NOTA:{C.RESET} La IP de datos moviles suele ser privada (10.x.x.x o 100.x.x.x)
  y puede no ser accesible desde otros dispositivos. Necesitas:
    1. Compartir internet via hotspot WiFi desde tu telefono
    2. Conectar el otro dispositivo al hotspot
    3. Usar la IP del hotspot (usualmente 192.168.43.1)
""")
    else:
        print(f"""
  {C.GREEN}# Si Cline esta en el MISMO telefono (Termux):{C.RESET}
  {C.CYAN}Base URL:{C.RESET} http://127.0.0.1:5000/v1

  {C.GREEN}# Si no se detecta la IP automaticamente:{C.RESET}
  1. Ejecuta: ip addr show
  2. Busca tu IP (inet 10.x.x.x o similar)
  3. Agrega a .env: TITAN_BIND_IP=tu_ip_aqui

  {C.GREEN}# Para compartir con otro dispositivo:{C.RESET}
  1. Activa hotspot WiFi en tu telefono
  2. El otro dispositivo se conecta al hotspot
  3. Usa la IP del gateway del hotspot
  4. Normalmente: http://192.168.43.1:5000/v1
""")

    # Guardar diagnostico
    diag_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"network_diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    diag_data = {
        "timestamp": datetime.now().isoformat(),
        "platform": platform_info,
        "interfaces": interfaces,
        "detected_ip": detected_ip,
        "loopback_ok": loopback_ok,
        "issues": issues,
        "solutions": solutions,
        "mobile_ip": mobile_ip,
    }
    with open(diag_file, "w") as f:
        json.dump(diag_data, f, indent=2, default=str)
    print(f"\n  Diagnostico guardado en: {C.CYAN}{diag_file}{C.RESET}")


# ════════════════════════════════════════════════════════════════════
#  AUTO-FIX
# ════════════════════════════════════════════════════════════════════

def run_auto_fix():
    """Intentar arreglar problemas de red automaticamente."""
    print_header("AUTO-FIX: Corrigiendo problemas de red")

    # 1. Detectar IP
    print_step("Paso 1: Detectando IP")
    from src.server.server import get_local_ip, _ip_from_ip_addr, _ip_from_proc_net

    ip = get_local_ip()
    if ip == "127.0.0.1":
        print_warn("get_local_ip() retorno 127.0.0.1 — buscando IP alternativa")
        alt_ip = _ip_from_ip_addr() or _ip_from_proc_net()
        if alt_ip:
            print_ok(f"IP alternativa encontrada: {alt_ip}")
            ip = alt_ip
        else:
            print_fail("No se pudo encontrar IP alternativa")
            print_info("Configura manualmente TITAN_BIND_IP en .env")
            return
    else:
        print_ok(f"IP detectada: {ip}")

    # 2. Actualizar .env si existe
    print_step("Paso 2: Actualizando .env")
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    env_example = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.example")

    if not os.path.exists(env_file) and os.path.exists(env_example):
        print_warn("No existe .env — copiando desde .env.example")
        import shutil
        shutil.copy(env_example, env_file)
        print_ok(".env creado desde .env.example")

    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            content = f.read()

        if "TITAN_BIND_IP" in content:
            # Actualizar valor existente
            import re
            content = re.sub(
                r'TITAN_BIND_IP=.*',
                f'TITAN_BIND_IP={ip}',
                content
            )
            print_ok(f"TITAN_BIND_IP actualizado a {ip}")
        else:
            # Agregar nueva variable
            content += f"\n# ── BIND IP (auto-configurado por termux_network_diag) ──\n"
            content += f"# IP detectada para datos moviles\n"
            content += f"TITAN_BIND_IP={ip}\n"
            print_ok(f"TITAN_BIND_IP={ip} agregado a .env")

        with open(env_file, "w") as f:
            f.write(content)
    else:
        print_warn("No se encontro .env ni .env.example")
        print_info(f"Agrega manualmente: TITAN_BIND_IP={ip}")

    # 3. Verificar puerto 5000
    print_step("Paso 3: Verificando puerto 5000")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.bind(("0.0.0.0", 5000))
        s.close()
        print_ok("Puerto 5000 disponible")
    except OSError as e:
        if "Address already in use" in str(e) or "98" in str(e):
            print_warn("Puerto 5000 en uso — probablemente TITAN ya esta corriendo")
            print_info("Si no responde, detiene el proceso anterior y reintenta")
        else:
            print_fail(f"Puerto 5000 error: {e}")

    # 4. Instrucciones para Cline
    print_step("Paso 4: Configuracion de Cline")
    print(f"""
  {C.BOLD}{C.GREEN}CONFIGURACION DE CLINE:{C.RESET}

  Si Cline esta en el {C.BOLD}MISMO telefono{C.RESET} (Termux):
    {C.CYAN}Base URL:{C.RESET}   http://127.0.0.1:5000/v1
    {C.CYAN}API Key:{C.RESET}    cualquiera (ej: sk-titan-local)
    {C.CYAN}Model:{C.RESET}      titan-omniscale-x

  Si Cline esta en {C.BOLD}OTRO dispositivo{C.RESET} via hotspot:
    {C.CYAN}Base URL:{C.RESET}   http://{ip}:5000/v1
    {C.CYAN}API Key:{C.RESET}    cualquiera (ej: sk-titan-local)
    {C.CYAN}Model:{C.RESET}      titan-omniscale-x

  {C.YELLOW}IMPORTANTE para datos moviles:{C.RESET}
    1. Si no tienes WiFi, Cline DEBE estar en el mismo telefono
    2. Usa 127.0.0.1 (localhost) como Base URL
    3. La IP de datos moviles NO es accesible desde fuera
    4. Para acceso externo: activa hotspot WiFi
""")


# ════════════════════════════════════════════════════════════════════
#  TEST SERVER RAPIDO
# ════════════════════════════════════════════════════════════════════

def test_server_quick():
    """Iniciar un servidor de prueba rapido para verificar conectividad."""
    print_header("SERVIDOR DE PRUEBA RAPIDA")
    print_info("Iniciando servidor de prueba en puerto 5999...")
    print_info("Esto verifica si Cline puede conectarse a Termux\n")

    from http.server import HTTPServer, BaseHTTPRequestHandler

    class QuickHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            response = json.dumps({
                "status": "ok",
                "message": "TITAN test server — Cline puede conectarse!",
                "path": self.path,
                "client_ip": self.client_address[0],
                "timestamp": datetime.now().isoformat(),
            })
            self.wfile.write(response.encode())

        def do_POST(self):
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode() if content_length else ""
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            response = json.dumps({
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Test OK — Cline puede comunicarse con TITAN!"
                    },
                    "finish_reason": "stop"
                }],
                "model": "titan-omniscale-x-test",
            })
            self.wfile.write(response.encode())

        def log_message(self, format, *args):
            print(f"  {C.GREEN}[TEST SERVER]{C.RESET} {args[0]}")

    try:
        server = HTTPServer(("0.0.0.0", 5999), QuickHandler)
        print_ok("Servidor de prueba iniciado en http://0.0.0.0:5999")

        # Obtener IP
        from src.server.server import get_local_ip
        ip = get_local_ip()
        print_info(f"IP detectada: {ip}")
        print_info(f"Prueba desde otra terminal: curl http://127.0.0.1:5999/test")
        print_info(f"Configura Cline temporal: http://127.0.0.1:5999/v1")
        print(f"\n  {C.YELLOW}Ctrl+C para detener{C.RESET}\n")

        server.serve_forever()
    except OSError as e:
        print_fail(f"No se pudo iniciar servidor: {e}")
    except KeyboardInterrupt:
        print_info("\nServidor detenido")


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="TITAN OMNISCALE X v18 — Diagnostico de Red para Termux"
    )
    parser.add_argument(
        '--fix', action='store_true',
        help='Auto-fix: configurar TITAN_BIND_IP y .env'
    )
    parser.add_argument(
        '--test-server', action='store_true',
        help='Iniciar servidor de prueba rapida (puerto 5999)'
    )
    args = parser.parse_args()

    if args.test_server:
        test_server_quick()
    elif args.fix:
        run_auto_fix()
    else:
        run_full_diagnostic()
