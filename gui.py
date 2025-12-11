#!/usr/bin/env python3
import sys
import threading
from pathlib import Path
from typing import List, Dict, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse
import os
import time

# Pour afficher les covers
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    from io import BytesIO
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Lecteur audio
try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False
    print("pygame non installé. Le lecteur audio sera désactivé.")

# Thème Sun Valley (sv_ttk)
try:
    import sv_ttk
    HAS_SV_TTK = True
except ImportError:
    HAS_SV_TTK = False

# Bibliothèque drag and drop depuis OS
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    print("tkinterdnd2 non installé. Drag & Drop désactivé.")
    
# Accès à src/
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.append(str(SRC_DIR))

# Importations ou Classes Dummy
try:
    from library.models.music_library import MusicLibrary
    from library.models.audio_file import AudioFile
    from library.models.mp3_file import MP3File
    from library.models.flac_file import FLACFile
    from library.core.playlist_generator import PlaylistGenerator
    from library.core.metadatafetcher import MetadataFetcher
except ImportError:
    print("Attention: Modules library non trouvés. Mode interface seule.")
    
    class MusicLibrary:
        def __init__(self): self.files = []
        def load_directory(self, p): pass
    
    class AudioFile:
        def __init__(self, p): self.filepath = p; self.metadata = {}
        def extract_metadata(self): return {}
        def get_duration(self): return 0
        def get_cover_art(self): return None
        def save_metadata(self): pass

    class MetadataFetcher:
        def fetch_lyrics_for_audio(self, a): return "Paroles démo..."
        def update_audio_file_metadata(self, a): return False


# --------- Tooltip simple pour IHM (guidage) ----------
class Tooltip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() - 10
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=4, ipady=2)

    def hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class MusicLibraryGUI(TkinterDnD.Tk if HAS_DND else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PyMetaPlay")
        self.geometry("1200x800")
        self.minsize(1000, 680)

        # --- THEMES JOUR / NUIT ---
        self.themes = {
            "dark": {
                "bg": "#0A0A12",            
                "sidebar": "#0F0F1C",       
                "player": "#0A0A12",        
                "card": "#0A0A12",          
                "accent": "#1936B7",
                "accent_dark": "#a393eb",
                "text": "#F2F2F7",
                "text_dim": "#A7A7B2",
                "text_barre": "#F2F2F7",
                "border": "#1E1E2A",
                "list_bg": "#10101A",
                "list_fg": "#F2F2F7",
                "list_sel_bg": "#D4A017",
                "list_sel_fg": "#0A0A12",
                "input_bg": "#1A1A28",
                "input_fg": "#F2F2F7",
            },
            "light": {
                "bg": "#E8ECF7",
                "sidebar": "#F4F7FF",
                "card": "#F4F7FF",
                "player": "#2D51B3",
                "accent": "#1936B7",
                "accent_dark": "#1936B7",
                "text": "#1A1F36",
                "text_barre": "#1A1F36",
                "text_dim": "#505560",
                "border": "#C7D1E6",
                "list_bg": "#C9CED8",
                "list_fg": "#1A1F36",
                "list_sel_bg": "#E0E6FB",
                "list_sel_fg": "#1A1F36",
                "input_bg": "#FFFFFF",
                "input_fg": "#1A1F36",
            },
        }

        self.current_theme = "light"
        self.colors = self.themes[self.current_theme]
        self.configure(bg=self.colors["bg"])

        # Frames / widgets à recolorer quand on change de thème
        self.sidebar_button_frame = None
        self.player_center_frame = None
        self.player_controls_frame = None
        self.player_progress_frame = None
        self.player_status_bar = None
        self.status_label = None
        self.theme_toggle_btn = None

        # Boutons player (pour le hover + thème)
        self.btn_repeat = None
        self.btn_prev = None
        self.btn_next = None
        self.btn_play = None
        self.btn_vol = None

        # Labels principaux (now playing)
        self.lbl_title = None
        self.lbl_artist = None
        self.lbl_details = None
        
        # En-têtes fixes (Contenu principal)
        self.lbl_header_pochette = None
        self.lbl_header_lecture = None
        self.lbl_header_paroles = None

        # En-têtes fixes (Sidebar)
        self.lbl_header_logo = None
        self.lbl_header_search = None
        self.lbl_header_lib = None
        self.lbl_header_tracks = None

        # Données
        self.library = MusicLibrary()
        self.audio_files: List[AudioFile] = []
        self.displayed_files: List[AudioFile] = []
        self.index_to_audio: Dict[int, AudioFile] = {}

        # METADATA FETCHER
        self.metadata_fetcher = MetadataFetcher()

        # État du lecteur
        self.audio_player_enabled = False
        self.current_index: Optional[int] = None
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.repeat: bool = False
        self.volume: float = 0.8
        self.muted: bool = False
        self.current_offset: float = 0.0
        self.user_dragging_progress: bool = False

        # Init Audio
        if HAS_PYGAME:
            try:
                pygame.mixer.init()
                pygame.mixer.music.set_volume(self.volume)
                self.audio_player_enabled = True
            except Exception as e:
                print("Erreur audio:", e)

        # Drag and Drop
        if HAS_DND:
            try:
                # On accepte le drop de fichiers partout sur la fenêtre
                self.drop_target_register(DND_FILES)
                self.dnd_bind('<<Drop>>', self.on_drop_files)
            except Exception as e:
                print(f"Erreur init DND: {e}")

        # Images (cover / placeholder ♪)
        self.cover_image_ref = None
        self.placeholder_image = None

        # Variables d'état
        self.var_title = tk.StringVar(value="Aucune lecture")
        self.var_artist = tk.StringVar(value="--")
        self.var_details = tk.StringVar(value="")
        self.var_duration = tk.StringVar(value="0")
        self.var_path = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="Bienvenue dans PyMetaPlay")

        self.var_album_internal = ""
        self.var_year_internal = ""

        self._setup_styles()
        self._build_layout()
        self._build_menu()

        # Boucle d'update du temps de lecture
        self.after(500, self._progress_loop)

        # Appliquer le thème initial
        self._apply_theme(self.current_theme)

        # Message IHM au démarrage dans la liste
        self._refresh_listbox()

    # Helper tooltip
    def _add_tooltip(self, widget, text: str):
        Tooltip(widget, text)

    # ---------- Styles ----------
    def _setup_styles(self):
        style = ttk.Style(self)
        c = self.colors

        if HAS_SV_TTK:
            if self.current_theme == "dark":
                sv_ttk.use_dark_theme()
            else:
                sv_ttk.use_light_theme()

        style.configure("Sidebar.TFrame", background=c["sidebar"])
        style.configure("Player.TFrame", background=c["player"])
        style.configure("Main.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"])

        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=8,
            background=c["accent"],
            foreground=c["text"],
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", c["accent_dark"]),
                ("pressed", c["accent_dark"]),
            ],
            foreground=[
                ("active", c["bg"]),
                ("pressed", c["bg"]),
            ],
        )
        
        if self.current_theme == "dark":
            btn_bg = "#576574"
            btn_fg = "#ffffff"
            btn_active = "#222f3e"
        else:
            btn_bg = "#b2bec3" 
            btn_fg = "#000000"
            btn_active = "#636e72"

        style.configure(
            "Custom.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=8,
            background=btn_bg,   
            foreground=btn_fg,   
        )
        style.map(
            "Custom.TButton",
            background=[("active", btn_active), ("pressed", btn_active)],
            foreground=[("active", btn_fg), ("pressed", btn_fg)],
        )

    # ---------- Layout général ----------
    def _build_layout(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(15, 15))
        sidebar.grid(row=0, column=0, sticky="nsew")
        self._build_sidebar(sidebar)

        main_content = ttk.Frame(self, style="Main.TFrame", padding=(20, 20))
        main_content.grid(row=0, column=1, sticky="nsew")
        self._build_main_content(main_content)

        player_bar = ttk.Frame(self, style="Player.TFrame")
        player_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        player_bar.columnconfigure(0, weight=1)
        self._build_player_bar(player_bar)

    # ---------- Trier liste audio ----------
    def _sort_treeview(self, col, reverse):
        # 1. On récupère la liste des objets (index, AudioFile)
        l = []
        for k, audio in self.index_to_audio.items():
            # On détermine la valeur de tri selon la colonne
            val = ""
            if col == "titre":
                val = audio.metadata.get("title", audio.filepath.stem).lower()
            elif col == "artiste":
                val = audio.metadata.get("artist", "").lower()
            elif col == "duree":
                val = audio.get_duration() 
            
            l.append((val, k, audio))

        # 2. On trie la liste
        l.sort(key=lambda x: x[0], reverse=reverse)

        # 3. On met à jour displayed_files et l'interface
        self.displayed_files = [x[2] for x in l]
        self._refresh_listbox()

        # 4. On inverse le sens pour le prochain clic (Ascendant <-> Descendant)
        self.tree.heading(col, command=lambda: self._sort_treeview(col, not reverse))

    # ---------- Sidebar ----------
    def _build_sidebar(self, parent):
        c = self.colors
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=0)
        parent.rowconfigure(3, weight=0)
        parent.rowconfigure(4, weight=0) # C'était 1 avant, on met 0 pour figer la hauteur
        parent.rowconfigure(5, weight=0)
        parent.rowconfigure(6, weight=1)

        self.lbl_header_logo = tk.Label(
            parent,
            text="🎵 PyMetaPlay",
            font=("Segoe UI", 16, "bold"),
            bg=c["sidebar"], 
            fg=c["accent"],
        )
        self.lbl_header_logo.grid(row=0, column=0, sticky="w", pady=(0, 20))

        self.lbl_header_search = tk.Label(
            parent, 
            text="RECHERCHE", 
            font=("Segoe UI", 11, "bold"),
            bg=c["sidebar"], 
            fg=c["text_barre"]
        )
        self.lbl_header_search.grid(row=1, column=0, sticky="w")

        search_frame = ttk.Frame(parent, style="Sidebar.TFrame")
        search_frame.grid(row=2, column=0, sticky="ew", pady=(5, 15))
        search_frame.columnconfigure(0, weight=1)

        self.var_search = tk.StringVar()
        self.var_search.trace("w", self.on_search_change)

        search_entry = ttk.Entry(search_frame, textvariable=self.var_search)
        search_entry.grid(row=0, column=0, sticky="ew")

        self.lbl_header_lib = tk.Label(
            parent, 
            text="BIBLIOTHÈQUE", 
            font=("Segoe UI", 11, "bold"),
            bg=c["sidebar"], 
            fg=c["text_barre"]
        )
        self.lbl_header_lib.grid(row=3, column=0, sticky="w", pady=(5, 5))

        btn_style = {
            "bg": c["sidebar"],
            "fg": c["text"],
            "bd": 0,
            "anchor": "w",
            "padx": 10,
            "pady": 6,
            "cursor": "hand2",
            "activebackground": c["input_bg"],
            "activeforeground": c["accent"],
            "relief": "flat",
        }

        btn_frame = tk.Frame(parent, bg=c["sidebar"])
        btn_frame.grid(row=4, column=0, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        self.sidebar_button_frame = btn_frame

        tk.Button(
            btn_frame, text="📂 Ouvrir un dossier", command=self.open_directory, **btn_style
        ).grid(row=0, column=0, sticky="ew", pady=1)

        tk.Button(
            btn_frame, text="📄 Ouvrir une playlist XSPF", command=self.open_playlist, **btn_style
        ).grid(row=1, column=0, sticky="ew", pady=1)

        tk.Button(
            btn_frame,
            text="💾 Sauvegarder la sélection",
            command=self.generate_playlist_selection,
            **btn_style,
        ).grid(row=2, column=0, sticky="ew", pady=1)

        self.lbl_header_tracks = tk.Label(
            parent, 
            text="PISTES", 
            font=("Segoe UI", 11, "bold"),
            bg=c["sidebar"], 
            fg=c["text_barre"]
        )
        self.lbl_header_tracks.grid(row=5, column=0, sticky="w", pady=(15, 5))

        list_container = ttk.Frame(parent)
        list_container.grid(row=6, column=0, sticky="nsew")
        parent.rowconfigure(6, weight=1)

        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

       # --- REMPLACEMENT DE LA LISTBOX PAR UN TREEVIEW PAR SOUMY---
        list_container = ttk.Frame(parent)
        list_container.grid(row=6, column=0, sticky="nsew")
        parent.rowconfigure(6, weight=1)

        # Définition des colonnes
        columns = ("titre", "artiste", "duree")
        self.tree = ttk.Treeview(
            list_container, 
            columns=columns, 
            show="headings", 
            selectmode="browse"
        )

        # Configuration des en-têtes
        for col in columns:
            self.tree.heading(
                col, 
                text=col.capitalize(), 
                command=lambda c=col: self._sort_treeview(c, False)
            )

        # Configuration des largeurs de colonnes
        self.tree.column("titre", width=150, minwidth=100)
        self.tree.column("artiste", width=100, minwidth=80)
        self.tree.column("duree", width=50, minwidth=40, anchor="e")

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Binding du clic (avec <<TreeviewSelect>>)
        self.tree.bind("<<TreeviewSelect>>", self.on_selection_change)
        
        self.listbox = None

    # ---------- Contenu principal ----------
    def _build_main_content(self, parent):
        c = self.colors
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        left_frame = ttk.Frame(parent, style="Main.TFrame") 
        left_frame.grid(row=0, column=0, sticky="n", padx=(0, 20))

        cover_card = ttk.Frame(left_frame, style="Main.TFrame") 
        cover_card.pack(fill=tk.X, pady=(0, 10))

        self.cover_label = tk.Label(
            cover_card,
            bg=c["bg"],
            bd=0,
        )
        self.cover_label.pack(anchor="center")
        
        right_frame = ttk.Frame(parent, style="Main.TFrame")
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.rowconfigure(2, weight=1)
        right_frame.columnconfigure(0, weight=1)

        now_playing = ttk.Frame(right_frame, style="Main.TFrame")
        now_playing.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.lbl_header_lecture = tk.Label(
            now_playing,
            text="Lecture en cours",
            font=("Segoe UI", 11, "bold"),
            bg=c["bg"],          
            fg=c["text_dim"],
        )
        self.lbl_header_lecture.pack(anchor="w", pady=(0, 5))

        self.lbl_title = tk.Label(
            now_playing,
            textvariable=self.var_title,
            font=("Segoe UI", 22, "bold"),
            bg=c["bg"],          
            fg=c["text"],        
            anchor="w"
        )
        self.lbl_title.pack(anchor="w", fill=tk.X)

        self.lbl_artist = tk.Label(
            now_playing,
            textvariable=self.var_artist,
            font=("Segoe UI", 14, "bold"),
            bg=c["bg"],          
            fg=c["text"],
            anchor="w"
        )
        self.lbl_artist.pack(anchor="w", pady=(3, 0), fill=tk.X)

        self.lbl_details = tk.Label(
            now_playing,
            textvariable=self.var_details,
            font=("Segoe UI", 11),
            bg=c["bg"],          
            fg=c["text_dim"],
            anchor="w"
        )
        self.lbl_details.pack(anchor="w", pady=(2, 0), fill=tk.X)

        lyrics_frame = ttk.Frame(right_frame, style="Main.TFrame")
        lyrics_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 10))
        right_frame.rowconfigure(1, weight=3)

        header_frame = ttk.Frame(lyrics_frame, style="Main.TFrame")
        header_frame.pack(fill=tk.X)

        self.lbl_header_paroles = tk.Label(
            header_frame,
            text="Paroles",
            font=("Segoe UI", 11, "bold"),
            bg=c["bg"],          
            fg=c["text_dim"],
        )
        self.lbl_header_paroles.pack(side=tk.LEFT, anchor="w")

        text_container = ttk.Frame(lyrics_frame, style="Main.TFrame")
        text_container.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        scroll_lyrics = ttk.Scrollbar(text_container)
        scroll_lyrics.pack(side=tk.RIGHT, fill=tk.Y)

        self.lyrics_text = tk.Text(
            text_container,
            height=12,
            bg=c["bg"],   
            fg=c["text"],
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
            yscrollcommand=scroll_lyrics.set,
        )
        self.lyrics_text.pack(fill=tk.BOTH, expand=True)
        scroll_lyrics.config(command=self.lyrics_text.yview)

        action_frame = ttk.Frame(right_frame, style="Main.TFrame")
        action_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        ttk.Button(
            action_frame,
            text="☁️ Mettre à jour via API",
            command=self.fetch_api_current,
            style="Custom.TButton",
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            action_frame,
            text="✏️ Éditer manuellement",
            command=self.edit_metadata_current,
            style="Custom.TButton",
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            action_frame,
            text="💾 Sauvegarder tags",
            command=self.save_metadata_current,
            style="Custom.TButton",
        ).pack(side=tk.LEFT)

    # ---------- Player bar ----------
    def _build_player_bar(self, parent):
        c = self.colors
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        center_frame = tk.Frame(parent, bg=c["player"])
        center_frame.grid(row=0, column=0, sticky="ew", padx=30, pady=(8, 0))
        self.player_center_frame = center_frame

        controls = tk.Frame(center_frame, bg=c["player"])
        controls.pack(side=tk.TOP, pady=(8, 4))
        self.player_controls_frame = controls

        btn_sec_style = {
            "bg": c["player"],
            "fg": "white",
            "activebackground": c["player"],
            "activeforeground": c["accent"],
            "bd": 0,
            "font": ("Segoe UI Symbol", 14),
            "cursor": "hand2",
            "relief": "flat",
        }

        self.btn_repeat = tk.Button(
            controls, text="🔁", command=self.toggle_repeat, **btn_sec_style
        )
        self.btn_repeat.pack(side=tk.LEFT, padx=10)

        self.btn_prev = tk.Button(
            controls, text="⏮", command=self.play_prev, **btn_sec_style
        )
        self.btn_prev.pack(side=tk.LEFT, padx=10)

        self.btn_play = ttk.Button(
            controls, text="▶", command=self.toggle_play_pause, width=5
        )
        self.btn_play.pack(side=tk.LEFT, padx=16)

        self.btn_next = tk.Button(
            controls, text="⏭", command=self.play_next, **btn_sec_style
        )
        self.btn_next.pack(side=tk.LEFT, padx=10)

        self.btn_vol = tk.Button(
            controls, text="🔊", command=self.toggle_mute, **btn_sec_style
        )
        self.btn_vol.pack(side=tk.LEFT, padx=10)

        self.theme_toggle_btn = tk.Button(
            controls,
            text="🌙" if self.current_theme == "dark" else "☀️",
            bg=c["player"],
            fg=c["text_dim"] if self.current_theme == "dark" else c["text"],
            bd=0,
            font=("Segoe UI", 12),
            cursor="hand2",
            activebackground=c["player"],
            activeforeground=c["accent"],
            command=self._toggle_theme,
        )
        self.theme_toggle_btn.pack(side=tk.LEFT, padx=10)

        self._add_tooltip(self.btn_repeat, "Répéter la piste")
        self._add_tooltip(self.btn_prev, "Piste précédente")
        self._add_tooltip(self.btn_play, "Lecture / pause")
        self._add_tooltip(self.btn_next, "Piste suivante")
        self._add_tooltip(self.btn_vol, "Activer / couper le son")
        self._add_tooltip(self.theme_toggle_btn, "Changer de thème clair / sombre")

        for b in [self.btn_repeat, self.btn_prev, self.btn_next, self.btn_vol, self.theme_toggle_btn]:
            b.bind("<Enter>", self._on_player_btn_enter)
            b.bind("<Leave>", self._on_player_btn_leave)

        progress_frame = tk.Frame(center_frame, bg=c["player"])
        progress_frame.pack(side=tk.TOP, fill=tk.X, pady=(2, 6))
        self.player_progress_frame = progress_frame

        self.lbl_current_time = tk.Label(
            progress_frame,
            text="0:00",
            bg=c["player"],
            fg=c.get("text_barre", c["text_dim"]),
            font=("Segoe UI", 10)
        )
        self.lbl_current_time.pack(side=tk.LEFT, padx=10)

        self.progress_var = tk.DoubleVar()
        self.progress_scale = ttk.Scale(
            progress_frame, variable=self.progress_var, from_=0, to=100
        )
        self.progress_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_scale.bind("<Button-1>", self._on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self._on_progress_release)

        self.lbl_total_time = tk.Label(
            progress_frame,
            text="0:00",
            bg=c["player"],
            fg=c.get("text_barre", c["text_dim"]),
            font=("Segoe UI", 10)
        )
        self.lbl_total_time.pack(side=tk.RIGHT, padx=10)

        status_bar = tk.Frame(parent, bg=c["player"])
        status_bar.grid(row=1, column=0, sticky="ew")
        self.player_status_bar = status_bar

        status_label = tk.Label(
            status_bar,
            textvariable=self.var_status,
            anchor="w",
            bg=c["player"],
            fg=c.get("text_barre", c["text_dim"]),
            font=("Segoe UI", 10),
            padx=15,
            pady=3,
        )
        status_label.pack(fill=tk.X)
        self.status_label = status_label

    def _on_player_btn_enter(self, event):
        c = self.colors
        event.widget.config(bg=c["accent_dark"])

    def _on_player_btn_leave(self, event):
        c = self.colors
        event.widget.config(bg=c["player"])

    def _build_menu(self):
        menubar = tk.Menu(self)
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Ouvrir un dossier…", command=self.open_directory)
        menu_file.add_separator()
        menu_file.add_command(label="Quitter", command=self.quit)
        menubar.add_cascade(label="Fichier", menu=menu_file)

        menu_view = tk.Menu(menubar, tearoff=0)
        menu_view.add_command(label="Mode clair", command=lambda: self._apply_theme("light"))
        menu_view.add_command(label="Mode sombre", command=lambda: self._apply_theme("dark"))
        menubar.add_cascade(label="Affichage", menu=menu_view)
        self.config(menu=menubar)

    # ============ THEME ==============
    def _apply_theme(self, theme_name: str):
        if theme_name not in self.themes:
            return

        self.current_theme = theme_name
        self.colors = self.themes[theme_name]
        c = self.colors
        self.configure(bg=c["bg"])

        self._setup_styles()

        if hasattr(self, "listbox"):
            try:
                self.listbox.config(
                    bg=c["list_bg"],
                    fg=c["list_fg"],
                    selectbackground=c["list_sel_bg"],
                    selectforeground=c["list_sel_fg"],
                )
            except Exception:
                pass

        if self.sidebar_button_frame is not None:
            try:
                self.sidebar_button_frame.config(bg=c["sidebar"])
                for child in self.sidebar_button_frame.winfo_children():
                    if isinstance(child, tk.Button):
                        child.config(
                            bg=c["sidebar"],
                            fg=c["text"],
                            activebackground=c["input_bg"],
                            activeforeground=c["accent"],
                        )
            except Exception:
                pass

        for frame in [
            self.player_center_frame,
            self.player_controls_frame,
            self.player_progress_frame,
            self.player_status_bar,
        ]:
            if frame is not None:
                try:
                    frame.config(bg=c["player"])
                except Exception:
                    pass

        if hasattr(self, "lbl_current_time"):
            self.lbl_current_time.config(
                bg=c["player"],
                fg=c.get("text_barre", c["text_dim"])
            )
        if hasattr(self, "lbl_total_time"):
            self.lbl_total_time.config(
                bg=c["player"],
                fg=c.get("text_barre", c["text_dim"])
            )
        if self.status_label is not None:
            self.status_label.config(
                bg=c["player"],
                fg=c.get("text_barre", c["text_dim"])
            )

        for b in [self.btn_repeat, self.btn_prev, self.btn_next, self.btn_vol]:
            if b is not None:
                b.config(
                    bg=c["player"],
                    fg="white",
                    activebackground=c["player"],
                    activeforeground=c["accent"],
                )
        if self.theme_toggle_btn is not None:
            self.theme_toggle_btn.config(
                text="🌙" if self.current_theme == "dark" else "☀️",
                bg=c["player"],
                fg=c["text_dim"] if self.current_theme == "dark" else c["text"],
                activebackground=c["player"],
                activeforeground=c["accent"],
            )

        if self.lbl_title is not None:
            self.lbl_title.config(bg=c["bg"], fg=c["text"])
        if self.lbl_artist is not None:
            self.lbl_artist.config(bg=c["bg"], fg=c["text"])
        if self.lbl_details is not None:
            self.lbl_details.config(bg=c["bg"], fg=c["text_dim"])
            
        header_lecture = getattr(self, 'lbl_header_lecture', None)
        if header_lecture:
            header_lecture.config(bg=c["bg"], fg=c["text_dim"])
            
        header_paroles = getattr(self, 'lbl_header_paroles', None)
        if header_paroles:
            header_paroles.config(bg=c["bg"], fg=c["text_dim"])

        header_logo = getattr(self, 'lbl_header_logo', None)
        if header_logo:
            header_logo.config(bg=c["sidebar"], fg=c["accent"])

        header_search = getattr(self, 'lbl_header_search', None)
        if header_search:
            header_search.config(bg=c["sidebar"], fg=c["text_barre"])

        header_lib = getattr(self, 'lbl_header_lib', None)
        if header_lib:
            header_lib.config(bg=c["sidebar"], fg=c["text_barre"])

        header_tracks = getattr(self, 'lbl_header_tracks', None)
        if header_tracks:
            header_tracks.config(bg=c["sidebar"], fg=c["text_barre"])

        if hasattr(self, "lyrics_text"):
            self.lyrics_text.config(bg=c["bg"], fg=c["text"])

        if hasattr(self, "cover_label"):
            self.cover_label.config(bg=c["bg"])

        if HAS_PIL:
            self.placeholder_image = self._create_placeholder_cover(size=320)
            if self.cover_image_ref is None:
                self._clear_cover()

    def _toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._apply_theme(new_theme)

    # ============ LOGIC ==============
    def open_directory(self):
        directory = filedialog.askdirectory()
        if not directory:
            return
        try:
            self.library = MusicLibrary()
            self.library.load_directory(Path(directory))
            self.audio_files = list(self.library.files)
            self.displayed_files = list(self.audio_files)
            self.current_index = None
            self.is_playing = False
            self.is_paused = False

            self.var_title.set("Aucune lecture")
            self.var_artist.set("--")
            self.var_details.set("")
            self.var_duration.set("0")
            self.var_path.set("")
            self.var_status.set(f"Dossier chargé : {directory}")

            self._set_lyrics_text("")
            self._clear_cover()
            self._refresh_listbox()
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def on_search_change(self, *args):
        query = self.var_search.get().lower().strip()
        if not query:
            self.displayed_files = list(self.audio_files)
        else:
            filtered = []
            for audio in self.audio_files:
                md = getattr(audio, "metadata", {}) or {}
                txt_search = (f"{audio.filepath.stem} {md.get('title','')} {md.get('artist','')}").lower()
                if query in txt_search:
                    filtered.append(audio)
            self.displayed_files = filtered
        self._refresh_listbox()

    def _refresh_listbox(self):
        # Nettoyage du tableau
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.index_to_audio.clear()

        if not self.audio_files:
            return

        # Remplissage
        for idx, audio in enumerate(self.displayed_files):
            # Extraction propre des données pour l'affichage
            md = getattr(audio, "metadata", {}) or {}
            
            titre = md.get("title") or audio.filepath.stem
            artiste = md.get("artist") or "--"
            
            # Formatage de la durée
            try:
                d = audio.get_duration()
                duree = f"{int(d//60)}:{int(d%60):02d}"
            except:
                duree = "--:--"

            # Insertion dans le Treeview (iid correspond à l'index pour retrouver le fichier facilement)
            self.tree.insert(
                "", 
                tk.END, 
                iid=str(idx), 
                values=(titre, artiste, duree)
            )
            
            self.index_to_audio[idx] = audio

    def on_selection_change(self, event):
        # Récupère l'ID de l'item sélectionné
        selected_items = self.tree.selection()
        if not selected_items:
            return
            
        # L'ID (iid) est l'index que nous avons défini dans _refresh_listbox (str(idx))
        idx_str = selected_items[0]
        try:
            idx = int(idx_str)
            if idx in self.index_to_audio:
                self.play_from_index(idx)
        except ValueError:
            pass

    def play_from_index(self, idx: int):
        self.current_index = idx
        self.current_offset = 0.0
        audio = self.index_to_audio.get(idx)
        if not audio:
            return

        try:
            md = audio.extract_metadata()
        except:
            md = {}

        title = md.get("title") or audio.filepath.stem
        artist = md.get("artist") or "Artiste inconnu"

        self.var_title.set(title)
        self.var_artist.set(artist)
        self.var_path.set(str(audio.filepath))
        self.var_album_internal = md.get("album") or ""
        self.var_year_internal = str(md.get("year") or "")
        details = []
        if self.var_album_internal:
            details.append(self.var_album_internal)
        if self.var_year_internal:
            details.append(self.var_year_internal)
        self.var_details.set(" • ".join(details) if details else "")

        self._update_cover(audio, force_validation=False)


        try:
            dur = audio.get_duration()
            self.var_duration.set(f"{round(dur, 1)} s")
            self.lbl_total_time.config(text=self._fmt_time(dur))
        except:
            self.var_duration.set("0")
            self.lbl_total_time.config(text="0:00")

        self._set_lyrics_text("Chargement des paroles...")
        self.var_status.set("Chargement des paroles...")

        if self.audio_player_enabled:
            try:
                pygame.mixer.music.load(str(audio.filepath))
                pygame.mixer.music.play()
                self.is_playing = True
                self.is_paused = False
                self.btn_play.config(text="⏸")
                self.var_status.set(f"Lecture : {title}")
            except Exception as e:
                print("Erreur audio:", e)
                self.var_status.set("Erreur lecture audio.")

        def _bg_lyrics(aud, i):
            try:
                l = self.metadata_fetcher.fetch_lyrics_for_audio(aud)
            except:
                l = None

            def _ui():
                if self.current_index != i:
                    return
                if l:
                    self._set_lyrics_text(l)
                    self.var_status.set("Paroles chargées.")
                else:
                    self._set_lyrics_text("")
                    self.var_status.set("Aucune parole trouvée.")
            self.after(0, _ui)

        threading.Thread(target=_bg_lyrics, args=(audio, idx), daemon=True).start()

    def _progress_loop(self):
        if (
            self.audio_player_enabled
            and self.is_playing
            and not self.is_paused
            and not self.user_dragging_progress
        ):
            try:
                current_ms = pygame.mixer.music.get_pos()
                if current_ms >= 0:
                    act = self.current_offset + (current_ms / 1000.0)
                    t_str = self.var_duration.get().replace(" s", "")
                    tot = float(t_str) if t_str else 0.0
                    if tot > 0:
                        self.progress_var.set((act / tot) * 100)
                        self.lbl_current_time.config(text=self._fmt_time(act))
            except:
                pass
            
            try:
                if not pygame.mixer.music.get_busy() and self.is_playing:
                    if self.repeat and self.current_index is not None:
                        self.play_from_index(self.current_index)
                    else:
                        self.play_next()
            except:
                pass
        self.after(500, self._progress_loop)

    def _fmt_time(self, s: float) -> str:
        return f"{int(s//60)}:{int(s%60):02d}"

    def toggle_play_pause(self):
        if not self.audio_player_enabled:
            return
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.btn_play.config(text="⏸")
        elif self.is_playing:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.btn_play.config(text="▶")
        else:
            if self.current_index is not None:
                self.play_from_index(self.current_index)

    def play_next(self):
        if self.current_index is not None and self.displayed_files:
            # 1. Calcul du nouvel index
            idx = (self.current_index + 1) % len(self.displayed_files)
            
            # 2. Conversion en ID pour le Treeview (on a utilisé str(idx) comme identifiant)
            item_id = str(idx)
            
            # 3. Sélection visuelle dans le Treeview
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id) # Sélectionne la ligne
                self.tree.see(item_id)           # Scrolle pour la rendre visible
                self.tree.focus(item_id)         
            self.play_from_index(idx)

    def play_prev(self):
        if self.current_index is not None and self.displayed_files:
            # 1. Calcul du nouvel index (avec modulo pour revenir à la fin si on est au début)
            idx = (self.current_index - 1) % len(self.displayed_files)            
            # 2. Sélection visuelle dans le Treeview
            item_id = str(idx)            
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id)
                self.tree.see(item_id)
                self.tree.focus(item_id)

            self.play_from_index(idx)
    def toggle_repeat(self):
        self.repeat = not self.repeat
        self.btn_repeat.config(fg=self.colors["accent"] if self.repeat else "white")

    def toggle_mute(self):
        if not self.audio_player_enabled:
            return
        self.muted = not self.muted
        pygame.mixer.music.set_volume(0.0 if self.muted else self.volume)
        self.btn_vol.config(text="🔈" if self.muted else "🔊")

    def _on_progress_press(self, event):
        self.user_dragging_progress = True

    def _on_progress_release(self, event):
        self.user_dragging_progress = False
        self._seek_absolute(self.progress_scale.get())

    def _seek_absolute(self, pct: float):
        if not self.audio_player_enabled or not self.var_duration.get():
            return
        try:
            tot = float(self.var_duration.get().replace(" s", ""))
        except:
            return
        new_t = (pct / 100.0) * tot
        self.current_offset = new_t
        try:
            pygame.mixer.music.play(start=new_t)
        except:
            try:
                pygame.mixer.music.rewind()
                pygame.mixer.music.set_pos(new_t)
            except:
                pass
        self.is_playing = True
        self.is_paused = False
        self.btn_play.config(text="⏸")

    # --------- API & METADATA ----------
    def fetch_api_current(self):
        """Version Priorité Utilisateur : Force l'utilisation du texte de l'écran pour la recherche"""
        if self.current_index is None:
            messagebox.showwarning("Attention", "Aucune piste sélectionnée")
            return
        
        audio = self.index_to_audio.get(self.current_index)
        if not audio: return

        # 1. INPUTS UI (Ce que vous avez tapé)
        screen_title = self.var_title.get()
        screen_artist = self.var_artist.get()
        
        # On prépare l'objet
        if not audio.metadata: audio.metadata = {}
        audio.metadata['title'] = screen_title
        audio.metadata['artist'] = screen_artist if screen_artist != "--" else ""

        self.var_status.set(f"Préparation : {screen_title}...")

        # 2. ARRÊT & DÉVERROUILLAGE
        was_playing = self.is_playing
        was_paused = self.is_paused
        current_pos = 0.0
        
        if self.audio_player_enabled and (self.is_playing or self.is_paused):
            try:
                current_ms = pygame.mixer.music.get_pos()
                if current_ms >= 0:
                    current_pos = self.current_offset + (current_ms / 1000.0)
            except: pass
            pygame.mixer.music.stop()
            try: pygame.mixer.music.unload()
            except AttributeError: pass
            self.is_playing = False; self.is_paused = False
        
        try:
            # 3. PRE-SAUVEGARDE (On tente d'écrire sur le disque)
            audio.save_metadata()
            time.sleep(0.5)
            
            # 4. RELOAD (Lecture technique)
            # On relit pour avoir la durée, le bitrate, etc.
            refreshed_tags = audio.extract_metadata()
            if refreshed_tags:
                # ATTENTION : On ne laisse pas le reload écraser le titre si le reload est vide !
                # On garde les autres infos (album, année existante...)
                old_title = audio.metadata.get('title') # Votre input "malvil"
                old_artist = audio.metadata.get('artist')
                
                audio.metadata = refreshed_tags
                
                # === FIX CRITIQUE ICI ===
                # Si le reload du disque renvoie un titre vide ou nul, on remet VOTRE input
                # C'est ça qui manquait : on force l'API à chercher "malvil" et pas ""
                if screen_title and (not audio.metadata.get('title') or audio.metadata.get('title') == ""):
                    audio.metadata['title'] = screen_title
                else:
                    # Même si le disque renvoie quelque chose, pour la recherche API, 
                    # on préfère généralement ce que l'utilisateur vient de corriger manuellement
                    audio.metadata['title'] = screen_title
                    
                if screen_artist and screen_artist != "--":
                    audio.metadata['artist'] = screen_artist

            # Log pour vérifier que "malvil" est bien là avant l'envoi
            print(f"DEBUG: Titre envoyé à l'API : '{audio.metadata.get('title')}'")

            # 5. APPEL API
            self.var_status.set(f"Recherche API pour : {audio.metadata.get('title')}...")
            res = self.metadata_fetcher.update_audio_file_metadata(audio)
            
            time.sleep(0.5)

            # 6. REFRESH FINAL (Pour afficher le résultat Spotify)
            final_tags = audio.extract_metadata()
            if final_tags:
                audio.metadata = final_tags

            # 7. REPRISE LECTURE
            if self.audio_player_enabled and was_playing:
                try:
                    pygame.mixer.music.load(str(audio.filepath))
                    pygame.mixer.music.play(start=current_pos)
                    self.is_playing = True
                    self.is_paused = was_paused
                    if was_paused: pygame.mixer.music.pause()
                    self.btn_play.config(text="⏸" if not was_paused else "▶")
                except Exception: pass
            
            # GESTION RESULTAT
            if not res:
                self.var_status.set("API : Aucun résultat.")
                messagebox.showinfo("Info", "Pas de résultat Spotify.")
            else:
                messagebox.showinfo("Succès", "Tags mis à jour !")

            # MISE A JOUR UI
            md = audio.metadata or {}
            self.var_title.set(md.get("title", screen_title))
            self.var_artist.set(md.get("artist", screen_artist))
            self.var_album_internal = md.get("album", "")
            self.var_year_internal = str(md.get("year", ""))
            
            details = []
            if self.var_album_internal: details.append(self.var_album_internal)
            if self.var_year_internal: details.append(self.var_year_internal)
            self.var_details.set(" • ".join(details))
            
            self._update_cover(audio, force_validation=True)
            self._refresh_listbox()
            
            def _bg_lyrics():
                l = self.metadata_fetcher.fetch_lyrics_for_audio(audio)
                if l: self._set_lyrics_text(l)
            threading.Thread(target=_bg_lyrics, daemon=True).start()
            
        except Exception as e:
            if self.audio_player_enabled and was_playing:
                try:
                    pygame.mixer.music.load(str(audio.filepath))
                    pygame.mixer.music.play(start=current_pos)
                    self.is_playing = True
                except: pass
            print(f"Erreur critique: {e}")
            messagebox.showerror("Erreur", str(e))

            
    
    def save_metadata_current(self):
        """Sauvegarde les métadonnées affichées dans le fichier audio"""
        if self.current_index is None:
            messagebox.showwarning("Attention", "Aucune piste sélectionnée")
            return
        
        audio = self.index_to_audio.get(self.current_index)
        if not audio:
            return
        
        was_playing = self.is_playing
        was_paused = self.is_paused
        current_pos = 0.0
        
        if self.audio_player_enabled and was_playing:
            try:
                current_ms = pygame.mixer.music.get_pos()
                if current_ms >= 0:
                    current_pos = self.current_offset + (current_ms / 1000.0)
            except:
                pass
        
        try:
            # ÉTAPE 1 : Arrêter complètement la lecture pour libérer le fichier
            if self.audio_player_enabled:
                if self.is_playing or self.is_paused: # Tenter l'arrêt même si l'état est confus
                    pygame.mixer.music.stop()
                
                # AJOUT : Décharger explicitement le fichier pour s'assurer que le verrou est levé
                try:
                    pygame.mixer.music.unload()
                except:
                    # Gérer les versions où unload() n'existe pas ou échoue
                    pass

                self.is_playing = False
                self.is_paused = False
            
            if not hasattr(audio, 'metadata') or audio.metadata is None:
                audio.metadata = {}
            
            audio.metadata['title'] = self.var_title.get()
            audio.metadata['artist'] = self.var_artist.get()
            audio.metadata['album'] = self.var_album_internal
            
            if self.var_year_internal and self.var_year_internal.isdigit():
                audio.metadata['year'] = int(self.var_year_internal)
            
            audio.save_metadata()
            
            self._refresh_listbox()
            
            self.var_status.set(f"Tags sauvegardés : {audio.filepath.name}")
            messagebox.showinfo("Succès", "Métadonnées sauvegardées dans le fichier")
            
            if was_playing and self.audio_player_enabled:
                try:
                    pygame.mixer.music.load(str(audio.filepath))
                    pygame.mixer.music.play(start=current_pos)
                    self.is_playing = True
                    self.is_paused = was_paused
                    if was_paused:
                        pygame.mixer.music.pause()
                    self.btn_play.config(text="⏸" if not was_paused else "▶")
                except Exception as e:
                    print(f"Erreur reprise lecture : {e}")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de sauvegarder : {str(e)}")
            self.var_status.set("Erreur lors de la sauvegarde")
            
            if was_playing and self.audio_player_enabled:
                try:
                    pygame.mixer.music.load(str(audio.filepath))
                    pygame.mixer.music.play(start=current_pos)
                    self.is_playing = True
                except:
                    pass

    def edit_metadata_current(self):
        """Ouvre une fenêtre de dialogue pour éditer manuellement les métadonnées"""
        if self.current_index is None:
            messagebox.showwarning("Attention", "Aucune piste sélectionnée")
            return
        
        audio = self.index_to_audio.get(self.current_index)
        if not audio:
            return
        
        dialog = tk.Toplevel(self)
        dialog.title("Éditer les métadonnées")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()
        
        c = self.colors
        dialog.configure(bg=c["bg"])
        
        current_title = self.var_title.get()
        current_artist = self.var_artist.get()
        current_album = self.var_album_internal
        current_year = self.var_year_internal
        
        main_frame = tk.Frame(dialog, bg=c["bg"], padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(
            main_frame, 
            text="Titre :", 
            bg=c["bg"], 
            fg=c["text"],
            font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        entry_title = tk.Entry(main_frame, font=("Segoe UI", 10), width=40)
        entry_title.insert(0, current_title)
        entry_title.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        
        tk.Label(
            main_frame, 
            text="Artiste :", 
            bg=c["bg"], 
            fg=c["text"],
            font=("Segoe UI", 10, "bold")
        ).grid(row=2, column=0, sticky="w", pady=(0, 5))
        
        entry_artist = tk.Entry(main_frame, font=("Segoe UI", 10), width=40)
        entry_artist.insert(0, current_artist)
        entry_artist.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        
        tk.Label(
            main_frame, 
            text="Album :", 
            bg=c["bg"], 
            fg=c["text"],
            font=("Segoe UI", 10, "bold")
        ).grid(row=4, column=0, sticky="w", pady=(0, 5))
        
        entry_album = tk.Entry(main_frame, font=("Segoe UI", 10), width=40)
        entry_album.insert(0, current_album)
        entry_album.grid(row=5, column=0, sticky="ew", pady=(0, 15))
        
        tk.Label(
            main_frame, 
            text="Année :", 
            bg=c["bg"], 
            fg=c["text"],
            font=("Segoe UI", 10, "bold")
        ).grid(row=6, column=0, sticky="w", pady=(0, 5))
        
        entry_year = tk.Entry(main_frame, font=("Segoe UI", 10), width=40)
        entry_year.insert(0, current_year)
        entry_year.grid(row=7, column=0, sticky="ew", pady=(0, 20))
        
        main_frame.columnconfigure(0, weight=1)
        
        btn_frame = tk.Frame(main_frame, bg=c["bg"])
        btn_frame.grid(row=8, column=0, sticky="ew")

        def save_and_close():
            self.var_title.set(entry_title.get())
            self.var_artist.set(entry_artist.get())
            self.var_album_internal = entry_album.get()
            self.var_year_internal = entry_year.get()
            
            details = []
            if self.var_album_internal:
                details.append(self.var_album_internal)
            if self.var_year_internal:
                details.append(self.var_year_internal)
            self.var_details.set(" • ".join(details) if details else "")
            
            dialog.destroy()
            
            if messagebox.askyesno("Sauvegarder ?", "Voulez-vous sauvegarder ces modifications dans le fichier ?"):
                self.save_metadata_current()
        
        tk.Button(
            btn_frame,
            text="Annuler",
            command=dialog.destroy,
            bg=c["input_bg"],
            fg=c["text"],
            font=("Segoe UI", 10),
            padx=20,
            pady=8,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(
            btn_frame,
            text="Appliquer",
            command=save_and_close,
            bg=c["accent"],
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=20,
            pady=8,
            cursor="hand2"
        ).pack(side=tk.LEFT)

    # --------- Playlist placeholders ----------
    def open_playlist(self):
        filename = filedialog.askopenfilename(
            title="Ouvrir une playlist XSPF",
            filetypes=[("Playlists XSPF", "*.xspf"), ("Tous les fichiers", "*.*")]
        )
        if not filename:
            return

        try:
            # --- LOGIQUE DE LECTURE XML ---
            tree = ET.parse(filename)
            root = tree.getroot()
            
            ns = {'ns': "http://xspf.org/ns/0/"}
            
            new_files = []
            
            for track in root.findall(".//ns:track", ns):
                location = track.find("ns:location", ns)
                if location is not None and location.text:
                    uri = location.text
                    
                    parsed = urlparse(uri)
                    path_str = unquote(parsed.path)
                    
                    if os.name == 'nt' and path_str.startswith('/') and ':' in path_str:
                        path_str = path_str.lstrip('/')
                    
                    p = Path(path_str)
                    
                    if p.exists():
                        # --- CORRECTION ICI ---
                        # On crée l'objet, puis on LIT SES TAGS immédiatement
                        audio_obj = None
                        suffix = p.suffix.lower()
                        
                        if suffix == '.mp3':
                            audio_obj = MP3File(p)
                        elif suffix == '.flac':
                            audio_obj = FLACFile(p)
                        
                        if audio_obj:
                            audio_obj.extract_metadata() 
                            new_files.append(audio_obj)

            if not new_files:
                messagebox.showwarning("Attention", "Aucun fichier valide trouvé dans cette playlist.")
                return

            # --- MISE A JOUR DE L'INTERFACE ---
            self.library = MusicLibrary() 
            self.audio_files = new_files
            self.displayed_files = list(self.audio_files)
            
            self.current_index = None
            self.is_playing = False
            self.var_title.set("Playlist chargée")
            self.var_artist.set(f"{len(new_files)} pistes")
            self.var_path.set(filename)
            
            self._refresh_listbox()
            self.var_status.set(f"Playlist chargée : {Path(filename).name}")

        except Exception as e:
            print(f"Erreur lecture XSPF: {e}")
            messagebox.showerror("Erreur", f"Impossible de lire le fichier XSPF :\n{e}")

    def generate_playlist_selection(self):
        # 1. Récupérer les fichiers (soit la sélection, soit tout)
        selection_indices = self.tree.selection()
        files_to_save = []
        
        if selection_indices:
            for idx in selection_indices:
                if idx in self.index_to_audio:
                    files_to_save.append(self.index_to_audio[idx])
        else:
            files_to_save = self.displayed_files

        if not files_to_save:
            messagebox.showwarning("Attention", "Rien à sauvegarder.")
            return

        # 2. Demander où enregistrer
        filename = filedialog.asksaveasfilename(
            title="Sauvegarder la playlist",
            defaultextension=".xspf",
            filetypes=[("Playlists XSPF", "*.xspf")]
        )
        if not filename:
            return

        try:
            # 3. Utiliser PlaylistGenerator 
            # On passe un dossier parent bidon pour l'init, car on va override les fichiers juste après
            pg = PlaylistGenerator(dossier=Path(filename).parent, fichier_sortie=filename)
            
            # C'est ici qu'on utilise la méthode existante pour forcer la liste de fichiers
            pg.set_audio_files(files_to_save)
            
            # On construit les balises <track> en mémoire
            pg.construire_piste()
            
            # On écrit le fichier sur le disque
            pg.ecrire_xspf(titre=f"Playlist {Path(filename).stem}")
            
            self.var_status.set(f"Sauvegardé : {Path(filename).name}")
            messagebox.showinfo("Succès", "Playlist exportée avec succès !")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la création XSPF :\n{e}")

    # --------- Cover & lyrics ----------
    def _create_placeholder_cover(self, size=320):
        if not HAS_PIL:
            return None
        c = self.colors
        img = Image.new("RGB", (size, size), c["bg"])
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 150)
        except:
            font = ImageFont.load_default()
        text = "♪"
        try: 
            bbox = draw.textbbox((0, 0), text, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        except:
            w, h = 50, 50
        draw.text(((size-w)/2, (size-h)/2 - 20), text, font=font, fill=c["accent"])
        m = 10
        draw.rectangle([m, m, size-m, size-m], outline=c["border"], width=2)
        return ImageTk.PhotoImage(img)

    def _clear_cover(self):
        if self.placeholder_image:
            self.cover_label.config(image=self.placeholder_image)
            self.cover_image_ref = self.placeholder_image

    def _update_cover(self, audio: AudioFile, force_validation: bool = False):
        """
        Affiche la cover. 
        PRIORITÉ : Image téléchargée (disque) > Image interne (tags).
        """
        if not HAS_PIL:
            return

        # --- ETAPE 1 : Vérifier si une image existe sur le disque (API / Cache) ---
        # On fait cela EN PREMIER pour que la nouvelle image prime sur l'ancienne
        cover_path = None
        try:
            if hasattr(self.metadata_fetcher, "ensure_cover_image"):
                cover_path = self.metadata_fetcher.ensure_cover_image(audio)
        except Exception as e:
            print("Erreur ensure_cover_image:", e)
            cover_path = None

        if cover_path and cover_path.exists():
            try:
                img = Image.open(cover_path)
                img.thumbnail((320, 320))
                photo = ImageTk.PhotoImage(img)

                # Affichage
                self.cover_label.config(image=photo)
                self.cover_image_ref = photo
                self.cover_label.update_idletasks() # Force l'affichage avant la popup

                # --- VALIDATION (Uniquement si demandé) ---
                if force_validation:
                    titre = self.var_title.get() or audio.filepath.stem
                    ok = messagebox.askyesno(
                        "Nouvelle pochette trouvée",
                        f"Une image a été téléchargée pour :\n{titre}\n\nVoulez-vous utiliser cette image ?"
                    )

                    if not ok:
                        # L'utilisateur refuse : on supprime le fichier téléchargé
                        try:
                            cover_path.unlink()
                            print("[cover] Image refusée et supprimée.")
                        except Exception:
                            pass
                        
                        # On relance l'update sans validation pour remettre l'ancienne cover (si elle existe)
                        self._update_cover(audio, force_validation=False)
                        return
                    else:
                        print("[cover] Image validée.")
                        # Ici, l'image reste sur le disque dans le dossier de l'album
                        # (Ce qui correspond à la consigne "enregistrer dans le dossier de l'album")

                return # On a affiché l'image disque, on s'arrête là.
            except Exception as e:
                print("Erreur chargement cover fichier :", e)

        # --- ETAPE 2 : Si pas d'image disque, on regarde l'image interne (Tags ID3/FLAC) ---
        # C'est le "fallback" si l'API n'a rien trouvé
        data = audio.get_cover_art()
        if data:
            try:
                img = Image.open(BytesIO(data))
                img.thumbnail((320, 320))
                photo = ImageTk.PhotoImage(img)
                self.cover_label.config(image=photo)
                self.cover_image_ref = photo
                return
            except Exception:
                pass

        # --- ETAPE 3 : Rien trouvé nulle part ---
        self._clear_cover()

    def _set_lyrics_text(self, text: str):
        self.lyrics_text.config(state=tk.NORMAL)
        self.lyrics_text.delete("1.0", tk.END)
        self.lyrics_text.insert(tk.END, text if text else "Paroles non disponibles.")
        self.lyrics_text.config(state=tk.DISABLED)


    def on_drop_files(self, event):
        """Gère les fichiers dropés dans la fenêtre"""
        raw_data = event.data
        print(f"Fichiers reçus (raw): {raw_data}")

        # S'assurer que le chemin est bien parsé:
        paths = []
        if raw_data.startswith("{") and raw_data.endswith('}:'):
            # regex (cherche entre accolades )
            import re
            parts = re.findall(r'\{.*?\}|\S+', raw_data)
            for p in parts:
                path_str = p.strip('{}')
                paths.append(Path(path_str))
        else:
            # Cas simple (un seul fichier sans espace ou liste simple)
            paths.append(Path(raw_data))

        count_added = 0
        new_files = []

        for p in paths:
            if p.is_dir():
                # Si c'est un dossier, on utilise la méthode existante de lib
                # Idéalement, il faudrait une méthode "add_directory" dans MusicLibrary ( si on a le temps bien sur)
                temp_lib = MusicLibrary()
                temp_lib.load_directory(p)
                new_files.extend(temp_lib.files)
            elif p.is_file() and p.suffix.lower() in ['.mp3', '.wav', '.ogg', '.flac']:
                # Création manuelle d'un AudioFile si c'est un fichier seul
                suffix = p.suffix.lower()
                if suffix == '.mp3':
                    new_files.append(MP3File(p))
                elif suffix == '.flac':
                    new_files.append(FLACFile(p))

        if new_files:
            # On ajoute à la liste existante
            self.audio_files.extend(new_files)
            self.displayed_files = list(self.audio_files) # Reset filtre recherche
            
            # Mise à jour IHM
            self._refresh_listbox()
            self.var_status.set(f"{len(new_files)} fichier(s) ajouté(s) par glisser-déposer.")
        else:
            self.var_status.set("Aucun fichier audio valide détecté.")


if __name__ == "__main__":
    app = MusicLibraryGUI()
    app.mainloop()