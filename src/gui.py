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
CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent 

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from library.models.music_library import MusicLibrary
from library.models.audio_file import AudioFile
from library.models.mp3_file import MP3File
from library.models.flac_file import FLACFile
from library.core.playlist_generator import PlaylistGenerator
from library.core.file_explorer import FileExplorer
from library.core.metadatafetcher import MetadataFetcher
from library.core.lyricsresolver import LyricsResolver

    


# --------- Tooltip simple pour IHM (guidage) ----------
class Tooltip:
    """Crée une petite info-bulle (tooltip) qui s'affiche au survol d'un widget."""
    def __init__(self, widget, text: str):
        """Initialise le tooltip pour un widget spécifique."""
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        """Affiche la fenêtre d'info-bulle calculée près de la souris."""
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
        """Détruit la fenêtre d'info-bulle."""
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


class MusicLibraryGUI(TkinterDnD.Tk if HAS_DND else tk.Tk):
    """
    Interface graphique principale de l'application PyMetaPlay.

    Cette classe gère la fenêtre principale, la boucle d'événements, 
    le lecteur audio (via pygame) et l'interaction avec la bibliothèque musicale.

    Attributes:
        library (MusicLibrary): Instance de la bibliothèque gérant les fichiers.
        audio_files (List[AudioFile]): Liste complète des fichiers chargés.
        displayed_files (List[AudioFile]): Liste des fichiers affichés (filtrés par recherche).
        current_theme (str): Thème actif ('light' ou 'dark').
        is_playing (bool): Indique si une lecture est en cours.
    """
    def __init__(self):
        """
        Initialise la fenêtre principale, les variables d'état, le moteur audio
        et construit toute l'interface graphique.
        """
        super().__init__()
        self.title("PyMetaPlay")
        self.geometry("1200x800")
        self.minsize(1000, 680)

        # --- THEMES JOUR / NUIT ---
        self.themes = {
            "dark": {
                "bg": "#121212",             
                "sidebar": "#1E1E1E",        
                "player": "#252525",         
                "card": "#1E1E1E",
                "accent": "#82AAFF",                         
                "accent_dark": "#6889CC",    
                "text": "#E0E0E0",                           
                "text_dim": "#A0A0A0",        
                "text_barre": "#CCCCCC",
                "border": "#333333",
                "list_bg": "#1E1E1E",
                "list_fg": "#E0E0E0",
                "list_sel_bg": "#82AAFF",     
                "list_sel_fg": "#121212",    
                "input_bg": "#2C2C2C",
                "input_fg": "#FFFFFF",
            },
            "light": {
                "bg": "#E8ECF7",             
                "sidebar": "#F4F7FF",        
                "player": "#FFFFFF",         
                "card": "#FFFFFF",
                "accent": "#2962FF",         
                "accent_dark": "#0039CB",
                "text": "#212121",           
                "text_dim": "#757575",
                "text_barre": "#424242",
                "border": "#E0E0E0",
                "list_bg": "#FFFFFF",
                "list_fg": "#212121",
                "list_sel_bg": "#E3F2FD",    
                "list_sel_fg": "#2962FF",    
                "input_bg": "#FFFFFF",
                "input_fg": "#212121",
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
        self.shuffle_mode: bool = False

        #  Mini cover pour la playbar
        self.mini_cover_ref = None

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

        # Désactiver les contrôles audio si le backend audio n'est pas disponible
        self._update_audio_controls_state()

        # Boucle d'update du temps de lecture
        self.after(500, self._progress_loop)

        # Appliquer le thème initial
        self._apply_theme(self.current_theme)

        self.bind("<space>", self._on_space_pressed)

        # Message IHM au démarrage dans la liste
        self._refresh_listbox()

    # Helper tooltip
    def _add_tooltip(self, widget, text: str):
        """Ajoute une info-bulle à un widget donné."""
        Tooltip(widget, text)

    # ---------- Styles ----------
    def _setup_styles(self):
        """
        Configure les styles TTK (couleurs, polices, bordures) en fonction
        du thème actuel (Light ou Dark).
        """
        style = ttk.Style(self)
        c = self.colors

        # Si sv_ttk est présent, on l'active, mais on écrase ensuite avec nos couleurs
        if HAS_SV_TTK:
            if self.current_theme == "dark":
                sv_ttk.use_dark_theme()
            else:
                sv_ttk.use_light_theme()

        # --- Configuration Générale ---
        style.configure("Sidebar.TFrame", background=c["sidebar"])
        style.configure("Player.TFrame", background=c["player"])
        style.configure("Main.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"])

        # --- Treeview (La Liste) ---
        # On force les couleurs du Treeview pour qu'elles correspondent au thème
        style.configure(
            "Treeview",
            background=c["list_bg"],
            foreground=c["list_fg"],
            fieldbackground=c["list_bg"],
            borderwidth=0,
            font=("Segoe UI", 10)
        )
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        
        # Couleur de sélection (map)
        style.map(
            "Treeview",
            background=[("selected", c["list_sel_bg"])],
            foreground=[("selected", c["list_sel_fg"])]
        )

        # --- Barre de progression ---
        style.configure(
            "Player.Horizontal.TScale",
            background=c["player"],      
            troughcolor=c["border"],     
            bordercolor=c["player"],
            lightcolor=c["accent"],      
            darkcolor=c["accent"],
        )

        # --- Boutons Accent (Gros boutons bleus) ---
        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=8,
            background=c["accent"],
            foreground="#FFFFFF" if self.current_theme == "dark" else "#FFFFFF", # Toujours blanc sur l'accent bleu
        )
        style.map(
            "Accent.TButton",
            background=[("active", c["accent_dark"]), ("pressed", c["accent_dark"])],
        )
        
        # --- Boutons Custom (Gris/Neutre) ---
        if self.current_theme == "dark":
            btn_bg = "#3A3A3A"
            btn_fg = "#FFFFFF"
            btn_active = "#505050"
        else:
            btn_bg = "#E0E0E0" 
            btn_fg = "#000000"
            btn_active = "#D6D6D6"

        style.configure(
            "Custom.TButton",
            font=("Segoe UI", 9),
            padding=6,
            background=btn_bg,   
            foreground=btn_fg,   
        )
        style.map(
            "Custom.TButton",
            background=[("active", btn_active)],
        )

    
    # ---------- Layout général ----------
    def _build_layout(self):
        """Place les trois grandes zones principales (Sidebar, Main Content, Player Bar)."""
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
        """
        Trie la liste des fichiers audio dans le Treeview.
        
        Args:
            col (str): La colonne à trier ('titre', 'artiste', 'duree').
            reverse (bool): Si True, tri descendant. Sinon ascendant.
        """
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
        """Construit la barre latérale (Logo, Recherche, Boutons fichiers, Liste des pistes)."""
        c = self.colors
        
        # Configuration de la grille (Layout)
        parent.rowconfigure(0, weight=0) # Logo
        parent.rowconfigure(1, weight=0) # Header Recherche
        parent.rowconfigure(2, weight=0) # Barre Recherche
        parent.rowconfigure(3, weight=0) # Header Bibliotheque
        parent.rowconfigure(4, weight=0) # Boutons (TAILLE FIXE POUR PETITE RES)
        parent.rowconfigure(5, weight=0) # Header Pistes
        parent.rowconfigure(6, weight=1) # Liste 

        # 1. LOGO
        self.lbl_header_logo = tk.Label(
            parent,
            text="PyMetaPlay",
            font=("Segoe UI", 16, "bold"),
            bg=c["sidebar"], 
            fg=c["text"],
        )
        self.lbl_header_logo.grid(row=0, column=0, sticky="w", pady=(0, 20))

        # 2. HEADER RECHERCHE
        self.lbl_header_search = tk.Label(
            parent, 
            text="RECHERCHE", 
            font=("Segoe UI", 11, "bold"),
            bg=c["sidebar"], 
            fg=c["text_barre"]
        )
        self.lbl_header_search.grid(row=1, column=0, sticky="w")

        # 3. BARRE RECHERCHE
        search_frame = ttk.Frame(parent, style="Sidebar.TFrame")
        search_frame.grid(row=2, column=0, sticky="ew", pady=(5, 15))
        search_frame.columnconfigure(0, weight=1)

        self.var_search = tk.StringVar()
        # Use a lambda so the bound method keeps the correct `self` when called from Tcl
        self.var_search.trace("w", lambda *a: self.on_search_change())

        # Entry de recherche avec placeholder accessible
        self.search_entry = ttk.Entry(search_frame, textvariable=self.var_search)
        self.search_entry.grid(row=0, column=0, sticky="ew")

        # Placeholder text (accessible hint)
        self._search_placeholder = "nom auteur ou chanson"
        # Helper pour afficher/masquer le placeholder
        def _show_search_placeholder(event=None):
            """
            Mets un placeholder dans la bar de recherche
            """
            try:
                if not self.var_search.get():
                    self.var_search.set(self._search_placeholder)
                    try:
                        self.search_entry.config(foreground=self.colors.get("text_dim", "#757575"))
                    except Exception:
                        pass
            except Exception:
                pass

        def _clear_search_placeholder(event=None):
            """
            Enleve le placeholder a l'input
            """
            try:
                if self.var_search.get() == self._search_placeholder:
                    self.var_search.set("")
                    try:
                        self.search_entry.config(foreground=self.colors.get("input_fg", "#212121"))
                    except Exception:
                        pass
            except Exception:
                pass

        # Bind focus events
        self.search_entry.bind("<FocusIn>", _clear_search_placeholder)
        self.search_entry.bind("<FocusOut>", _show_search_placeholder)
        # Initial placeholder
        _show_search_placeholder()

        # 4. HEADER BIBLIOTHEQUE
        self.lbl_header_lib = tk.Label(
            parent, 
            text="BIBLIOTHÈQUE", 
            font=("Segoe UI", 11, "bold"),
            bg=c["sidebar"], 
            fg=c["text_barre"]
        )
        self.lbl_header_lib.grid(row=3, column=0, sticky="w", pady=(5, 5))

        # 5. BOUTONS
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

        # 6. HEADER PISTES
        self.lbl_header_tracks = tk.Label(
            parent, 
            text="PISTES", 
            font=("Segoe UI", 11, "bold"),
            bg=c["sidebar"], 
            fg=c["text_barre"]
        )
        self.lbl_header_tracks.grid(row=5, column=0, sticky="w", pady=(15, 5))

        # 7. TREEVIEW (LISTE) - C'est ici qu'il y avait l'erreur de duplication
        list_container = ttk.Frame(parent)
        list_container.grid(row=6, column=0, sticky="nsew")
        
        # Définition des colonnes
        columns = ("titre", "artiste", "duree")
        self.tree = ttk.Treeview(
            list_container, 
            columns=columns, 
            show="headings", # Mettre "tree headings" si tu veux l'icône dans la colonne #0
            selectmode="browse"
        )

        # En-têtes cliquables pour le tri
        for col in columns:
            self.tree.heading(
                col, 
                text=col.capitalize(), 
                command=lambda c=col: self._sort_treeview(c, False)
            )

        # Configuration des largeurs
        self.tree.column("titre", width=150, minwidth=100)
        self.tree.column("artiste", width=100, minwidth=80)
        self.tree.column("duree", width=50, minwidth=40, anchor="e")

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Création d'un overlay hint dans la zone blanche des pistes (sera affiché si la liste est vide)
        try:
            self.lbl_tracks_overlay = tk.Label(
                list_container,
                text="Ouvrez un dossier ou glissez-déposez un audio sur la piste",
                font=("Segoe UI", 10),
                bg=c["list_bg"], fg=c["text_dim"],
                bd=0, justify=tk.LEFT, wraplength=300
            )
            # Position relative pour rester à l'intérieur de la zone blanche
            # Lower a bit more so it doesn't overlap the Treeview headers
            self.lbl_tracks_overlay.place(relx=0.03, rely=0.20, anchor="nw")
        except Exception:
            self.lbl_tracks_overlay = None

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_selection_change)
        
        self.listbox = None

    # ---------- Contenu principal ----------
    def _build_main_content(self, parent):
        """Construit la zone centrale (Grande pochette, Titres, Paroles, Boutons d'édition)."""
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
            fg=c["text"],
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
        """Construit la barre de lecture en bas (Contrôles, Barre de progression, Volume)."""
        c = self.colors
        
        # On configure 3 colonnes : Gauche (Info), Centre (Player), Droite (Volume/Outils)
        parent.columnconfigure(0, weight=1) # Gauche
        parent.columnconfigure(1, weight=2) # Centre (plus large)
        parent.columnconfigure(2, weight=1) # Droite
        parent.rowconfigure(0, weight=1)

        # --- ZONE 1 : GAUCHE (Mini Cover + Titre) ---
        self.left_frame = tk.Frame(parent, bg=c["player"])
        self.left_frame.grid(row=0, column=0, sticky="w", padx=10)

        # La petite image cd cover (60x60)
        cover_frame = tk.Frame(self.left_frame, bg=c["player"], width=60, height=60)
        cover_frame.pack_propagate(False) # Empêche la frame de rétrécir si le label est vide
        cover_frame.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_mini_cover = tk.Label(cover_frame, bg=c["player"])
        self.lbl_mini_cover.pack(fill=tk.BOTH, expand=True)
        
        # Un petit rappel du titre (optionnel mais classe)
        info_frame = tk.Frame(self.left_frame, bg=c["player"])
        info_frame.pack(side=tk.LEFT)
        
        self.lbl_mini_title = tk.Label(
            info_frame, 
            textvariable=self.var_title, 
            font=("Segoe UI", 16, "bold"),
            bg=c["player"], fg="white", anchor="w"
        )
        self.lbl_mini_title.pack(anchor="w")
        
        self.lbl_mini_artist = tk.Label(
            info_frame, 
            textvariable=self.var_artist, 
            font=("Segoe UI", 12),
            bg=c["player"], fg="white", anchor="w"
        )
        self.lbl_mini_artist.pack(anchor="w")


        # --- ZONE 2 : CENTRE (Contrôles + Barre de progression) ---
        center_frame = tk.Frame(parent, bg=c["player"])
        center_frame.grid(row=0, column=1, sticky="ew")
        self.player_center_frame = center_frame

        controls = tk.Frame(center_frame, bg=c["player"])
        controls.pack(side=tk.TOP, pady=(5, 0))
        self.player_controls_frame = controls

        btn_sec_style = {
            "bg": c["player"],
            "fg": "white",
            "activebackground": c["player"],
            "activeforeground": c["accent"],
            "bd": 0,
            "font": ("Segoe UI Symbol", 12),
            "cursor": "hand2",
            "relief": "flat",
        }

        # Bouton shuffle (Aléatoire)
        self.btn_shuffle = tk.Button(
            controls, text="🔀", command=self.toggle_shuffle, **btn_sec_style
        )
        self.btn_shuffle.pack(side=tk.LEFT, padx=8)

        # Bouton précédent
        self.btn_prev = tk.Button(
            controls, text="⏮", command=self.play_prev, **btn_sec_style
        )
        self.btn_prev.pack(side=tk.LEFT, padx=8)

        # Bouton play (plus gros que les autres)
        btn_play_style = dict(btn_sec_style)
        btn_play_style.update({
            "font": ("Segoe UI Symbol", 16),
            "width": 5,
            "relief": "flat",
            "bd": 0,
        })

        self.btn_play = tk.Button(
            controls, text="▶", command=self.toggle_play_pause, **btn_play_style
        )
        self.btn_play.pack(side=tk.LEFT, padx=15)

        # Bouton suivant
        self.btn_next = tk.Button(
            controls, text="⏭", command=self.play_next, **btn_sec_style
        )
        self.btn_next.pack(side=tk.LEFT, padx=8)

        # Bouton répéter
        self.btn_repeat = tk.Button(
            controls, text="🔁", command=self.toggle_repeat, **btn_sec_style
        )
        self.btn_repeat.pack(side=tk.LEFT, padx=8)

        # Barre de progression
        progress_frame = tk.Frame(center_frame, bg=c["accent"])
        progress_frame.pack(side=tk.TOP, fill=tk.X, pady=(2, 5), padx=20)
        self.player_progress_frame = progress_frame

        self.lbl_current_time = tk.Label(
            progress_frame, text="0:00", bg=c["player"], fg=c["text_dim"], font=("Segoe UI", 8)
        )
        self.lbl_current_time.pack(side=tk.LEFT)

        self.progress_var = tk.DoubleVar()
        self.progress_scale = ttk.Scale(
            progress_frame, variable=self.progress_var, from_=0, to=100, style="Player.Horizontal.TScale"
        )
        self.progress_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        # Bindings pour cliquer sur la barre
        self.progress_scale.bind("<Button-1>", self._on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self._on_progress_release)

        self.lbl_total_time = tk.Label(
            progress_frame, text="0:00", bg=c["player"], fg=c["text_dim"], font=("Segoe UI", 8)
        )
        self.lbl_total_time.pack(side=tk.RIGHT)


        # --- ZONE 3 : DROITE (Volume + Theme) ---
        right_frame = tk.Frame(parent, bg=c["player"])
        right_frame.grid(row=0, column=2, sticky="e", padx=10)

        self.btn_vol = tk.Button(
            right_frame, text="🔊", command=self.toggle_mute, **btn_sec_style
        )
        self.btn_vol.pack(side=tk.LEFT, padx=5)

        self.theme_toggle_btn = tk.Button(
            right_frame,
            text="🌙",
            bg=c["player"], fg=c["text"], bd=0,
            command=self._toggle_theme, cursor="hand2"
        )
        self.theme_toggle_btn.pack(side=tk.LEFT, padx=5)
    def _on_player_btn_enter(self, event):
        """Change la couleur de fond au survol des boutons du lecteur."""
        c = self.colors
        event.widget.config(bg=c["accent_dark"])

    def _on_player_btn_leave(self, event):
        """Rétablit la couleur de fond quand la souris quitte un bouton."""
        c = self.colors
        event.widget.config(bg=c["player"])

    def _build_menu(self):
        """Crée la barre de menu supérieure (Fichier, Affichage)."""
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
        """
        Applique un thème complet (couleurs de fond, de texte, des boutons).
        Met à jour manuellement les widgets standards (tk) qui ne supportent pas les styles TTK.
        
        Args:
            theme_name (str): 'light' ou 'dark'.
        """
        if theme_name not in self.themes:
            return

        self.current_theme = theme_name
        self.colors = self.themes[theme_name]
        c = self.colors
        
        # Application du fond général
        self.configure(bg=c["bg"])

        # Mise à jour des styles TTK
        self._setup_styles()

        # --- 1. Sidebar ---
        if hasattr(self, 'lbl_header_logo'):
            self.lbl_header_logo.config(bg=c["sidebar"], fg=c["accent"])
            
        labels_sidebar = [
            getattr(self, 'lbl_header_search', None),
            getattr(self, 'lbl_header_lib', None),
            getattr(self, 'lbl_header_tracks', None)
        ]
        for lbl in labels_sidebar:
            if lbl: lbl.config(bg=c["sidebar"], fg=c["text_barre"])

        if self.sidebar_button_frame is not None:
            self.sidebar_button_frame.config(bg=c["sidebar"])
            for child in self.sidebar_button_frame.winfo_children():
                if isinstance(child, tk.Button):
                    child.config(
                        bg=c["sidebar"],
                        fg=c["text"],
                        activebackground=c["input_bg"],
                        activeforeground=c["accent"],
                    )

        # Update search entry colors and placeholder state
        if hasattr(self, 'search_entry'):
            try:
                # If placeholder active, keep dim color
                if getattr(self, '_search_placeholder', None) and self.var_search.get() == self._search_placeholder:
                    try:
                        self.search_entry.config(foreground=c['text_dim'])
                    except Exception:
                        pass
                else:
                    try:
                        self.search_entry.config(foreground=c['input_fg'])
                    except Exception:
                        pass
                try:
                    self.search_entry.config(background=c['input_bg'])
                except Exception:
                    pass
            except Exception:
                pass

        # --- 2. Main Content ---
        if hasattr(self, "cover_label"):
            self.cover_label.config(bg=c["bg"])
            
        if hasattr(self, "lyrics_text"):
            self.lyrics_text.config(bg=c["bg"], fg=c["text"])

        # Labels de la zone principale
        main_labels = [
            self.lbl_title, self.lbl_artist, self.lbl_details, 
            getattr(self, 'lbl_header_lecture', None),
            getattr(self, 'lbl_header_paroles', None)
        ]
        for lbl in main_labels:
            if lbl:
                if lbl == self.lbl_title: # Le titre reste en couleur texte principale
                    lbl.config(bg=c["bg"], fg=c["text"])
                elif lbl == self.lbl_artist:
                     lbl.config(bg=c["bg"], fg=c["accent"]) # Artiste en accent c'est joli
                else:
                    lbl.config(bg=c["bg"], fg=c["text_dim"])

        # --- 3. Player Bar ---
        # Détermine la couleur des icônes du lecteur
        # Si le fond du lecteur est sombre (theme dark), icones blanches
        # Si le fond du lecteur est blanc (theme light), icones gris foncé ou noires
        player_icon_fg = "#FFFFFF" if self.current_theme == "dark" else "#424242"
        player_icon_active = c["accent"]

        # Frames du lecteur
        player_frames = [
            self.left_frame,
            self.player_center_frame,
            self.player_controls_frame,
            self.player_status_bar if hasattr(self, 'player_status_bar') else None
        ]
        # Ajout du parent des boutons de droite
        if hasattr(self, 'btn_vol'):
            player_frames.append(self.btn_vol.master)

        for frame in player_frames:
            if frame: frame.config(bg=c["player"])

        # Forcer le background des widgets enfants dans la zone du player
        # Certains widgets tk peuvent garder un fond blanc par défaut; on les harmonise ici.
        try:
            for parent in [self.left_frame, self.player_center_frame, self.player_controls_frame]:
                if not parent:
                    continue
                for child in parent.winfo_children():
                    try:
                        child.config(bg=c["player"])
                    except Exception:
                        pass
                    # Et pour leurs enfants (labels/images à l'intérieur)
                    try:
                        for sub in child.winfo_children():
                            try:
                                sub.config(bg=c["player"])
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

        # Mini Cover & Info
        if hasattr(self, 'lbl_mini_title'):
            self.lbl_mini_title.config(bg=c["player"], fg=c["text"])
        if hasattr(self, 'lbl_mini_artist'):
            self.lbl_mini_artist.config(bg=c["player"], fg=c["text_dim"])
        if hasattr(self, 'lbl_mini_cover'):
            # Le parent du mini cover
            self.lbl_mini_cover.master.config(bg=c["player"])

        # Timers
        if hasattr(self, "lbl_current_time"):
            self.lbl_current_time.config(bg=c["player"], fg=c["text_dim"])
        if hasattr(self, "lbl_total_time"):
            self.lbl_total_time.config(bg=c["player"], fg=c["text_dim"])

        # Hint overlay inside the tracks area
        if hasattr(self, 'lbl_tracks_overlay') and self.lbl_tracks_overlay is not None:
            try:
                self.lbl_tracks_overlay.config(bg=c["list_bg"], fg=c["text_dim"], wraplength=300)
            except Exception:
                pass

        # Boutons Player (tk.Button)
        player_buttons = [self.btn_repeat, self.btn_prev, self.btn_play, self.btn_next, self.btn_vol, self.btn_shuffle, self.theme_toggle_btn]
        for b in player_buttons:
            if b is not None:
                b.config(
                    bg=c["player"],
                    fg=player_icon_fg,
                    activebackground=c["player"],
                    activeforeground=player_icon_active
                )
        
        # Cas spécial pour le Shuffle s'il est actif
        if self.shuffle_mode and hasattr(self, 'btn_shuffle'):
            self.btn_shuffle.config(fg=c["accent"])

        # Bouton Play (ttk)
        # Il est géré par le style "TButton", pas besoin de modif manuelle ici sauf si style custom appliqué

        # --- 4. Mise à jour de l'image Placeholder ---
        if HAS_PIL:
            self.placeholder_image = self._create_placeholder_cover(size=320)
            if self.cover_image_ref is None:
                self._clear_cover()
    def _toggle_theme(self):
        """Bascule entre le mode clair et le mode sombre."""
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._apply_theme(new_theme)

    # ============ LOGIC ==============
    def open_directory(self):
        """Ouvre une boîte de dialogue pour choisir un dossier et charge les fichiers audio."""
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
        """
        Filtre la liste des fichiers affichés en temps réel selon le texte saisi.
        Recherche dans le titre, l'artiste et le nom de fichier.
        """
        if not hasattr(self, 'tree') or self.tree is None:
            return

        raw = self.var_search.get()
        # Ignore le placeholder et prends en compte que un vrai input
        if getattr(self, '_search_placeholder', None) and raw == self._search_placeholder:
            query = ""
        else:
            query = raw.lower().strip()

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
        """
        Vide et remplit le Treeview (liste des pistes) avec les fichiers de `displayed_files`.
        Met à jour le mappage index -> fichier audio.
        """
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.index_to_audio.clear()

        # Si aucune piste affichée, montrer l'overlay d'instruction
        if not self.displayed_files:
            if hasattr(self, 'lbl_tracks_overlay') and self.lbl_tracks_overlay is not None:
                try:
                    self.lbl_tracks_overlay.lift()
                    # positionnement
                    self.lbl_tracks_overlay.place(relx=0.03, rely=0.20, anchor="nw")
                except Exception:
                    pass
            return
        else:
            # Masquer l'overlay s'il existe
            if hasattr(self, 'lbl_tracks_overlay') and self.lbl_tracks_overlay is not None:
                try:
                    self.lbl_tracks_overlay.place_forget()
                except Exception:
                    pass

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
        """Gère le clic sur une ligne du tableau pour lancer la lecture."""
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

    def play_from_index(self, idx: int, start_play: bool = True):
        """
        Docstring for play_from_index
        Prépare et lance la lecture d'une piste basée sur son index dans la liste.

        Met à jour l'interface (titre, artiste, cover), charge les paroles 
        en arrière-plan et lance le moteur audio pygame.
        
        Args:
            idx (int): L'index de la piste dans `self.displayed_files` (et non `self.audio_files`).
            start_play (bool, optional): Si True, la lecture commence immédiatement. 
                                         Si False, la piste est chargée mais mise en pause. 
                                         Défaut à True.
        """
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
                # Si on doit démarrer la lecture immédiatement
                if start_play:
                    pygame.mixer.music.play()
                    self.is_playing = True
                    self.is_paused = False
                    self.btn_play.config(text="⏸")
                    self._update_play_button_color()
                    self.var_status.set(f"Lecture : {title}")
                else:
                    # Si l'utilisateur est en pause, on charge et on met en pause
                    # pour que le comportement du bouton Play/Pause reste cohérent
                    if self.is_paused:
                        try:
                            pygame.mixer.music.play()
                            pygame.mixer.music.pause()
                        except Exception:
                            pass
                        self.is_playing = False
                        # is_paused reste True pour indiquer l'état visuel
                        self.btn_play.config(text="▶")
                        self._update_play_button_color()
                        self.var_status.set(f"En pause : {title}")
                    else:
                        # On charge sans démarrer
                        self.is_playing = False
                        self.is_paused = False
                        self.btn_play.config(text="▶")
                        self._update_play_button_color()
                        self.var_status.set(f"Prêt : {title}")
            except Exception as e:
                print("Erreur audio:", e)
                self.var_status.set("Erreur lecture audio.")

        def _bg_lyrics(aud, i):
            """
            Component lyrics
            """
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
        """
        Boucle récursive (exécutée toutes les 500ms) pour mettre à jour
        la barre de progression et passer à la piste suivante à la fin du morceau.
        """
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
        """
        Convertit une durée en secondes vers un format lisible MM:SS.

        Args:
            s (float): La durée en secondes (ex: 73.5).

        Returns:
            str: La chaîne formatée (ex: "01:02").
        """
        return f"{int(s//60)}:{int(s%60):02d}"

    def _update_play_button_color(self):
        """Met à jour la couleur du bouton Play pour rester lisible et indiquer l'état.
        Utilise `accent` quand on joue, sinon la couleur par défaut des icônes.
        """
        try:
            player_icon_fg = "#FFFFFF" if self.current_theme == "dark" else "#424242"
            accent = self.colors.get("accent", "#2962FF")
            if self.is_playing and not self.is_paused:
                fg = accent
            else:
                fg = player_icon_fg
            if self.btn_play is not None:
                self.btn_play.config(fg=fg)
        except Exception:
            pass

    def toggle_play_pause(self):
        """Bascule entre Lecture et Pause, ou lance la lecture si rien n'est joué."""
        if not self.audio_player_enabled:
            return
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self.btn_play.config(text="⏸")
            self._update_play_button_color()
        elif self.is_playing:
            pygame.mixer.music.pause()
            self.is_paused = True
            self.btn_play.config(text="▶")
            self._update_play_button_color()
        else:
            if self.current_index is not None:
                self.play_from_index(self.current_index)

    def _on_space_pressed(self, event):
        """Gère l'appui sur la barre espace (Pause/Play) sauf si on écrit du texte."""
        # On vérifie quel widget a le focus
        widget = event.widget
        
        # Si on est dans une zone de texte (Recherche, Édition tags, Paroles...), on laisse l'espace s'écrire
        if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            return
            
        # Sinon, on lance la commande Play/Pause
        self.toggle_play_pause()
        
        # (Optionnel) Empêche l'événement de se propager (ex: scroller vers le bas)
        return "break"

    def toggle_shuffle(self):
        """
        Active ou désactive le mode aléatoire.
        
        Change l'état du booléen `shuffle_mode` et met à jour la couleur 
        du bouton pour refléter l'état (Accent si actif, Gris/Blanc sinon).
        """
        self.shuffle_mode = not self.shuffle_mode
        normal_fg = "#FFFFFF" if self.current_theme == "dark" else "#424242"
        color = self.colors["accent"] if self.shuffle_mode else normal_fg
        
        self.btn_shuffle.config(fg=color)
    
    def play_next(self):
        """Passe au morceau suivant (ou aléatoire si Shuffle activé)."""
        if self.current_index is not None and self.displayed_files:
            import random

            if self.shuffle_mode:
                # prendre un index au hasard
                new_idx = self.current_index
                if len(self.displayed_files) > 1:
                    while new_idx == self.current_index:
                        new_idx = random.randint(0, len(self.displayed_files) - 1)
                idx = new_idx
            else:
                idx = (self.current_index + 1) % len(self.displayed_files)
            
            
            # 2. Conversion en ID pour le Treeview (on a utilisé str(idx) comme identifiant)
            item_id = str(idx)
            
            # 3. Sélection visuelle dans le Treeview
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id) # Sélectionne la ligne
                self.tree.see(item_id)           # Scrolle pour la rendre visible
                self.tree.focus(item_id)         
            # Démarrer la lecture seulement si l'utilisateur n'est pas en pause
            self.play_from_index(idx, start_play=(not self.is_paused))

    def play_prev(self):
        """Passe au morceau précédent."""
        if self.current_index is not None and self.displayed_files:
            # 1. Calcul du nouvel index (avec modulo pour revenir à la fin si on est au début)
            idx = (self.current_index - 1) % len(self.displayed_files)            
            # 2. Sélection visuelle dans le Treeview
            item_id = str(idx)            
            if self.tree.exists(item_id):
                self.tree.selection_set(item_id)
                self.tree.see(item_id)
                self.tree.focus(item_id)

            # Respecter l'état de pause lors du changement de piste
            self.play_from_index(idx, start_play=(not self.is_paused))

    def toggle_repeat(self):
        """Active/Désactive la répétition de la piste en cours."""
        self.repeat = not self.repeat
        normal_fg = "#FFFFFF" if self.current_theme == "dark" else "#424242"
        self.btn_repeat.config(fg=self.colors["accent"] if self.repeat else normal_fg)

    def toggle_mute(self):
        """Coupe ou rétablit le son (Mute)."""
        if not self.audio_player_enabled:
            return
        self.muted = not self.muted
        pygame.mixer.music.set_volume(0.0 if self.muted else self.volume)
        self.btn_vol.config(text="🔈" if self.muted else "🔊")

    def _update_audio_controls_state(self):
        """Active ou désactive les contrôles audio selon `self.audio_player_enabled`.
        Permet d'éviter des interactions silencieuses quand pygame manque.
        """
        enabled = self.audio_player_enabled
        state = tk.NORMAL if enabled else tk.DISABLED

        # Boutons principaux
        try:
            if self.btn_play is not None:
                self.btn_play.config(state=state)
            if self.btn_next is not None:
                self.btn_next.config(state=state)
            if self.btn_prev is not None:
                self.btn_prev.config(state=state)
            if self.btn_vol is not None:
                self.btn_vol.config(state=state)
            if getattr(self, 'progress_scale', None) is not None:
                self.progress_scale.config(state=state)
            if getattr(self, 'btn_shuffle', None) is not None:
                self.btn_shuffle.config(state=state)
            if getattr(self, 'btn_repeat', None) is not None:
                self.btn_repeat.config(state=state)
        except Exception:
            pass

        if not enabled:
            self.var_status.set("Audio désactivé : installez 'pygame' ou vérifiez la sortie audio.")

    def _on_progress_press(self, event):
        """Arrête la mise à jour automatique de la barre quand l'utilisateur clique dessus."""
        self.user_dragging_progress = True

    def _on_progress_release(self, event):
        """Reprend la lecture à la nouvelle position quand l'utilisateur relâche la barre."""
        self.user_dragging_progress = False
        self._seek_absolute(self.progress_scale.get())

    def _seek_absolute(self, pct: float):
        """Déplace la tête de lecture à un pourcentage donné (0-100)."""
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
        self._update_play_button_color()

  # --------- API & METADATA ----------
    def fetch_api_current(self):
        """
        Récupère les métadonnées depuis l'API Spotify via MetadataFetcher.

        Workflow :
        1. Utilise les champs texte de l'interface (Titre/Artiste) comme requête prioritaire.
        2. Sauvegarde temporairement ces infos dans le fichier.
        3. Interroge l'API.
        4. Met à jour l'interface et recharge la cover si un résultat est trouvé.

        Raises:
            Exception: Affiche une popup d'erreur si la connexion échoue ou si l'écriture fichier est bloquée.
        """
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
            # AJOUT : Reload force pour éviter le cache mutagen
            if hasattr(audio, 'reload'):
                audio.reload()
                time.sleep(0.3)
            
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
            # On reload avant d'extraire pour avoir les dernières données écrites
            if hasattr(audio, 'reload'):
                audio.reload()
                time.sleep(0.3)
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
                    if was_paused:
                        pygame.mixer.music.pause()
                    self.btn_play.config(text="⏸" if not was_paused else "▶")
                    self._update_play_button_color()
                except Exception:
                    pass
            
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
                    self.btn_play.config(text="⏸")
                    self._update_play_button_color()
                except:
                    pass
            print(f"Erreur critique: {e}")
            messagebox.showerror("Erreur", str(e))

            
            
    
    def save_metadata_current(self):
        """
        Sauvegarde les informations affichées (Titre, Artiste, Album, Année) 
        directement dans les tags ID3/FLAC du fichier.
        """
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
            
            # Étape 2 : Sauvegarder sur le disque
            audio.save_metadata()
            time.sleep(0.3)
            
            # On recharge l'objet audio pour vidanger le cache mutagen
            # Cela force une relecture RÉELLE depuis le fichier disque
            if hasattr(audio, 'reload'):
                audio.reload()
                time.sleep(0.3)
            
            # Étape 3 : Relire les tags APRÈS le reload
            updated_tags = audio.extract_metadata()
            if updated_tags:
                audio.metadata = updated_tags
                # On met à jour les variables UI pour prouver que la sauvegarde a marché
                self.var_title.set(updated_tags.get("title", ""))
                self.var_artist.set(updated_tags.get("artist", ""))
                self.var_album_internal = updated_tags.get("album", "")
                self.var_year_internal = str(updated_tags.get("year", ""))
                
                details = []
                if self.var_album_internal:
                    details.append(self.var_album_internal)
                if self.var_year_internal:
                    details.append(self.var_year_internal)
                self.var_details.set(" • ".join(details) if details else "")
            # ============================================

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
                    self._update_play_button_color()
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
            """ Fenetre de sauvegarde de metadonnées"""
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
        """Lit un fichier .xspf, extrait les chemins et charge les fichiers correspondants."""
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
        """
        Génère un fichier playlist .xspf contenant soit les fichiers sélectionnés,
        soit tous les fichiers affichés actuellement.
        """
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
        """Génère une image par défaut (Note de musique ♪) si aucune pochette n'existe."""
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
        """Réinitialise l'affichage de la pochette avec le placeholder."""
        if self.placeholder_image:
            self.cover_label.config(image=self.placeholder_image)
            self.cover_image_ref = self.placeholder_image

        if hasattr(self, 'lbl_mini_cover'):
            self.lbl_mini_cover.config(image="", width=0, bg=self.colors["player"])

    def _update_cover(self, audio: AudioFile, force_validation: bool = False):
            """
            Affiche la pochette de l'album.
            
            Stratégie :
            1. Cherche une image locale téléchargée par l'API.
            2. (Optionnel) Demande validation à l'utilisateur.
            3. Sinon, extrait l'image intégrée dans les tags du fichier.
            4. Sinon, affiche le placeholder.
            """
            if not HAS_PIL:
                return

            final_image = None
            source_is_file = False
            cover_path = None

            # --- ÉTAPE 1 : TENTATIVE CHARGEMENT DISQUE ---
            try:
                if hasattr(self.metadata_fetcher, "ensure_cover_image"):
                    cover_path = self.metadata_fetcher.ensure_cover_image(audio)
                    if cover_path and cover_path.exists():
                        # On charge en mémoire et on ferme immédiatement le fichier
                        try:
                            with Image.open(cover_path) as opened_img:
                                opened_img.load() 
                                # On stocke une copie pour l'interface
                                disk_image = opened_img.copy()
                            source_is_file = True
                        except Exception as e:
                            print(f"Erreur lecture image disque: {e}")
                            disk_image = None
                    else:
                        disk_image = None
            except Exception as e:
                print(f"Erreur cover disque: {e}")
                disk_image = None

            # --- ÉTAPE 2 : VALIDATION (Si nécessaire) ---
            # Si on a trouvé une image disque ET qu'on est en mode validation (API)
            if source_is_file and force_validation and disk_image:
                
                # Fenêtre de prévisualisation
                preview_window = tk.Toplevel(self)
                preview_window.title("Validation")
                preview_window.geometry("400x480")
                preview_window.transient(self)
                preview_window.grab_set()
                
                c = self.colors
                preview_window.config(bg=c["bg"])

                tk.Label(preview_window, text="Nouvelle pochette trouvée :", bg=c["bg"], fg=c["text"], font=("Segoe UI", 11, "bold")).pack(pady=15)

                # Image Preview
                preview_img = disk_image.copy()
                preview_img.thumbnail((300, 300))
                photo_preview = ImageTk.PhotoImage(preview_img)
                
                lbl_preview = tk.Label(preview_window, image=photo_preview, bg=c["bg"])
                lbl_preview.pack(pady=5)
                # On garde une ref locale pour que l'image s'affiche
                lbl_preview.image = photo_preview 

                tk.Label(preview_window, text="Voulez-vous l'utiliser ?", bg=c["bg"], fg=c["text"]).pack(pady=10)

                user_response = tk.BooleanVar(value=False)

                def on_yes():
                    user_response.set(True)
                    preview_window.destroy()

                def on_no():
                    user_response.set(False)
                    preview_window.destroy()

                btn_frame = tk.Frame(preview_window, bg=c["bg"])
                btn_frame.pack(pady=10)

                tk.Button(btn_frame, text="Non, supprimer", command=on_no, width=15).pack(side=tk.LEFT, padx=10)
                tk.Button(btn_frame, text="Oui, garder", command=on_yes, width=15, bg=c["accent"], fg="white").pack(side=tk.LEFT, padx=10)

                self.wait_window(preview_window)

                # --- LOGIQUE DE DÉCISION ---
                if user_response.get():
                    # L'utilisateur a dit OUI : on garde l'image du disque
                    final_image = disk_image
                else:
                    # L'utilisateur a dit NON : 
                    print("Cover rejetée. Tentative de suppression...")
                    
                    # 1. On oublie l'image disque dans nos variables
                    final_image = None
                    disk_image = None
                    
                    # 2. On nettoie les objets graphiques pour libérer le verrou
                    del photo_preview
                    del preview_img
                    
                    # 3. Petit délai pour laisser Windows respirer (nécessaire parfois)
                    self.update_idletasks()
                    time.sleep(0.1)

                    # 4. Suppression du fichier
                    try:
                        if cover_path and cover_path.exists():
                            os.remove(cover_path)
                            print("Fichier supprimé avec succès.")
                    except Exception as e:
                        # Si ça échoue, on prévient l'utilisateur mais on continue sans planter
                        print(f"Échec suppression fichier : {e}")
                        messagebox.showwarning("Info", f"L'image n'a pas pu être supprimée du disque (verrouillée).\nMais elle ne sera pas utilisée pour l'instant.")

            else:
                # Pas de validation demandée : on prend l'image disque si elle existe
                final_image = disk_image

            # --- ÉTAPE 3 : FALLBACK (Tags Internes) ---
            # Si après tout ça, on n'a pas d'image (soit pas trouvée, soit rejetée par l'utilisateur)
            # On va chercher dans les tags internes du fichier audio (MP3/FLAC)
            if final_image is None:
                data = audio.get_cover_art()
                if data:
                    try:
                        final_image = Image.open(BytesIO(data))
                    except Exception as e:
                        print(f"Erreur cover interne: {e}")

            # --- ÉTAPE 4 : AFFICHAGE ---
            if final_image:
                try:
                    # Grande Cover
                    img_big = final_image.copy()
                    img_big.thumbnail((320, 320))
                    photo_big = ImageTk.PhotoImage(img_big)
                    
                    self.cover_label.config(image=photo_big)
                    self.cover_image_ref = photo_big

                    # Mini Cover
                    if hasattr(self, 'lbl_mini_cover'):
                        img_mini = final_image.copy()
                        img_mini.thumbnail((60, 60))
                        photo_mini = ImageTk.PhotoImage(img_mini)
                        self.lbl_mini_cover.config(image=photo_mini, width=60, height=60)
                        self.mini_cover_ref = photo_mini
                    
                    self.cover_label.update_idletasks()
                except Exception as e:
                    print(f"Erreur affichage: {e}")
            else:
                self._clear_cover()

    def _set_lyrics_text(self, text: str):
        """Affiche les paroles dans la zone de texte (déverrouille, écrit, verrouille)."""
        self.lyrics_text.config(state=tk.NORMAL)
        self.lyrics_text.delete("1.0", tk.END)
        self.lyrics_text.insert(tk.END, text if text else "Paroles non disponibles.")
        self.lyrics_text.config(state=tk.DISABLED)


    def on_drop_files(self, event):
        """
        Gère le glisser-déposer de fichiers depuis l'explorateur Windows.
        Parse les chemins (parfois complexes avec accolades) et ajoute les fichiers valides.
        """
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