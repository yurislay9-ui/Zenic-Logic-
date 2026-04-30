import sys, os
# Asegurar que src sea importable desde Buildozer
sys.path.insert(0, os.path.dirname(__file__))

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
import threading, socket
import uvicorn
from src.api.server import app


class TitanApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical', padding=30, spacing=20)
        self.ip_label = Label(text="Conecta Cline a: http://000.000.000.000:5000/v1", font_size='18sp')
        self.status = Label(text="Motor Apagado", font_size='16sp')
        self.btn = Button(text="INICIAR TITAN OMNISCALE X", font_size='20sp', size_hint=(1, 0.5))
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
        """Ejecuta uvicorn en el hilo daemon y actualiza el estado al confirmar inicio."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(app, host="0.0.0.0", port=5000, loop=loop)
        server = uvicorn.Server(config)
        # Marcar como activo una vez que el servidor arranque
        loop.call_soon_threadsafe(self._mark_active)
        loop.run_until_complete(server.serve())

    def _mark_active(self):
        """Actualiza la UI cuando el servidor está realmente listo."""
        self.status.text = "Motor Activo - Escuchando en puerto 5000"

    def start_engine(self, instance):
        self.btn.disabled = True
        self.status.text = "Iniciando Núcleo Lógico..."
        self.ip_label.text = f"Conecta Cline a: http://{self.get_ip()}:5000/v1"
        threading.Thread(target=self._run_server, daemon=True).start()
        # No actualizamos a "Activo" aquí; se actualiza vía callback cuando uvicorn arranca


if __name__ == '__main__':
    TitanApp().run()
