"""
Lndis AI Assistant — Desktop Application (CustomTkinter)

A premium, modern dark-themed desktop GUI.
Run: python ui/app.py
Build: pyinstaller --onefile --windowed ui/app.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from datetime import datetime

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import customtkinter as ctk

from core.agent import Agent
from core.settings import Settings, PROVIDER_PRESETS
from core.llm import LLMAdapter
from core.voice import VoiceEngine

# ── Theme ──────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Color constants
BG_DARK      = "#0d0d14"
BG_SIDEBAR   = "#111118"
BG_CARD      = "#16161f"
BG_INPUT     = "#1a1a26"
BG_HOVER     = "#1e1e2a"
ACCENT       = "#f0a030"
ACCENT_DIM   = "#2a2010"
ACCENT_HOVER = "#ffb840"
TEXT_PRIMARY  = "#e0e0f0"
TEXT_SECONDARY= "#8888a0"
TEXT_MUTED    = "#555568"
SUCCESS      = "#34d399"
DANGER       = "#f87171"
INFO         = "#60a5fa"
BORDER       = "#222230"
MIC_ACTIVE   = "#ef4444"
MIC_READY    = "#34d399"


# ══════════════════════════════════════════════════════════════
# Main Application
# ══════════════════════════════════════════════════════════════

class LndisApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Window setup
        self.title("Lndis AI Assistant")
        self.geometry("1100x700")
        self.minsize(900, 550)
        self.configure(fg_color=BG_DARK)

        # Try to set icon
        icon_path = _ROOT / "assets" / "icon.ico"
        if icon_path.exists():
            self.iconbitmap(str(icon_path))

        # Backend
        self.settings = Settings()
        self.agent = Agent(settings=self.settings)

        # Voice engine
        self.voice = VoiceEngine()
        self.voice.tts_enabled = self.settings.get("tts_enabled", True)
        self._listening = False

        # State
        self._current_panel = "chat"
        self._processing = False
        self.auto_execute = self.settings.get("auto_execute", True)

        # Build UI
        self._build_sidebar()
        self._build_main()

        # Load initial data
        self.after(100, self._update_status)

    # ── Sidebar ────────────────────────────────────────────────

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=200, fg_color=BG_SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=15, pady=(20, 25))

        ctk.CTkLabel(
            logo_frame, text="◉  Lndis AI",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            logo_frame, text="Desktop Assistant",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")

        # Navigation buttons
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("chat", "💬  Chat"),
            ("tools", "🔧  Tools"),
            ("logs", "📋  Logs"),
            ("settings", "⚙️  Settings"),
        ]

        for panel_name, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_SECONDARY,
                anchor="w",
                height=38,
                corner_radius=8,
                command=lambda p=panel_name: self._switch_panel(p),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[panel_name] = btn

        # Spacer
        ctk.CTkFrame(self.sidebar, fg_color="transparent", height=10).pack(fill="both", expand=True)

        # Status indicator
        self.status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.status_dot = ctk.CTkLabel(
            self.status_frame, text="●", font=ctk.CTkFont(size=10),
            text_color=TEXT_MUTED, width=15,
        )
        self.status_dot.pack(side="left")

        self.status_label = ctk.CTkLabel(
            self.status_frame, text="Loading...",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self.status_label.pack(side="left", padx=5)

        # Set initial active
        self._highlight_nav("chat")

    def _highlight_nav(self, panel_name: str):
        for name, btn in self.nav_buttons.items():
            if name == panel_name:
                btn.configure(fg_color=ACCENT_DIM, text_color=ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SECONDARY)

    # ── Main Area ──────────────────────────────────────────────

    def _build_main(self):
        self.main_frame = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self.main_frame.pack(side="right", fill="both", expand=True)

        # Create panels
        self.panels: dict[str, ctk.CTkFrame] = {}
        self._build_chat_panel()
        self._build_tools_panel()
        self._build_logs_panel()
        self._build_settings_panel()

        self._switch_panel("chat")

    def _switch_panel(self, panel_name: str):
        self._current_panel = panel_name
        self._highlight_nav(panel_name)

        for name, panel in self.panels.items():
            if name == panel_name:
                panel.pack(fill="both", expand=True)
            else:
                panel.pack_forget()

        # Refresh data
        if panel_name == "tools":
            self._refresh_tools()
        elif panel_name == "logs":
            self._refresh_logs()
        elif panel_name == "settings":
            self._refresh_settings()

    # ══════════════════════════════════════════════════════════
    # Chat Panel
    # ══════════════════════════════════════════════════════════

    def _build_chat_panel(self):
        panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.panels["chat"] = panel

        # Header
        header = ctk.CTkFrame(panel, fg_color=BG_SIDEBAR, height=52, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Mascot / Status Orb in Header
        self.mascot_frame = ctk.CTkFrame(header, fg_color="transparent", width=40, height=40)
        self.mascot_frame.pack(side="left", padx=(10, 0))
        self.mascot_frame.pack_propagate(False)

        self.mascot_orb = ctk.CTkLabel(
            self.mascot_frame, text="◉",
            font=ctk.CTkFont(size=24), text_color=ACCENT
        )
        self.mascot_orb.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            header, text="Lndis AI", font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left", padx=10)

        self.provider_badge = ctk.CTkLabel(
            header, text="--",
            font=ctk.CTkFont(size=11),
            text_color=ACCENT,
            fg_color=ACCENT_DIM,
            corner_radius=12,
            width=80, height=24,
        )
        self.provider_badge.pack(side="right", padx=(0, 20))

        # Messages area
        self.chat_scroll = ctk.CTkScrollableFrame(
            panel, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=TEXT_MUTED,
        )
        self.chat_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Welcome message
        self.welcome_frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        self.welcome_frame.pack(fill="x", pady=60)

        ctk.CTkLabel(
            self.welcome_frame, text="◉",
            font=ctk.CTkFont(size=40), text_color=ACCENT,
        ).pack()

        ctk.CTkLabel(
            self.welcome_frame, text="Lndis AI Assistant",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(8, 4))

        ctk.CTkLabel(
            self.welcome_frame, text="Security-first · Local-first · Desktop",
            font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY,
        ).pack()

        # Quick action chips
        chips_frame = ctk.CTkFrame(self.welcome_frame, fg_color="transparent")
        chips_frame.pack(pady=20)

        for label in ["run whoami", "list workspace", "write test.txt Hello"]:
            chip = ctk.CTkButton(
                chips_frame, text=label,
                font=ctk.CTkFont(family="Consolas", size=11),
                fg_color=BG_CARD, hover_color=ACCENT_DIM,
                text_color=TEXT_SECONDARY, border_width=1, border_color=BORDER,
                corner_radius=16, height=30,
                command=lambda t=label: self._quick_send(t),
            )
            chip.pack(side="left", padx=4)

        # Approval bar (hidden by default)
        self.approval_frame = ctk.CTkFrame(panel, fg_color=ACCENT_DIM, height=50, corner_radius=0)
        self.approval_label = ctk.CTkLabel(
            self.approval_frame, text="Plan ready for approval",
            font=ctk.CTkFont(size=12), text_color=ACCENT,
        )
        self.approval_label.pack(side="left", padx=20)

        self.btn_approve = ctk.CTkButton(
            self.approval_frame, text="✓ Approve & Run",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=SUCCESS, hover_color="#2dd48e",
            text_color=BG_DARK, width=130, height=32,
            corner_radius=8,
            command=self._on_approve_run,
        )
        self.btn_approve.pack(side="right", padx=5, pady=8)

        self.btn_dismiss = ctk.CTkButton(
            self.approval_frame, text="✕ Dismiss",
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=TEXT_SECONDARY, border_width=1, border_color=BORDER,
            width=90, height=32, corner_radius=8,
            command=self._on_dismiss,
        )
        self.btn_dismiss.pack(side="right", padx=5, pady=8)
        self.approval_frame.pack_forget() # Ensure hidden initially

        # Input area
        input_frame = ctk.CTkFrame(panel, fg_color=BG_SIDEBAR, height=70, corner_radius=0)
        input_frame.pack(fill="x", side="bottom")
        input_frame.pack_propagate(False)

        input_inner = ctk.CTkFrame(input_frame, fg_color=BG_INPUT, corner_radius=10, border_width=1, border_color=BORDER)
        input_inner.pack(fill="x", padx=20, pady=12)

        # Microphone button
        self.mic_btn = ctk.CTkButton(
            input_inner, text="🎤",
            font=ctk.CTkFont(size=16),
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=MIC_READY if self.voice.mic_available else TEXT_MUTED,
            width=36, height=36, corner_radius=8,
            command=self._on_mic_click,
        )
        self.mic_btn.pack(side="left", padx=(5, 0), pady=2)

        self.chat_entry = ctk.CTkEntry(
            input_inner,
            placeholder_text="Type a message or press 🎤 to speak...",
            font=ctk.CTkFont(size=13),
            fg_color="transparent", border_width=0,
            text_color=TEXT_PRIMARY,
            height=36,
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, padx=(5, 5))
        self.chat_entry.bind("<Return>", self._on_enter)

        # TTS toggle in header area
        self.tts_btn = ctk.CTkButton(
            input_inner, text="🔊" if self.voice.tts_enabled else "🔇",
            font=ctk.CTkFont(size=14),
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=ACCENT if self.voice.tts_enabled else TEXT_MUTED,
            width=36, height=36, corner_radius=8,
            command=self._toggle_tts,
        )
        self.tts_btn.pack(side="right", padx=2, pady=2)

        self.send_btn = ctk.CTkButton(
            input_inner, text="➤",
            font=ctk.CTkFont(size=16),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=BG_DARK,
            width=36, height=36, corner_radius=8,
            command=self._on_send,
        )
        self.send_btn.pack(side="right", padx=5, pady=2)

    def _on_enter(self, event):
        self._on_send()

    def _on_send(self):
        text = self.chat_entry.get().strip()
        if not text or self._processing:
            return
        self.chat_entry.delete(0, "end")

        # Remove welcome
        if self.welcome_frame.winfo_exists():
            self.welcome_frame.destroy()

        self._add_chat_message("user", text)

        # Always try to plan first via the agent.
        # The agent should decide if tools are needed or if it's just a chat.
        threading.Thread(target=self._process_input, args=(text,), daemon=True).start()

    def _process_input(self, text: str):
        self._processing = True
        self.after(0, lambda: self.send_btn.configure(state="disabled"))
        self.after(0, lambda: self.mic_btn.configure(state="disabled"))

        loading_id = self._add_loading()

        try:
            # 1. Ask Agent for a plan
            plan = self.agent.plan(text)

            self.after(0, lambda: self._remove_widget(loading_id))

            # If agent found actual tool actions, show the plan
            if plan.actions and any(a.tool_call.tool_name != "none" for a in plan.actions):
                self.after(0, lambda: self._show_plan(plan))
                
                # AUTOMATIC EXECUTION
                if self.auto_execute:
                    self.after(500, self._on_approve_run)
            else:
                # No actions? Treat as regular chat response
                self._do_chat_logic(text)

        except Exception as e:
            self.after(0, lambda: self._remove_widget(loading_id))
            self.after(0, lambda: self._add_chat_message("system", f"Process error: {e}"))

        self.after(0, lambda: self.send_btn.configure(state="normal"))
        self.after(0, lambda: self.mic_btn.configure(state="normal"))
        self.after(0, self._update_status)
        self._processing = False

    def _do_chat_logic(self, message: str):
        try:
            self.after(0, self._update_status)
            response = self.agent.llm.chat(
                [
                    {"role": "system", "content": "You are Lndis AI, a friendly and helpful mascot. Use a warm, conversational tone. You are the user's personal companion."},
                    {"role": "user", "content": message},
                ]
            )
            response_text = response.content
            self.after(0, lambda: self._add_chat_message("assistant", response_text))
            if self.voice.tts_enabled:
                # Update mascot to speaking state before starting TTS
                self.after(0, self._update_status)
                self.voice.speak(response_text)
                # Check periodically to return to idle
                self._poll_voice_status()
        except Exception as e:
            self.after(0, lambda: self._add_chat_message("system", f"Chat error: {e}"))
        finally:
            self.after(0, self._update_status)

    def _poll_voice_status(self):
        """Monitor TTS and update mascot accordingly."""
        if self.voice.is_speaking:
            self._update_status()
            self.after(500, self._poll_voice_status)
        else:
            self._update_status()

    def _quick_send(self, text: str):
        self.chat_entry.delete(0, "end")
        self.chat_entry.insert(0, text)
        self._on_send()

    # ── Chat background tasks ─────────────────────────────────

    def _do_chat(self, message: str):
        self._processing = True
        self.after(0, lambda: self.send_btn.configure(state="disabled"))

        loading_id = self._add_loading()

        try:
            if self.agent.planning_mode == "keyword":
                response_text = "AI not configured. Go to Settings to set up a provider and API key."
            else:
                response = self.agent.llm.chat(
                    [
                        {"role": "system", "content": "You are Lndis AI Assistant, a helpful desktop assistant. Respond concisely in the user's language."},
                        {"role": "user", "content": message},
                    ],
                    temperature=float(self.settings.get("temperature", 0.3)),
                    max_tokens=int(self.settings.get("max_tokens", 2048)),
                )
                response_text = response.content
        except Exception as e:
            response_text = f"Error: {e}"

        self.after(0, lambda: self._remove_widget(loading_id))
        self.after(0, lambda: self._add_chat_message("assistant", response_text))
        self.after(0, lambda: self.send_btn.configure(state="normal"))
        self._processing = False

        # Speak assistant response aloud
        if self.voice.tts_enabled and not response_text.startswith("Error:"):
            self.voice.speak(response_text)

    def _do_plan(self, request: str):
        self._processing = True
        self.after(0, lambda: self.send_btn.configure(state="disabled"))

        loading_id = self._add_loading()

        try:
            plan = self.agent.plan(request)
            self.after(0, lambda: self._remove_widget(loading_id))
            self.after(0, lambda: self._show_plan(plan))
        except Exception as e:
            self.after(0, lambda: self._remove_widget(loading_id))
            self.after(0, lambda: self._add_chat_message("system", f"Plan error: {e}"))

        self.after(0, lambda: self.send_btn.configure(state="normal"))
        self._processing = False

    def _show_plan(self, plan):
        # Show plan card
        card = ctk.CTkFrame(self.chat_scroll, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=20, pady=4, anchor="w")

        ctk.CTkLabel(card, text="PLAN", font=ctk.CTkFont(size=10, weight="bold"),
                      text_color=ACCENT).pack(anchor="w", padx=14, pady=(10, 4))

        ctk.CTkLabel(card, text=plan.summary, font=ctk.CTkFont(size=12),
                      text_color=TEXT_SECONDARY, wraplength=500).pack(anchor="w", padx=14)

        for i, action in enumerate(plan.actions, 1):
            step_frame = ctk.CTkFrame(card, fg_color="transparent")
            step_frame.pack(fill="x", padx=14, pady=4)

            ctk.CTkLabel(
                step_frame, text=f"{i}.", font=ctk.CTkFont(size=12, weight="bold"),
                text_color=ACCENT, width=20,
            ).pack(side="left")

            step_text = f"{action.description}\n{action.tool_call.tool_name}({json.dumps(action.tool_call.args, ensure_ascii=False)})"
            ctk.CTkLabel(
                step_frame, text=step_text,
                font=ctk.CTkFont(size=11),
                text_color=TEXT_PRIMARY,
                wraplength=450, justify="left",
            ).pack(side="left", padx=8)

        ctk.CTkFrame(card, fg_color="transparent", height=8).pack()

        self._scroll_to_bottom()

        # Show approval bar only if auto_execute is DISABLED
        if not self.auto_execute:
            self.approval_label.configure(text=f"Plan: {plan.summary} ({len(plan.actions)} steps)")
            self.approval_frame.pack(fill="x", before=self.chat_scroll.master.winfo_children()[-1])

    def _on_approve_run(self):
        if self.agent.current_plan is None:
            return
        self.approval_frame.pack_forget()
        self._add_chat_message("system", "Plan approved. Executing...")

        threading.Thread(target=self._do_execute, daemon=True).start()

    def _do_execute(self):
        self._processing = True
        loading_id = self._add_loading()

        try:
            self.agent.approve()
            plan = self.agent.execute()

            self.after(0, lambda: self._remove_widget(loading_id))
            self.after(0, lambda: self._show_results(plan))
            self.after(0, self._update_status)
        except Exception as e:
            self.after(0, lambda: self._remove_widget(loading_id))
            self.after(0, lambda: self._add_chat_message("system", f"Execution error: {e}"))

        self._processing = False

    def _show_results(self, plan):
        from core.models import ActionStatus

        card = ctk.CTkFrame(self.chat_scroll, fg_color=BG_CARD, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=20, pady=4, anchor="w")

        ctk.CTkLabel(card, text="RESULTS", font=ctk.CTkFont(size=10, weight="bold"),
                      text_color=SUCCESS).pack(anchor="w", padx=14, pady=(10, 4))

        for i, action in enumerate(plan.actions, 1):
            step_frame = ctk.CTkFrame(card, fg_color="transparent")
            step_frame.pack(fill="x", padx=14, pady=4)

            # Status icon
            if action.status == ActionStatus.COMPLETED:
                icon, color = "✓", SUCCESS
            elif action.status == ActionStatus.DENIED:
                icon, color = "✕", DANGER
            elif action.status == ActionStatus.FAILED:
                icon, color = "✕", DANGER
            else:
                icon, color = "?", TEXT_MUTED

            ctk.CTkLabel(
                step_frame, text=icon,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=color, width=20,
            ).pack(side="left")

            info_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True, padx=8)

            ctk.CTkLabel(
                info_frame, text=action.description,
                font=ctk.CTkFont(size=12), text_color=TEXT_PRIMARY,
                wraplength=400, justify="left", anchor="w",
            ).pack(anchor="w")

            # Show result or error
            if action.error:
                ctk.CTkLabel(
                    info_frame, text=action.error,
                    font=ctk.CTkFont(size=11), text_color=DANGER,
                    wraplength=400, justify="left",
                ).pack(anchor="w")
            elif action.result:
                result_str = self._format_result(action.result)
                if result_str:
                    result_box = ctk.CTkTextbox(
                        info_frame, height=80, fg_color=BG_DARK,
                        font=ctk.CTkFont(family="Consolas", size=11),
                        text_color=TEXT_SECONDARY, corner_radius=6,
                        border_width=1, border_color=BORDER, wrap="word",
                    )
                    result_box.pack(fill="x", pady=4)
                    result_box.insert("1.0", result_str[:500])
                    result_box.configure(state="disabled")

        ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        self._scroll_to_bottom()

    def _format_result(self, result) -> str:
        if isinstance(result, dict):
            if result.get("type") == "file":
                content = result.get("content", "")
                return f"File: {result.get('path')} ({result.get('lines', '?')} lines)\n{content[:400]}"
            elif result.get("type") == "directory":
                entries = result.get("entries", [])[:15]
                lines = [f"{'[D]' if e['type']=='dir' else '[F]'} {e['name']}" for e in entries]
                return "\n".join(lines)
            elif "stdout" in result:
                return result.get("stdout", "")[:400]
            elif result.get("ok") is True:
                return json.dumps(result, ensure_ascii=False, indent=2)
            return json.dumps(result, ensure_ascii=False, indent=2)[:300]
        return str(result)[:300]

    def _on_dismiss(self):
        self.approval_frame.pack_forget()
        self._add_chat_message("system", "Plan dismissed.")

    # ── Voice controls ─────────────────────────────────────────

    def _on_mic_click(self):
        """Toggle microphone listening."""
        if not self.voice.mic_available:
            self._add_chat_message("system", "Microphone not available. Check audio device.")
            return

        if self.voice.is_speaking:
            self._add_chat_message("system", "Please wait for me to finish speaking...")
            return

        if self._listening:
            return  # Already listening

        if self._processing:
            return

        self._listening = True
        self.mic_btn.configure(text="🔴", fg_color=MIC_ACTIVE, text_color="white")
        self.chat_entry.configure(placeholder_text="Listening...")

        # Remove welcome if present
        if self.welcome_frame.winfo_exists():
            self.welcome_frame.destroy()

        self._add_chat_message("system", "🎤 Listening... Speak now.")

        self.voice.listen_async(
            on_result=self._on_voice_result,
            on_error=self._on_voice_error,
            on_listening=lambda: None,
        )

    def _on_voice_result(self, text: str):
        """Handle STT transcription."""
        self._listening = False
        self.after(0, lambda: self.mic_btn.configure(
            text="🎤", fg_color="transparent", text_color=MIC_READY
        ))
        self.after(0, lambda: self.chat_entry.configure(
            placeholder_text="Mesajınızı yazın..."
        ))

        # Show transcription and start mascot session
        self.after(0, lambda: self._add_chat_message("user", text))
        threading.Thread(target=self._process_input, args=(text,), daemon=True).start()

    def _on_voice_error(self, msg: str):
        """Called when speech recognition fails."""
        self._listening = False
        self.after(0, lambda: self.mic_btn.configure(
            text="🎤", fg_color="transparent", text_color=MIC_READY
        ))
        self.after(0, lambda: self._add_chat_message("system", f"Ses hatası: {msg}"))
        self.after(0, self._update_status)

    def _toggle_tts(self):
        """Toggle text-to-speech on/off."""
        self.voice.tts_enabled = not self.voice.tts_enabled
        self.settings.set("tts_enabled", self.voice.tts_enabled)

        if self.voice.tts_enabled:
            self.tts_btn.configure(text="🔊", text_color=ACCENT)
            self.voice.speak("Ses çıkışı aktif.")
        else:
            self.tts_btn.configure(text="🔇", text_color=TEXT_MUTED)
            self.voice.stop_speaking()

    # ── Chat message helpers ──────────────────────────────────

    def _add_chat_message(self, role: str, text: str):
        colors = {
            "user": (ACCENT_DIM, ACCENT),
            "assistant": (BG_CARD, TEXT_PRIMARY),
            "system": (BG_SIDEBAR, TEXT_MUTED),
        }
        bg, fg = colors.get(role, (BG_CARD, TEXT_PRIMARY))
        # User messages on the right (ne), others on the left (nw)
        curr_anchor = "ne" if role == "user" else "nw"
        
        row = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8, anchor=curr_anchor)

        # Main message column
        main_col = ctk.CTkFrame(row, fg_color="transparent")
        main_col.pack(side="right" if role == "user" else "left", fill="y")

        # Name and Mascot Indicator
        avatar_sym = "◉" if role != "user" else "👤"
        disp_name = "Lndis AI" if role != "user" else "Siz"
        if role == "system": disp_name = "Sistem"
        
        lbl_color = ACCENT if role == "assistant" else TEXT_MUTED
        if role == "user": lbl_color = ACCENT

        name_lbl = ctk.CTkLabel(
            main_col, text=f"{avatar_sym} {disp_name}", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=lbl_color
        )
        name_lbl.pack(anchor="e" if role == "user" else "w", padx=10)

        # Message bubble
        msg_frame = ctk.CTkFrame(main_col, fg_color=bg, corner_radius=12,
                                  border_width=1, border_color=BORDER if role != "user" else ACCENT_DIM)
        msg_frame.pack(side="top", pady=2, padx=5)

        ctk.CTkLabel(
            msg_frame, text=text,
            font=ctk.CTkFont(size=13),
            text_color=fg, wraplength=450,
            justify="left", anchor="w",
            padx=14, pady=10,
        ).pack()

        self._scroll_to_bottom()

    def _add_loading(self) -> str:
        frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=3, anchor="w")
        frame._lndis_id = f"loading_{id(frame)}"

        ctk.CTkLabel(
            frame, text="AI",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=BG_INPUT, width=28, height=28, corner_radius=14,
            text_color=INFO,
        ).pack(side="left", padx=(0, 8))

        bubble = ctk.CTkFrame(frame, fg_color=BG_CARD, corner_radius=10,
                               border_width=1, border_color=BORDER)
        bubble.pack(side="left")

        ctk.CTkLabel(
            bubble, text="Thinking...",
            font=ctk.CTkFont(size=12), text_color=TEXT_MUTED,
            padx=14, pady=10,
        ).pack()

        self._scroll_to_bottom()
        return frame._lndis_id

    def _remove_widget(self, widget_id: str):
        for child in self.chat_scroll.winfo_children():
            if hasattr(child, '_lndis_id') and child._lndis_id == widget_id:
                child.destroy()
                return

    def _scroll_to_bottom(self):
        self.after(50, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    # ══════════════════════════════════════════════════════════
    # Tools Panel
    # ══════════════════════════════════════════════════════════

    def _build_tools_panel(self):
        panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.panels["tools"] = panel

        header = ctk.CTkFrame(panel, fg_color=BG_SIDEBAR, height=52, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="Available Tools", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=20)

        self.tools_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.tools_scroll.pack(fill="both", expand=True, padx=20, pady=15)

    def _refresh_tools(self):
        for w in self.tools_scroll.winfo_children():
            w.destroy()

        tools = self.agent.list_tools()
        for t in tools:
            card = ctk.CTkFrame(self.tools_scroll, fg_color=BG_CARD, corner_radius=10,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4)

            ctk.CTkLabel(
                card, text=t["name"],
                font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                text_color=ACCENT,
            ).pack(anchor="w", padx=16, pady=(12, 2))

            ctk.CTkLabel(
                card, text=t["description"],
                font=ctk.CTkFont(size=12),
                text_color=TEXT_SECONDARY,
                wraplength=500, justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 12))

    # ══════════════════════════════════════════════════════════
    # Logs Panel
    # ══════════════════════════════════════════════════════════

    def _build_logs_panel(self):
        panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.panels["logs"] = panel

        header = ctk.CTkFrame(panel, fg_color=BG_SIDEBAR, height=52, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="Audit Log", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=20)

        ctk.CTkButton(
            header, text="Refresh", font=ctk.CTkFont(size=12),
            fg_color=BG_INPUT, hover_color=BG_HOVER, text_color=TEXT_SECONDARY,
            width=80, height=30, corner_radius=8,
            command=self._refresh_logs,
        ).pack(side="right", padx=20)

        self.logs_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.logs_scroll.pack(fill="both", expand=True, padx=20, pady=15)

    def _refresh_logs(self):
        for w in self.logs_scroll.winfo_children():
            w.destroy()

        entries = self.agent.audit.recent(50)
        if not entries:
            ctk.CTkLabel(
                self.logs_scroll, text="No audit entries yet.",
                font=ctk.CTkFont(size=13), text_color=TEXT_MUTED,
            ).pack(pady=30)
            return

        for e in entries:
            row = ctk.CTkFrame(self.logs_scroll, fg_color="transparent", height=32)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            ts = e.timestamp.strftime("%H:%M:%S")
            dec_color = SUCCESS if "allow" in e.policy_decision else DANGER

            ctk.CTkLabel(row, text=ts, font=ctk.CTkFont(family="Consolas", size=11),
                          text_color=TEXT_MUTED, width=65).pack(side="left")

            ctk.CTkLabel(row, text=e.policy_decision, font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=dec_color, width=50).pack(side="left", padx=5)

            ctk.CTkLabel(row, text=e.tool_name, font=ctk.CTkFont(family="Consolas", size=11),
                          text_color=INFO, width=120).pack(side="left", padx=5)

            if e.duration_ms:
                ctk.CTkLabel(row, text=f"{e.duration_ms}ms", font=ctk.CTkFont(size=11),
                              text_color=TEXT_MUTED, width=50).pack(side="left")

            if e.error:
                ctk.CTkLabel(row, text=e.error[:50], font=ctk.CTkFont(size=11),
                              text_color=DANGER).pack(side="left", padx=5)

    # ══════════════════════════════════════════════════════════
    # Settings Panel
    # ══════════════════════════════════════════════════════════

    def _build_settings_panel(self):
        panel = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.panels["settings"] = panel

        header = ctk.CTkFrame(panel, fg_color=BG_SIDEBAR, height=52, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="Settings", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=20)

        scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=15)
        self.settings_scroll = scroll

        # ── Provider Selection ─────────────────────────────────
        ctk.CTkLabel(scroll, text="AI PROVIDER", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        providers_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        providers_frame.pack(fill="x", pady=(0, 20))

        self.provider_buttons: dict[str, ctk.CTkButton] = {}
        provider_info = [
            ("deepseek", "DeepSeek", "Recommended, affordable"),
            ("openai", "OpenAI", "GPT-4o, GPT-4o-mini"),
            ("ollama", "Ollama", "Local, free, offline"),
            ("groq", "Groq", "Fast, free tier"),
            ("openrouter", "OpenRouter", "Multi-model gateway"),
        ]

        for i, (key, name, desc) in enumerate(provider_info):
            btn = ctk.CTkButton(
                providers_frame,
                text=f"{name}\n{desc}",
                font=ctk.CTkFont(size=12),
                fg_color=BG_CARD, hover_color=ACCENT_DIM,
                text_color=TEXT_PRIMARY,
                border_width=1, border_color=BORDER,
                corner_radius=10, height=55, width=140,
                command=lambda k=key: self._select_provider(k),
            )
            btn.grid(row=0, column=i, padx=4, pady=2, sticky="nsew")
            self.provider_buttons[key] = btn

        providers_frame.grid_columnconfigure(tuple(range(len(provider_info))), weight=1)

        # ── API Key ────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="API KEY", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        key_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        key_frame.pack(fill="x", pady=(0, 5))

        self.api_key_entry = ctk.CTkEntry(
            key_frame, placeholder_text="sk-XXXXXXXXXXXXXXXXXXXXXXXX",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, height=38, show="•",
        )
        self.api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            key_frame, text="Save",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=BG_DARK, width=70, height=38,
            corner_radius=8,
            command=self._save_api_key,
        ).pack(side="right")

        self.api_key_hint = ctk.CTkLabel(
            scroll, text="Enter your API key for the selected provider.",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
        )
        self.api_key_hint.pack(anchor="w", pady=(0, 20))

        # ── Model ─────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="MODEL", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        model_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        model_frame.pack(fill="x", pady=(0, 20))

        self.model_entry = ctk.CTkEntry(
            model_frame, placeholder_text="deepseek-chat",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, height=38,
        )
        self.model_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            model_frame, text="Save",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=BG_DARK, width=70, height=38,
            corner_radius=8,
            command=self._save_model,
        ).pack(side="right")

        # ── Network Toggle ────────────────────────────────────
        ctk.CTkLabel(scroll, text="NETWORK", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        net_frame = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=10,
                                  border_width=1, border_color=BORDER)
        net_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            net_frame, text="Allow web search",
            font=ctk.CTkFont(size=13), text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=14, pady=12)

        self.net_switch = ctk.CTkSwitch(
            net_frame, text="", width=44,
            fg_color=BG_INPUT, progress_color=ACCENT,
            button_color=TEXT_MUTED, button_hover_color=TEXT_PRIMARY,
            command=self._toggle_network,
        )
        self.net_switch.pack(side="right", padx=14, pady=12)

        ctk.CTkLabel(scroll, text="When enabled, the assistant can search the web. Disabled by default for privacy.",
                      font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 20))

        # ── Execution Settings ─────────────────────────────────
        ctk.CTkLabel(scroll, text="EXECUTION", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        exec_frame = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=10,
                                   border_width=1, border_color=BORDER)
        exec_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            exec_frame, text="Auto-execute plans (No approval needed)",
            font=ctk.CTkFont(size=13), text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=14, pady=12)

        self.auto_exec_switch = ctk.CTkSwitch(
            exec_frame, text="", width=44,
            fg_color=BG_INPUT, progress_color=ACCENT,
            button_color=TEXT_MUTED, button_hover_color=TEXT_PRIMARY,
            command=self._toggle_auto_execute,
        )
        if self.auto_execute:
            self.auto_exec_switch.select()
        self.auto_exec_switch.pack(side="right", padx=14, pady=12)

        # ── Voice Settings ─────────────────────────────────────
        ctk.CTkLabel(scroll, text="VOICE", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        voice_frame = ctk.CTkFrame(scroll, fg_color=BG_CARD, corner_radius=10,
                                    border_width=1, border_color=BORDER)
        voice_frame.pack(fill="x", pady=(0, 5))

        # TTS toggle
        ctk.CTkLabel(
            voice_frame, text="Read responses aloud (TTS)",
            font=ctk.CTkFont(size=13), text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=14, pady=12)

        self.tts_switch = ctk.CTkSwitch(
            voice_frame, text="", width=44,
            fg_color=BG_INPUT, progress_color=ACCENT,
            button_color=TEXT_MUTED, button_hover_color=TEXT_PRIMARY,
            command=self._settings_toggle_tts,
        )
        if self.voice.tts_enabled:
            self.tts_switch.select()
        self.tts_switch.pack(side="right", padx=14, pady=12)

        # STT Language
        lang_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        lang_frame.pack(fill="x", pady=(5, 5))

        ctk.CTkLabel(lang_frame, text="Voice language",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(side="left")

        self.lang_menu = ctk.CTkOptionMenu(
            lang_frame,
            values=["tr-TR", "en-US", "en-GB", "de-DE", "fr-FR", "es-ES", "ja-JP", "zh-CN"],
            font=ctk.CTkFont(size=12),
            fg_color=BG_INPUT, button_color=ACCENT,
            text_color=TEXT_PRIMARY, width=120,
            command=self._set_voice_language,
        )
        self.lang_menu.set(self.voice.stt_language)
        self.lang_menu.pack(side="right")

        # Speech rate
        rate_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        rate_frame.pack(fill="x", pady=(5, 5))

        ctk.CTkLabel(rate_frame, text="Speech speed",
                      font=ctk.CTkFont(size=12), text_color=TEXT_SECONDARY).pack(side="left")

        self.rate_slider = ctk.CTkSlider(
            rate_frame, from_=100, to=300,
            fg_color=BG_INPUT, progress_color=ACCENT,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            width=150,
            command=self._set_voice_rate,
        )
        self.rate_slider.set(self.voice.tts_rate)
        self.rate_slider.pack(side="right")

        # Mic status
        mic_status = "✓ Microphone detected" if self.voice.mic_available else "✕ No microphone found"
        mic_color = SUCCESS if self.voice.mic_available else DANGER
        ctk.CTkLabel(scroll, text=mic_status,
                      font=ctk.CTkFont(size=11), text_color=mic_color).pack(anchor="w", pady=(5, 20))

        # ── Current Config Display ────────────────────────────
        ctk.CTkLabel(scroll, text="CURRENT CONFIGURATION", font=ctk.CTkFont(size=11, weight="bold"),
                      text_color=TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        self.config_textbox = ctk.CTkTextbox(
            scroll, height=140, fg_color=BG_INPUT,
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=TEXT_SECONDARY, corner_radius=8,
            border_width=1, border_color=BORDER,
        )
        self.config_textbox.pack(fill="x")

    def _select_provider(self, provider: str):
        msg = self.settings.set_provider(provider)
        self.agent.reload_llm()
        self._refresh_settings()
        self._update_status()

        # Update hint
        hints = {
            "deepseek": "Get your key at platform.deepseek.com",
            "openai": "Get your key at platform.openai.com",
            "ollama": "Ollama runs locally — no API key needed.",
            "groq": "Get your key at console.groq.com",
            "openrouter": "Get your key at openrouter.ai",
        }
        self.api_key_hint.configure(text=hints.get(provider, "Enter your API key."), text_color=TEXT_MUTED)

    def _save_api_key(self):
        key = self.api_key_entry.get().strip()
        if not key:
            self.api_key_hint.configure(text="Please enter an API key.", text_color=DANGER)
            return

        msg = self.settings.set_api_key(key)
        self.agent.reload_llm()
        self.api_key_entry.delete(0, "end")
        self._refresh_settings()
        self._update_status()

        if self.agent.planning_mode == "llm":
            self.api_key_hint.configure(text=f"✓ {msg} — AI is ready!", text_color=SUCCESS)
        else:
            self.api_key_hint.configure(text=f"{msg}", text_color=TEXT_MUTED)

    def _save_model(self):
        model = self.model_entry.get().strip()
        if not model:
            return
        self.settings.set("model", model)
        self.agent.reload_llm()
        self._refresh_settings()
        self._update_status()

    def _toggle_network(self):
        enabled = self.net_switch.get()
        self.agent.policy.set_network(bool(enabled))

    def _toggle_auto_execute(self):
        self.auto_execute = bool(self.auto_exec_switch.get())
        self.settings.set("auto_execute", self.auto_execute)

    def _settings_toggle_tts(self):
        self.voice.tts_enabled = bool(self.tts_switch.get())
        self.settings.set("tts_enabled", self.voice.tts_enabled)
        self.tts_btn.configure(
            text="🔊" if self.voice.tts_enabled else "🔇",
            text_color=ACCENT if self.voice.tts_enabled else TEXT_MUTED,
        )

    def _set_voice_language(self, lang: str):
        self.voice.stt_language = lang
        self.settings.set("stt_language", lang)

    def _set_voice_rate(self, rate: float):
        self.voice.set_rate(int(rate))
        self.settings.set("tts_rate", int(rate))

    def _refresh_settings(self):
        cfg = self.settings.all()

        # Highlight active provider
        current = cfg.get("provider", "auto")
        for key, btn in self.provider_buttons.items():
            if key == current:
                btn.configure(fg_color=ACCENT_DIM, border_color=ACCENT)
            else:
                btn.configure(fg_color=BG_CARD, border_color=BORDER)

        # Model field
        model = cfg.get("model", "")
        self.model_entry.delete(0, "end")
        if model:
            self.model_entry.insert(0, model)

        # Config display
        self.config_textbox.configure(state="normal")
        self.config_textbox.delete("1.0", "end")
        for k, v in cfg.items():
            self.config_textbox.insert("end", f"  {k:18s} {v}\n")
        self.config_textbox.configure(state="disabled")

    # ── Status ─────────────────────────────────────────────────

    def _update_status(self):
        mode = self.agent.planning_mode
        provider = getattr(self.agent.llm, "provider_name", "none")
        model = getattr(self.agent.llm, "model", "none")

        # Update status bar
        if mode == "llm":
            self.status_dot.configure(text_color=SUCCESS)
            self.status_label.configure(text=f"{provider}/{model}", text_color=TEXT_SECONDARY)
            self.provider_badge.configure(text=f"{provider}/{model}")
        else:
            self.status_dot.configure(text_color=TEXT_MUTED)
            self.status_label.configure(text="Keyword mode", text_color=TEXT_MUTED)
            self.provider_badge.configure(text="No AI")

        # Update Mascot Visual State
        if self._listening:
            self.mascot_orb.configure(text_color=DANGER, text="◎") # Recording
        elif self.voice.is_speaking:
            self.mascot_orb.configure(text_color=SUCCESS, text="◉") # Speaking
        elif self._processing:
            self.mascot_orb.configure(text_color=INFO, text="◌") # Thinking
        else:
            self.mascot_orb.configure(text_color=ACCENT, text="◉") # Idle


# ══════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════

def main():
    app = LndisApp()
    app.mainloop()

if __name__ == "__main__":
    main()
