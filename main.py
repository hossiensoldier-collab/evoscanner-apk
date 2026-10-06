"""EvoScanner Android App — Kivy wrapper"""
import os
import sys
import subprocess
import threading
from pathlib import Path

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.core.window import Window

Window.clearcolor = (0.05, 0.07, 0.09, 1)

# مسیر پروژه در APK
try:
    from android.storage import app_storage_path
    APP_DIR = Path(app_storage_path())
except Exception:
    APP_DIR = Path.home() / "evoscanner"


class OutputView(ScrollView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.ti = TextInput(
            text="",
            readonly=True,
            background_color=(0.09, 0.11, 0.13, 1),
            foreground_color=(0.79, 0.82, 0.85, 1),
            font_size="11sp",
            size_hint_y=None,
        )
        self.ti.bind(minimum_height=self.ti.setter("height"))
        self.add_widget(self.ti)

    def append(self, text):
        self.ti.text += text + "\n"
        self.ti.cursor = (0, len(self.ti.text))

    def clear(self):
        self.ti.text = ""


class EvoApp(App):
    def build(self):
        self.title = "EvoScanner"
        root = BoxLayout(orientation="vertical")

        # تب‌ها
        tabs = TabbedPanel(do_default_tab=False)
        tabs.tab_width = 90

        # تب جستجو
        t1 = TabbedPanelItem(text="Search")
        t1.add_widget(self._search_tab())
        tabs.add_widget(t1)

        # تب مرتبط
        t2 = TabbedPanelItem(text="Related")
        t2.add_widget(self._related_tab())
        tabs.add_widget(t2)

        # تب پرسش
        t3 = TabbedPanelItem(text="Ask")
        t3.add_widget(self._ask_tab())
        tabs.add_widget(t3)

        # تب گراف
        t4 = TabbedPanelItem(text="Graph")
        t4.add_widget(self._graph_tab())
        tabs.add_widget(t4)

        # تب سیستم
        t5 = TabbedPanelItem(text="System")
        t5.add_widget(self._system_tab())
        tabs.add_widget(t5)

        root.add_widget(tabs)

        # خروجی مشترک
        self.output = OutputView(size_hint_y=None, height=240)
        root.add_widget(self.output)

        # دکمه پاک
        btn_clear = Button(text="Clear output", size_hint_y=None, height=40)
        btn_clear.bind(on_press=lambda x: self.output.clear())
        root.add_widget(btn_clear)

        return root

    def _search_tab(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        self.search_in = TextInput(
            hint_text="query (e.g. asyncio)",
            multiline=False, size_hint_y=None, height=50)
        box.add_widget(self.search_in)
        btn = Button(text="Search", size_hint_y=None, height=50,
                     background_color=(0.14, 0.52, 0.21, 1))
        btn.bind(on_press=lambda x: self.do_search())
        box.add_widget(btn)
        return box

    def _related_tab(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        self.rel_in = TextInput(
            hint_text="package (e.g. fastapi)",
            multiline=False, size_hint_y=None, height=50)
        box.add_widget(self.rel_in)
        btn = Button(text="Find related", size_hint_y=None, height=50,
                     background_color=(0.14, 0.52, 0.21, 1))
        btn.bind(on_press=lambda x: self.do_related())
        box.add_widget(btn)
        return box

    def _ask_tab(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        self.ask_in = TextInput(
            hint_text="question",
            multiline=False, size_hint_y=None, height=50)
        box.add_widget(self.ask_in)
        btn = Button(text="Ask (RAG)", size_hint_y=None, height=50,
                     background_color=(0.14, 0.52, 0.21, 1))
        btn.bind(on_press=lambda x: self.do_ask())
        box.add_widget(btn)
        return box

    def _graph_tab(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        self.graph_spinner = Spinner(
            text="top",
            values=("top", "graphics", "categories", "stats"),
            size_hint_y=None, height=50)
        box.add_widget(self.graph_spinner)
        btn = Button(text="Run", size_hint_y=None, height=50,
                     background_color=(0.14, 0.52, 0.21, 1))
        btn.bind(on_press=lambda x: self.do_graph())
        box.add_widget(btn)
        return box

    def _system_tab(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        for name, cmd in [
            ("Status", "status"),
            ("Categories", "categories"),
            ("Health", "health"),
            ("Rebuild", "rebuild"),
        ]:
            b = Button(text=name, size_hint_y=None, height=50)
            b.bind(on_press=lambda x, c=cmd: self.run_cmd(c))
            box.add_widget(b)
        return box

    # ── اجرای دستورات از طریق evoscanner_v2 ──
    def run_cmd(self, *args):
        self.output.append(f"$ esc {' '.join(args)}")
        threading.Thread(target=self._run_thread,
                         args=(args,), daemon=True).start()

    def _run_thread(self, args):
        try:
            os.chdir(str(APP_DIR))
            cmd = [sys.executable, "evoscanner_v2.py"] + list(args)
            result = subprocess.run(cmd, capture_output=True,
                                    text=True, timeout=60)
            for line in (result.stdout or "").splitlines():
                Clock.schedule_once(
                    lambda dt, l=line: self.output.append(l))
            if result.stderr:
                for line in result.stderr.splitlines()[:5]:
                    Clock.schedule_once(
                        lambda dt, l="[err] " + l: self.output.append(l))
        except Exception as e:
            Clock.schedule_once(
                lambda dt: self.output.append(f"[error] {e}"))

    def do_search(self):
        q = self.search_in.text.strip()
        if q:
            self.run_cmd("search", q)

    def do_related(self):
        p = self.rel_in.text.strip()
        if p:
            self.run_cmd("related", p)

    def do_ask(self):
        q = self.ask_in.text.strip()
        if q:
            self.run_cmd("ask", q)

    def do_graph(self):
        mode = self.graph_spinner.text
        if mode == "top":
            self.run_cmd("top", "20")
        elif mode == "graphics":
            self.run_cmd("categories")
        elif mode == "categories":
            self.run_cmd("categories")
        elif mode == "stats":
            self.run_cmd("stats")


if __name__ == "__main__":
    EvoApp().run()

