"""
TITAN OMNISCALE X - Aplicacion Android con Kivy
Motor Logico de Razonamiento Quirurgico

Version Android (Buildozer): Todo el motor funciona localmente
sin dependencias nativas (pydantic, fastapi, tree-sitter, etc.)
"""
import sys
import os

# Asegurar que src sea importable
sys.path.insert(0, os.path.dirname(__file__))

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
import threading
import socket


class TitanApp(App):
    """Aplicacion TITAN OMNISCALE X con interfaz Kivy."""

    def build(self):
        self.engine = None
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=15)

        # Titulo
        self.title_label = Label(
            text="[b]TITAN OMNISCALE X[/b]\nMotor Logico Quirurgico",
            font_size='20sp', markup=True, size_hint=(1, 0.15)
        )

        # Campo de entrada
        self.input_field = TextInput(
            hint_text="Escribe tu instruccion (ej: 'optimizar auth.py')",
            multiline=False, font_size='16sp', size_hint=(1, 0.1)
        )
        self.input_field.bind(on_text_validate=self.process_command)

        # Boton ejecutar
        self.btn = Button(
            text="EJECUTAR MOTOR",
            font_size='18sp', size_hint=(1, 0.1)
        )
        self.btn.bind(on_press=self.process_command)

        # Area de resultados
        scroll = ScrollView(size_hint=(1, 0.65))
        self.output_label = Label(
            text="Motor listo. Escribe un comando para iniciar.",
            font_size='14sp', size_hint_y=None, valign='top',
        )
        self.output_label.bind(
            width=lambda *x: setattr(self.output_label, 'text_size', (self.output_label.width, None))
        )
        self.output_label.bind(texture_size=self.output_label.setter('size'))
        scroll.add_widget(self.output_label)

        self.layout.add_widget(self.title_label)
        self.layout.add_widget(self.input_field)
        self.layout.add_widget(self.btn)
        self.layout.add_widget(scroll)
        return self.layout

    def process_command(self, instance):
        """Procesa un comando del usuario a traves del motor."""
        msg = self.input_field.text.strip()
        if not msg:
            return

        self.output_label.text = f"Procesando: {msg}..."
        self.btn.disabled = True

        # Ejecutar en hilo separado
        threading.Thread(target=self._execute_engine, args=(msg,), daemon=True).start()

    def _execute_engine(self, msg):
        """Ejecuta el motor en un hilo y actualiza la UI."""
        try:
            if self.engine is None:
                from src.core.local_engine import TitanEngine
                self.engine = TitanEngine()

            result = self.engine.execute(msg)
            output = (
                f"TITAN OMNISCALE X\n"
                f"{'='*40}\n"
                f"Estado: {result['status']}\n"
                f"Hash: {result.get('hash', 'N/A')}\n"
                f"Error: {result.get('error', 'Ninguno')}\n"
                f"{'='*40}\n"
                f"Codigo generado:\n{result.get('code', '')}"
            )
        except Exception as e:
            output = f"Error del motor: {str(e)}"

        # Actualizar UI desde el hilo principal
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: self._update_output(output))

    def _update_output(self, text):
        self.output_label.text = text
        self.btn.disabled = False


if __name__ == '__main__':
    TitanApp().run()
