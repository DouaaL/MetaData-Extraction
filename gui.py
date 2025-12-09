#!/usr/bin/env python3
import sys
import threading
from pathlib import Path
from typing import List, Dict, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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

# Accès à src/
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.append(str(SRC_DIR))

# Importations ou Classes Dummy
try:
    from library.models.music_library import MusicLibrary
    from library.models.audio_file import AudioFile
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


class MusicLibraryGUI(tk.Tk):
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
                "text_barre": "#F2F2F7",   # couleur barre (temps + statut + titres)
                "border": "#1E1E2A",
                "list_bg": "#10101A",
                "list_fg": "#F2F2F7",
                "list_sel_bg": "#D4A017",
                "list_sel_fg": "#0A0A12",
                "input_bg": "#1A1A28",
                "input_fg": "#F2F2F7",
            },
            "light": {
                "bg": "#E8ECF7",          # Fond global glacé
                "sidebar": "#F4F7FF",     # Panneau clair
                "card": "#F4F7FF",        # Cartes + blocs
                "player": "#2D51B3",      # Barre du player
                "accent": "#1936B7",      # Bleu brillant (boutons)
                "accent_dark": "#1936B7", # Bleu foncé (active/hover)
                "text": "#1A1F36",        # Texte principal
                "text_barre": "#1A1F36",  # le son, temps et bienvenue
                "text_dim": "#505560",    # Texte secondaire
                "border": "#C7D1E6",      # Bordure froide très légère
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
        self.lbl_header_pochette = None   # plus utilisé mais on laisse pour éviter d'erreurs
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

        # sv_ttk suit clair/sombre si dispo
        if HAS_SV_TTK:
            if self.current_theme == "dark":
                sv_ttk.use_dark_theme()
            else:
                sv_ttk.use_light_theme()

        style.configure("Sidebar.TFrame", background=c["sidebar"])
        style.configure("Player.TFrame", background=c["player"])
        style.configure("Main.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"])

        # Boutons accent
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
        
        # LOGIQUE COULEUR BOUTONS GRIS (API / sauvegarde)
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

        # SIDEBAR
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(15, 15))
        sidebar.grid(row=0, column=0, sticky="nsew")
        self._build_sidebar(sidebar)

        # CONTENU PRINCIPAL
        main_content = ttk.Frame(self, style="Main.TFrame", padding=(20, 20))
        main_content.grid(row=0, column=1, sticky="nsew")
        self._build_main_content(main_content)

        # BARRE LECTEUR
        player_bar = ttk.Frame(self, style="Player.TFrame")
        player_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        player_bar.columnconfigure(0, weight=1)
        self._build_player_bar(player_bar)

    # ---------- Sidebar ----------
    def _build_sidebar(self, parent):
        c = self.colors
        parent.rowconfigure(4, weight=1)

        # Logo / Titre
        self.lbl_header_logo = tk.Label(
            parent,
            text="🎵 PyMetaPlay",
            font=("Segoe UI", 16, "bold"),
            bg=c["sidebar"], 
            fg=c["accent"],
        )
        self.lbl_header_logo.grid(row=0, column=0, sticky="w", pady=(0, 20))

        # Recherche
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

        # Menu
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

        # Liste
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

        self.listbox = tk.Listbox(
            list_container,
            bg=c["list_bg"],
            fg=c["list_fg"],
            bd=0,
            highlightthickness=0,
            selectbackground=c["list_sel_bg"],
            selectforeground=c["list_sel_fg"],
            font=("Segoe UI", 10),
            yscrollcommand=scrollbar.set,
            activestyle="none",
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.on_selection_change)

    # ---------- Contenu principal ----------
    def _build_main_content(self, parent):
        c = self.colors
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        # 1. Colonne gauche = cover
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
        
        # 2. Colonne droite
        right_frame = ttk.Frame(parent, style="Main.TFrame")
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.rowconfigure(2, weight=1)
        right_frame.columnconfigure(0, weight=1)

        # Bloc "Lecture en cours"
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

        # Bloc Paroles
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

        # Actions
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

        # Boutons player
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
            fg=c["text_dim"] if self.current_theme == "dark" else c["text"],  # <<< ici
            bd=0,
            font=("Segoe UI", 12),
            cursor="hand2",
            activebackground=c["player"],
            activeforeground=c["accent"],
            command=self._toggle_theme,
        )
        self.theme_toggle_btn.pack(side=tk.LEFT, padx=10)

        # Tooltips IHM
        self._add_tooltip(self.btn_repeat, "Répéter la piste")
        self._add_tooltip(self.btn_prev, "Piste précédente")
        self._add_tooltip(self.btn_play, "Lecture / pause")
        self._add_tooltip(self.btn_next, "Piste suivante")
        self._add_tooltip(self.btn_vol, "Activer / couper le son")
        self._add_tooltip(self.theme_toggle_btn, "Changer de thème clair / sombre")

        # Hover (affordance)
        for b in [self.btn_repeat, self.btn_prev, self.btn_next, self.btn_vol, self.theme_toggle_btn]:
            b.bind("<Enter>", self._on_player_btn_enter)
            b.bind("<Leave>", self._on_player_btn_leave)

        # Progression
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

        # Status
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

    # Hover handlers pour les boutons player
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

        # Listbox
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

        # Sidebar buttons
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

        # Player frames
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

        # Temps + statut = text_barre
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

        # Boutons player (couleurs adaptées au thème)
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

        # Titre / artiste / détails
        if self.lbl_title is not None:
            self.lbl_title.config(bg=c["bg"], fg=c["text"])
        if self.lbl_artist is not None:
            self.lbl_artist.config(bg=c["bg"], fg=c["text"])
        if self.lbl_details is not None:
            self.lbl_details.config(bg=c["bg"], fg=c["text_dim"])
            
        # En-têtes contenu
        header_lecture = getattr(self, 'lbl_header_lecture', None)
        if header_lecture:
            header_lecture.config(bg=c["bg"], fg=c["text_dim"])
            
        header_paroles = getattr(self, 'lbl_header_paroles', None)
        if header_paroles:
            header_paroles.config(bg=c["bg"], fg=c["text_dim"])

        # En-têtes Sidebar
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

        # Paroles et cover
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
        # Guidage utilisateur (IHM) : message clair selon le contexte
        self.listbox.delete(0, tk.END)
        self.index_to_audio.clear()

        if not self.audio_files:
            # Aucun fichier encore chargé
            self.listbox.insert(tk.END, "Aucun fichier chargé.")
            self.listbox.insert(tk.END, "Utilisez « Ouvrir un dossier » pour commencer.")
            return

        if not self.displayed_files:
            # Fichiers chargés mais recherche vide
            self.listbox.insert(tk.END, "Aucun résultat pour cette recherche.")
            self.listbox.insert(tk.END, "Essayez un autre mot-clé.")
            return

        for idx, audio in enumerate(self.displayed_files):
            name = audio.filepath.stem
            md = getattr(audio, "metadata", {}) or {}
            if md.get("title"):
                name = md.get("title")
                if md.get("artist"):
                    name += f" - {md.get('artist')}"
            self.listbox.insert(tk.END, f"{idx+1}. {name}")
            self.index_to_audio[idx] = audio

    def on_selection_change(self, event):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx not in self.index_to_audio:
            return
        self.play_from_index(idx)

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

        self._update_cover(audio)

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
            idx = (self.current_index + 1) % len(self.displayed_files)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
            self.play_from_index(idx)

    def play_prev(self):
        if self.current_index is not None and self.displayed_files:
            idx = (self.current_index - 1) % len(self.displayed_files)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
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

    def fetch_api_current(self):
        if self.current_index is None:
            return
        audio = self.index_to_audio.get(self.current_index)
        if not audio:
            return
        try:
            res = self.metadata_fetcher.update_audio_file_metadata(audio)
            self.play_from_index(self.current_index)
            l = self.metadata_fetcher.fetch_lyrics_for_audio(audio)
            if l:
                self._set_lyrics_text(l)
            messagebox.showinfo("API", "Données mises à jour" if res else "Pas de nouveauté")
        except Exception as e:
            messagebox.showerror("API Error", str(e))

    def save_metadata_current(self):
        if self.current_index is None:
            return
        audio = self.index_to_audio.get(self.current_index)
        try:
            audio.save_metadata()
            messagebox.showinfo("Succès", "Tags sauvegardés")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def open_playlist(self):
        messagebox.showinfo("Info", "À implémenter")

    def generate_playlist_selection(self):
        messagebox.showinfo("Info", "À implémenter")

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

    def _update_cover(self, audio: AudioFile):
        """
        Affiche la pochette du morceau :
        1. via tags (get_cover_art)
        2. via cover téléchargée pour CE fichier (ensure_cover_image)
           → affichage + validation utilisateur
        3. sinon placeholder ♪
        """
        if not HAS_PIL:
            return

        # 1) COVER intégrée dans les tags (ID3, etc.)
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
                pass  # on tente l'étape suivante

        # 2) COVER téléchargée via MetadataFetcher.ensure_cover_image (MusicBrainz)
        cover_path = None
        try:
            if hasattr(self.metadata_fetcher, "ensure_cover_image"):
                cover_path = self.metadata_fetcher.ensure_cover_image(audio)
        except Exception as e:
            print("Erreur ensure_cover_image:", e)
            cover_path = None

        if cover_path and cover_path.exists():
            try:
                # On charge l'image trouvée
                img = Image.open(cover_path)
                img.thumbnail((320, 320))
                photo = ImageTk.PhotoImage(img)

                # On l'affiche d'abord à l'écran
                self.cover_label.config(image=photo)
                self.cover_image_ref = photo

                # Puis on demande à l'utilisateur s'il valide cette pochette
                titre = self.var_title.get() or audio.filepath.stem
                ok = messagebox.askyesno(
                    "Valider la pochette",
                    f"Utiliser cette image comme pochette pour :\n\n{titre} ?"
                )

                if not ok:
                    # L'utilisateur refuse → on supprime le fichier et on revient au placeholder
                    try:
                        cover_path.unlink()
                        print("[cover] Cover refusée, fichier supprimé :", cover_path)
                    except Exception as e:
                        print("[cover] Erreur suppression cover refusée :", e)
                    self._clear_cover()
                else:
                    print("[cover] Cover validée par l’utilisateur :", cover_path)

                return  # dans tous les cas, on arrête ici
            except Exception as e:
                print("Erreur chargement cover téléchargée :", e)
                # on retombera sur le placeholder

        # 3) Rien trouvé ou échec → placeholder ♪
        self._clear_cover()

    def _set_lyrics_text(self, text: str):
        self.lyrics_text.config(state=tk.NORMAL)
        self.lyrics_text.delete("1.0", tk.END)
        self.lyrics_text.insert(tk.END, text if text else "Paroles non disponibles.")
        self.lyrics_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    app = MusicLibraryGUI()
    app.mainloop()
