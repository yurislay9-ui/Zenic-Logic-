import sys
import os
import platform

# Asegurar que src sea importable desde Buildozer
sys.path.insert(0, os.path.dirname(__file__))

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Label as ButtonLabel
from kivy.uix.button import Button
from kivy.uix.scrolllabel import ScrollLabel
import threading
import socket

# Detectar plataforma
IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ or 'android' in sys.modules or platform.system() == 'Linux'


class TitanApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical', padding=30, spacing=20)
        self.ip_label = Label(
            text="TITAN OMNISCALE X - Motor Logico",
            font_size='18sp',
            size_hint=(1, 0.3)
        )
        self.status = Label(
            text="Motor Apagado",
            font_size='16sp',
            size_hint=(1, 0.2)
        )
        self.btn = Button(
            text="INICIAR TITAN OMNISCALE X",
            font_size='20sp',
            size_hint=(1, 0.5)
        )
        self.btn.bind(on_press=self.start_engine)

        self.layout.add_widget(self.ip_label)
        self.layout.add_widget(self.status)
        self.layout.add_widget(self.btn)
        return self.layout

    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _run_server(self):
        """Ejecuta el servidor uvicorn en modo desktop, o motor local en Android."""
        try:
            import asyncio
            import uvicorn
            from src.api.server import app

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            config = uvicorn.Config(app, host="0.0.0.0", port=5000, loop=loop)
            server = uvicorn.Server(config)
            loop.call_soon_threadsafe(self._mark_active)
            loop.run_until_complete(server.serve())
        except ImportError:
            # Modo Android: fastapi/uvicorn no disponibles, ejecutar motor local
            self._run_local_engine()

    def _run_local_engine(self):
        """Motor local para Android sin servidor HTTP."""
        try:
            from src.core.orchestrator import TitanOrchestrator
            self.orch = TitanOrchestrator()
            self._mark_active("Motor Activo (modo local)")
        except Exception as e:
            self.status.text = f"Error: {str(e)[:50]}"

    def _mark_active(self, msg="Motor Activo - Escuchando en puerto 5000"):
        """Actualiza la UI cuando el servidor está listo."""
        self.status.text = msg

    def start_engine(self, instance):
        self.btn.disabled = True
        self.status.text = "Iniciando Nucleo Logico..."
        ip = self.get_ip()
        self.ip_label.text = f"Conecta Cline a: http://{ip}:5000/v1"
        threading.Thread(target=self._run_server, daemon=True).start()


if __name__ == '__main__':
    TitanApp().run()
