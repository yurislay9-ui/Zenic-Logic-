"""
TITAN OMNISCALE X - Motor de IA Quirurgico Local v16
Servidor OpenAI-Compatible para Cline, Aide, OpenCode y mas.

Usa modulos src/core/ con Z3 SMT Solver (con fallback AC-3),
MCTS real, Ejecucion Simbolica real, Timeout enforcement real,
Cache de Teoremas con Skeleton Hash, Protocolo Abortivo,
y Razonamiento Parcial con tool_calls.

Modo de uso:
  1. Pulsa INICIAR MOTOR
  2. Conecta Cline/Aide a: http://TU_IP:5000/v1
  3. El motor procesa tus peticiones con 8 niveles de razonamiento
"""

import os
import logging
import threading
import atexit

# Cargar .env ANTES de cualquier otro import (variables de entorno)
from src.core.env_loader import load_env
load_env()

from src.core.shared.contracts import HAS_Z3
from src.core.shared.db_initializer import initialize_databases

# Use DAGOrchestrator (v16) as primary, with TitanOrchestrator (v16) as fallback
try:
    from src.core.dag_orchestrator import DAGOrchestrator as _Orchestrator
except ImportError:
    from src.core.orchestrator import TitanOrchestrator as _Orchestrator

from src.server import (
    TitanHTTPHandler, ThreadedHTTPServer,
    get_local_ip, configure_handler,
)

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TITAN")

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ


# ============================================================
#  INTERFAZ KIVY
# ============================================================

class TitanApp(App):
    """TITAN OMNISCALE X v16 con servidor OpenAI-compatible."""

    def build(self):
        self.engine = _Orchestrator()
        self.server = None
        self.server_running = False
        self.log_lines = []

        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)

        solver_name = "Z3" if HAS_Z3 else "AC-3"

        self.title_label = Label(
            text=f"[b]TITAN OMNISCALE X v16[/b]\nMotor de IA Quirurgico Local ({solver_name})",
            font_size='22sp', markup=True, size_hint=(1, 0.12),
            color=(0.2, 0.8, 1, 1))

        self.ip_label = Label(
            text="Conecta Cline/Aide/OpenCode a:\nhttp://0.0.0.0:5000/v1",
            font_size='16sp', size_hint=(1, 0.1),
            color=(1, 1, 0.5, 1))

        self.status_label = Label(
            text="Motor Apagado", font_size='16sp', size_hint=(1, 0.06),
            color=(1, 0.5, 0.5, 1))

        self.btn = Button(
            text="INICIAR MOTOR TITAN v16", font_size='20sp', size_hint=(1, 0.1),
            background_color=(0.1, 0.5, 0.9, 1))
        self.btn.bind(on_press=self.toggle_engine)

        self.input_field = TextInput(
            hint_text="Prueba local: 'crear modulo auth.py'",
            multiline=False, font_size='14sp', size_hint=(1, 0.08))
        self.input_field.bind(on_text_validate=self.test_local)

        self.test_btn = Button(
            text="PROBAR LOCALMENTE", font_size='14sp', size_hint=(1, 0.06),
            background_color=(0.3, 0.7, 0.3, 1))
        self.test_btn.bind(on_press=self.test_local)

        scroll = ScrollView(size_hint=(1, 0.48))
        self.log_label = Label(
            text=f"Motor v16 listo. Pulsa INICIAR MOTOR para activar el servidor.\n\n"
                 f"NOVEDADES v16:\n"
                 f"- {solver_name} SMT Solver (Z3 si disponible, AC-3 fallback)\n"
                 f"- MCTS real (UCB1, 100 simulaciones, depth 5)\n"
                 f"- Ejecucion Simbolica Acotada real\n"
                 f"- Timeout enforcement real (15s quirurgico, 5s moderado)\n"
                 f"- K-Paths basado en grafo de dependencias\n"
                 f"- Protocolo Abortivo (auto-subdivision en timeout)\n"
                 f"- Razonamiento Parcial con tool_calls\n"
                 f"- Cache de Teoremas con Skeleton Hash\n"
                 f"- Configuracion YAML conectada\n"
                 f"- MacroRouter con firmas topologicas del AST\n"
                 f"- Generacion de codigo contextual\n\n"
                 f"COMO CONECTAR CLINE:\n"
                 f"1. Inicia el motor en esta app\n"
                 f"2. En VS Code, configura Cline:\n"
                 f"   - API Provider: OpenAI Compatible\n"
                 f"   - Base URL: http://TU_IP:5000/v1\n"
                 f"   - Model: titan-omniscale-x\n"
                 f"3. Cline enviara peticiones a tu telefono",
            font_size='12sp', size_hint_y=None, valign='top')
        self.log_label.bind(
            width=lambda *x: setattr(self.log_label, 'text_size', (self.log_label.width, None)))
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        scroll.add_widget(self.log_label)

        layout.add_widget(self.title_label)
        layout.add_widget(self.ip_label)
        layout.add_widget(self.status_label)
        layout.add_widget(self.btn)
        layout.add_widget(self.input_field)
        layout.add_widget(self.test_btn)
        layout.add_widget(scroll)
        return layout

    def toggle_engine(self, instance):
        if self.server_running:
            self._stop_engine()
        else:
            self._start_engine()

    def _start_engine(self):
        ip = get_local_ip()
        self.ip_label.text = f"Conecta Cline/Aide/OpenCode a:\nhttp://{ip}:5000/v1"
        self.status_label.text = "Iniciando motor v16..."
        self.status_label.color = (1, 1, 0.5, 1)
        self.btn.disabled = True

        # Configurar handler compartido con rate limiter básico para Kivy
        rate_limiter = RateLimiter(
            max_requests_per_minute=30,
            burst_size=5,
            global_max_concurrent=10,
        )
        configure_handler(self.engine, governor=None, platform_tag="kivy",
                          rate_limiter=rate_limiter)
        def run_server():
            try:
                self.server = ThreadedHTTPServer(('0.0.0.0', 5000), TitanHTTPHandler)
                self.server_running = True
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._update_status_running(ip))
                self.server.serve_forever()
            except OSError as e:
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._update_status_error(str(e)))
            except Exception as e:
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._update_status_error(str(e)))

        threading.Thread(target=run_server, daemon=True).start()

    def _stop_engine(self):
        if self.server:
            self.server.shutdown()
            self.server = None
        self.server_running = False
        self.status_label.text = "Motor Apagado"
        self.status_label.color = (1, 0.5, 0.5, 1)
        self.btn.text = "INICIAR MOTOR TITAN v16"
        self.btn.background_color = (0.1, 0.5, 0.9, 1)
        self.btn.disabled = False
        self._add_log("Motor detenido.")

    def _update_status_running(self, ip):
        solver_name = "Z3" if HAS_Z3 else "AC-3"
        self.status_label.text = f"Motor v16 ACTIVO ({solver_name}) - {ip}:5000"
        self.status_label.color = (0.3, 1, 0.3, 1)
        self.btn.text = "DETENER MOTOR"
        self.btn.background_color = (0.9, 0.3, 0.1, 1)
        self.btn.disabled = False
        self._add_log(f"Motor v16 activo. {solver_name} + MCTS + SymbolicExec reales.")

    def _update_status_error(self, error):
        self.status_label.text = f"Error: {error}"
        self.status_label.color = (1, 0.3, 0.3, 1)
        self.btn.text = "REINTENTAR"
        self.btn.background_color = (0.1, 0.5, 0.9, 1)
        self.btn.disabled = False
        self._add_log(f"Error: {error}")

    def test_local(self, instance):
        msg = self.input_field.text.strip()
        if not msg:
            return
        self._add_log(f"\n>> Local: {msg}")
        self.test_btn.disabled = True
        self.input_field.text = ""
        threading.Thread(target=self._run_local_test, args=(msg,), daemon=True).start()

    def _run_local_test(self, msg):
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self.engine.execute(msg))
            loop.close()
            solver_name = "Z3" if HAS_Z3 else "AC-3"
            output = f"TITAN v16 - {result['status']}\n"
            output += f"Route: {result.get('route', 'N/A')} | Crit: {result.get('criticality', 'N/A')}\n"
            output += f"Time: {result.get('processing_time_ms', 0)}ms | Hash: {result.get('hash', 'N/A')}\n"
            output += f"Solver({solver_name}): {result.get('solver_status', 'N/A')} | MCTS: {result.get('mcts_simulations', 0)} sims\n"
            if result.get('paths_explored'):
                output += f"Paths: {result.get('paths_explored', 0)} explored, {result.get('paths_pruned', 0)} pruned\n"
            if result.get('partial_reasoning'):
                output += "PROTOCOL: Razonamiento Parcial - subdividiendo tarea\n"
            if result.get('explanations'):
                for exp in result['explanations']:
                    output += f"  {exp}\n"
            if result.get('code'):
                output += f"\nCode:\n{result['code']}\n"
            if result.get('error'):
                output += f"\nError: {result['error']}\n"
        except Exception as e:
            output = f"Error: {str(e)}"
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._update_test_result(output))

    def _update_test_result(self, text):
        self._add_log(text)
        self.test_btn.disabled = False

    def _add_log(self, text):
        self.log_lines.append(text)
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-200:]
        self.log_label.text = "\n".join(self.log_lines)


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================

def _cleanup():
    """Graceful shutdown: stop server, close DB connections."""
    try:
        if hasattr(TitanApp, '_instance') and TitanApp._instance:
            app_inst = TitanApp._instance
            if app_inst.server:
                app_inst.server.shutdown()
    except Exception:
        pass
    try:
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
    except Exception:
        pass

atexit.register(_cleanup)

if __name__ == '__main__':
    initialize_databases()
    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info("TITAN OMNISCALE X v16.0 - Local Surgical AI Engine")
    logger.info(f"Solver: {solver_name} | MCTS Real | Symbolic Exec Real | Timeout Real | Skeleton Hash")
    logger.info("OpenAI-compatible server for Cline, Aide, OpenCode")
    TitanApp().run()
