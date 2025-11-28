#!/usr/bin/env python3
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any
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
    print(" pygame non installé. Le lecteur audio sera désactivé.")

# Thème Sun Valley (sv_ttk) si dispo
try:
    import sv_ttk

    HAS_SV_TTK = True
except ImportError:
    HAS_SV_TTK = False

# Accès à src/
BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
sys.path.append(str(SRC_DIR))

from library.models.music_library import MusicLibrary
from library.models.audio_file import AudioFile
from library.core.playlist_generator import PlaylistGenerator
from library.core.metadatafetcher import MetadataFetcher


class MusicLibraryGUI(tk.Tk):
    """
    Interface graphique PyMetaPlay – GUI moderne + lecteur audio.
    """

    def __init__(self):
        super().__init__()
        self.title("PyMetaPlay – GUI")
        self.geometry("1200x700")

        self.configure(bg="#1f1f1f")

        if HAS_SV_TTK:
            sv_ttk.use_dark_theme()

        self.library = MusicLibrary()
        self.audio_files: List[AudioFile] = []
        self.index_to_audio: Dict[int, AudioFile] = {}

        self.metadata_fetcher = MetadataFetcher()

        # Stats "écouté récemment" / "plus écoutés"
        self.recent_history: List[str] = []
        self.play_count: Dict[str, int] = {}

        # Lecteur audio
        self.audio_player_enabled = False
        self.current_index: Optional[int] = None
        self.is_playing: bool = False
        self.is_paused: bool = False
        self.repeat: bool = False
        self.volume: float = 0.8
        self.muted: bool = False
        self._stored_volume: float = self.volume
        self.current_offset: float = 0.0  # position actuelle (sec)

        # Drag sur la barre de progression
        self.user_dragging_progress: bool = False

        if HAS_PYGAME:
            try:
                pygame.mixer.init()
                pygame.mixer.music.set_volume(self.volume)
                self.audio_player_enabled = True
            except Exception as e:
                print("Impossible d'initialiser le lecteur audio :", e)
        else:
            print(" Installe pygame pour activer le lecteur audio.")

        # Covers
        self.cover_image_ref = None
        self.placeholder_image = None
        self.card_placeholder_image = None
        self.highlight_covers: List[Any] = []

        if HAS_PIL:
            # Grande cover pour le lecteur principal
            self.placeholder_image = self._create_placeholder_cover(size=200)
            # Petite cover pour les cartes "Sélection"
            self.card_placeholder_image = self._create_placeholder_cover(size=120)

        self._setup_styles()
        self._build_menu()
        self._build_widgets()

        # boucle d'update de la barre de progression
        self.after(500, self._progress_loop)

    # ------------- Styles -------------

    def _setup_styles(self):
        style = ttk.Style(self)
        if not HAS_SV_TTK:
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass

            style.configure("Main.TFrame", background="#1f1f1f")
            style.configure("Card.TFrame", background="#2b2f33")
            style.configure(
                "Header.TLabel",
                background="#1f1f1f",
                foreground="#f5f5f5",
                font=("Segoe UI", 14, "bold"),
            )
            style.configure(
                "SubHeader.TLabel",
                background="#2b2f33",
                foreground="#f5f5f5",
                font=("Segoe UI", 11, "bold"),
            )
            style.configure(
                "Normal.TLabel",
                background="#2b2f33",
                foreground="#e0e0e0",
                font=("Segoe UI", 10),
            )
        else:
            style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
            style.configure("SubHeader.TLabel", font=("Segoe UI", 11, "bold"))
            style.configure("Normal.TLabel", font=("Segoe UI", 10))

        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Chip.TButton", font=("Segoe UI", 9))

    # ------------- Menu -------------

    def _build_menu(self):
        menubar = tk.Menu(self)

        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Ouvrir dossier…", command=self.open_directory)
        menu_file.add_command(label="Ouvrir playlist XSPF…", command=self.open_playlist)
        menu_file.add_separator()
        menu_file.add_command(label="Quitter", command=self.quit)
        menubar.add_cascade(label="Fichier", menu=menu_file)

        menu_playlist = tk.Menu(menubar, tearoff=0)
        menu_playlist.add_command(
            label="Générer playlist (tous les fichiers)",
            command=self.generate_playlist_all,
        )
        menu_playlist.add_command(
            label="Générer playlist (sélection)",
            command=self.generate_playlist_selection,
        )
        menubar.add_cascade(label="Playlist", menu=menu_playlist)

        self.config(menu=menubar)

    # ------------- Layout principal -------------

    def _build_widgets(self):
        container = ttk.Frame(self, style="Main.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # ---------- HEADER ----------
        header = ttk.Frame(container, style="Main.TFrame")
        header.pack(fill=tk.X, pady=(0, 15))

        logo_label = ttk.Label(header, text="PyMetaPlay", style="Header.TLabel")
        logo_label.grid(row=0, column=0, padx=(0, 10))

        self.var_search = tk.StringVar()
        search_entry = ttk.Entry(header, textvariable=self.var_search)
        search_entry.grid(row=0, column=1, sticky="ew")

        # Bouton Search JAUNE
        search_button = tk.Button(
            header,
            text="Search",
            command=self.do_search,
            bg="#ffc107",
            fg="black",
            activebackground="#ffcf40",
            activeforeground="black",
            relief="flat",
            padx=12,
            pady=4,
            font=("Segoe UI", 10, "bold"),
        )
        search_button.grid(row=0, column=2, padx=(10, 5))

        chips_frame = ttk.Frame(header, style="Main.TFrame")
        chips_frame.grid(row=0, column=3, padx=(10, 0))
        for label in ("Song", "Artiste", "Album", "Playlist"):
            ttk.Button(chips_frame, text=label, style="Chip.TButton").pack(
                side=tk.LEFT, padx=3
            )

        header.columnconfigure(1, weight=1)

        # ---------- ZONE PRINCIPALE ----------
        main = ttk.Frame(container, style="Main.TFrame")
        main.pack(fill=tk.BOTH, expand=True)

        main.rowconfigure(0, weight=2)
        main.rowconfigure(1, weight=3)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=2)
        main.columnconfigure(2, weight=1)

        # ---------- LIGNE HAUTE ----------

        # 1) Top-left : Sélection (4 cartes)
        discover_frame = ttk.Frame(main, style="Card.TFrame")
        discover_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

        ttk.Label(discover_frame, text="Sélection", style="SubHeader.TLabel").pack(
            anchor="w", padx=10, pady=5
        )

        self.highlights_frame = ttk.Frame(discover_frame, style="Card.TFrame")
        self.highlights_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # 2) Top-center : lecteur (cover + slider + boutons)
        nowplaying = ttk.Frame(main, style="Card.TFrame")
        nowplaying.grid(row=0, column=1, sticky="nsew", padx=10, pady=(0, 10))

        top_np = ttk.Frame(nowplaying, style="Card.TFrame")
        top_np.pack(fill=tk.X, padx=10, pady=10)

        # >>> cover principale : tk.Label avec fond sombre
        self.cover_label = tk.Label(
            top_np,
            text="[Cover]",
            bg="#202020",
            fg="white",
        )
        self.cover_label.pack(side=tk.LEFT, padx=(0, 10), pady=5)

        # Variables métadonnées
        self.var_title = tk.StringVar()
        self.var_artist = tk.StringVar()
        self.var_album = tk.StringVar()
        self.var_year = tk.StringVar()
        self.var_duration = tk.StringVar()
        self.var_format = tk.StringVar()
        self.var_path = tk.StringVar()

        text_np = ttk.Frame(top_np, style="Card.TFrame")
        text_np.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(text_np, textvariable=self.var_title, style="SubHeader.TLabel").pack(
            anchor="w"
        )
        ttk.Label(text_np, textvariable=self.var_artist, style="Normal.TLabel").pack(
            anchor="w"
        )
        ttk.Label(text_np, textvariable=self.var_album, style="Normal.TLabel").pack(
            anchor="w", pady=(5, 0)
        )

        bottom_np = ttk.Frame(nowplaying, style="Card.TFrame")
        bottom_np.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Slider de progression (0–100%)
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_scale = ttk.Scale(
            bottom_np, variable=self.progress_var, from_=0.0, to=100.0
        )
        self.progress_scale.pack(fill=tk.X, pady=(0, 5))
        self.progress_scale.bind("<Button-1>", self._on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self._on_progress_release)
    # Zone des boutons du lecteur
        controls_frame = tk.Frame(bottom_np, bg="#2b2f33")
        controls_frame.pack(pady=10)

        btn_style = {
            "bg": "#ffc107",
            "fg": "black",
            "activebackground": "#ffcf40",
            "activeforeground": "black",
            "relief": "flat",
            "bd": 0,
            "width": 4,
            "height": 1,
            "font": ("Segoe UI Symbol", 12),  # icônes lisibles sous Windows
        }

        # Boutons lecteur
        self.btn_prev = tk.Button(
            controls_frame, text="⏮", command=self.play_prev, **btn_style
        )
        self.btn_prev.pack(side=tk.LEFT, padx=6)

        self.btn_play = tk.Button(
            controls_frame, text="▶", command=self.toggle_play_pause, **btn_style
        )
        self.btn_play.pack(side=tk.LEFT, padx=6)

        self.btn_next = tk.Button(
            controls_frame, text="⏭", command=self.play_next, **btn_style
        )
        self.btn_next.pack(side=tk.LEFT, padx=6)

        self.btn_repeat = tk.Button(
            controls_frame, text="🔁", command=self.toggle_repeat, **btn_style
        )
        self.btn_repeat.pack(side=tk.LEFT, padx=6)

        self.btn_vol = tk.Button(
            controls_frame, text="🔊", command=self.toggle_mute, **btn_style
        )
        self.btn_vol.pack(side=tk.LEFT, padx=6)

        # 3) Top-right : "Écouté récemment"
        right_top = ttk.Frame(main, style="Card.TFrame")
        right_top.grid(row=0, column=2, sticky="nsew", padx=(10, 0), pady=(0, 10))

        ttk.Label(right_top, text="Écouté récemment", style="SubHeader.TLabel").pack(
            anchor="w", padx=10, pady=5
        )
        self.recent_box = tk.Listbox(
            right_top,
            height=10,
            bg="#2b2f33" if not HAS_SV_TTK else None,
            fg="white" if not HAS_SV_TTK else None,
            bd=0,
            highlightthickness=0,
            selectbackground="#ffc107",
        )
        self.recent_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # ---------- LIGNE BASSE ----------

        # 4) Bottom-left : "Ma playlist"
        bottom_left = ttk.Frame(main, style="Card.TFrame")
        bottom_left.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))

        top_bl = ttk.Frame(bottom_left, style="Card.TFrame")
        top_bl.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(top_bl, text="Ma playlist", style="SubHeader.TLabel").pack(
            side=tk.LEFT
        )

        # Bouton "Lire dossier" JAUNE
        tk.Button(
            top_bl,
            text="Lire dossier",
            command=self.open_directory,
            bg="#ffc107",
            fg="black",
            activebackground="#ffcf40",
            activeforeground="black",
            relief="flat",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.RIGHT)

        self.listbox = tk.Listbox(
            bottom_left,
            selectmode=tk.EXTENDED,
            exportselection=False,
            bg="#2b2f33" if not HAS_SV_TTK else None,
            fg="white" if not HAS_SV_TTK else None,
            bd=0,
            highlightthickness=0,
            selectbackground="#ffc107",
        )
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.listbox.bind("<<ListboxSelect>>", self.on_selection_change)

        # 5) Bottom-center : Paroles + boutons API
        bottom_center = ttk.Frame(main, style="Card.TFrame")
        bottom_center.grid(row=1, column=1, sticky="nsew", padx=10, pady=(10, 0))

        ttk.Label(bottom_center, text="Paroles", style="SubHeader.TLabel").pack(
            anchor="w", padx=10, pady=5
        )

        self.lyrics_text = tk.Text(
            bottom_center,
            height=8,  # un peu plus petit
            wrap=tk.WORD,
            bg="#2b2f33" if not HAS_SV_TTK else None,
            fg="white" if not HAS_SV_TTK else None,
            bd=0,
            highlightthickness=0,
            state=tk.DISABLED,
        )
        # on enlève expand=True pour éviter que ça pousse les boutons tout en bas
        self.lyrics_text.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))

        btn_frame = ttk.Frame(bottom_center, style="Card.TFrame")
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))  # petit espace au-dessus et en dessous


        # Boutons du bas JAUNES
        tk.Button(
            btn_frame,
            text="Sauvegarder métadonnées",
            command=self.save_metadata_current,
            bg="#ffc107",
            fg="black",
            activebackground="#ffcf40",
            activeforeground="black",
            relief="flat",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT)

        tk.Button(
            btn_frame,
            text="Rechercher via API (Spotify + paroles)",
            command=self.fetch_api_current,
            bg="#ffc107",
            fg="black",
            activebackground="#ffcf40",
            activeforeground="black",
            relief="flat",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side=tk.LEFT, padx=10)

        # 6) Bottom-right : "Que vous avez le plus écoutés"
        bottom_right = ttk.Frame(main, style="Card.TFrame")
        bottom_right.grid(row=1, column=2, sticky="nsew", padx=(10, 0), pady=(10, 0))

        ttk.Label(
            bottom_right,
            text="Que vous avez le plus écoutés",
            style="SubHeader.TLabel",
        ).pack(anchor="w", padx=10, pady=5)

        self.top_box = tk.Listbox(
            bottom_right,
            height=10,
            bg="#2b2f33" if not HAS_SV_TTK else None,
            fg="white" if not HAS_SV_TTK else None,
            bd=0,
            highlightthickness=0,
            selectbackground="#ffc107",
        )
        self.top_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self._clear_cover()

    # ------------- Cover par défaut -------------

    def _create_placeholder_cover(self, size=200):
        """Image par défaut avec une note de musique stylée."""
        try:
            img = Image.new("RGB", (size, size), "#202020")
            draw = ImageDraw.Draw(img)

            margin = size // 10
            # Cadre arrondi jaune
            try:
                draw.rounded_rectangle(
                    (margin, margin, size - margin, size - margin),
                    radius=int(size * 0.15),
                    outline="#ffc107",
                    width=max(2, size // 25),
                )
            except AttributeError:
                # Pour vieilles versions de Pillow
                draw.rectangle(
                    (margin, margin, size - margin, size - margin),
                    outline="#ffc107",
                    width=max(2, size // 25),
                )

            symbol = "♪"  # grosse note de musique

            # Police assez grosse
            try:
                font_size = int(size * 0.5)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except Exception:
                    font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

            # Centrage du texte
            try:
                bbox = draw.textbbox((0, 0), symbol, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = draw.textsize(symbol, font=font)

            x = (size - tw) // 2
            y = (size - th) // 2
            draw.text((x, y), symbol, fill="#ffc107", font=font)

            return ImageTk.PhotoImage(img)
        except Exception as e:
            print("Erreur création cover placeholder :", e)
            return None

    # ------------- Utilitaires lecteur -------------

    def _ensure_player(self) -> bool:
        if not self.audio_player_enabled:
            messagebox.showinfo(
                "Lecteur audio",
                "Le lecteur audio est désactivé (pygame non installé ou erreur d'initialisation).",
            )
            return False
        return True

    def _progress_loop(self):
        if self.audio_player_enabled and self.is_playing and not self.is_paused:
            try:
                pos_ms = pygame.mixer.music.get_pos()
                dur_str = self.var_duration.get()
                if pos_ms >= 0 and dur_str:
                    try:
                        dur = float(dur_str)
                        if dur > 0 and not self.user_dragging_progress:
                            total_pos_sec = self.current_offset + (pos_ms / 1000.0)
                            total_pos_sec = max(0.0, min(dur, total_pos_sec))
                            progress = (total_pos_sec / dur) * 100.0
                            progress = max(0.0, min(100.0, progress))
                            self.progress_var.set(progress)
                    except ValueError:
                        pass

                # fin de piste
                if (
                    self.is_playing
                    and not pygame.mixer.music.get_busy()
                    and not self.is_paused
                ):
                    self.is_playing = False
                    self.current_offset = 0.0
                    self.btn_play.config(text="▶")
                    self.progress_var.set(100.0)
                    if self.repeat:
                        self.current_offset = 0.0
                        self.play_current()
            except Exception:
                pass
        self.after(500, self._progress_loop)

    def play_current(self):
        if not self._ensure_player():
            return

        if self.current_index is None:
            if not self.index_to_audio:
                messagebox.showinfo("Info", "Aucun morceau sélectionné.")
                return
            self.current_index = 0
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
            self.listbox.see(0)
            self.listbox.event_generate("<<ListboxSelect>>")

        audio = self.index_to_audio.get(self.current_index)
        if not audio:
            return

        filepath = str(audio.filepath)
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
            # seek si on a un offset
            if self.current_offset > 0:
                try:
                    pygame.mixer.music.set_pos(self.current_offset)
                except Exception as e:
                    print("Erreur set_pos pour seek :", e)
            self.is_playing = True
            self.is_paused = False
            self.btn_play.config(text="⏸")
        except Exception as e:
            messagebox.showerror(
                "Erreur lecteur",
                f"Impossible de lire le fichier :\n{filepath}\n\n{e}",
            )

    def toggle_play_pause(self):
        if not self._ensure_player():
            return

        if not self.is_playing:
            self.current_offset = 0.0
            self.play_current()
            return

        try:
            if not self.is_paused:
                pygame.mixer.music.pause()
                self.is_paused = True
                self.btn_play.config(text="▶")
            else:
                pygame.mixer.music.unpause()
                self.is_paused = False
                self.btn_play.config(text="⏸")
        except Exception as e:
            print("Erreur toggle play/pause :", e)

    def play_next(self):
        if not self._ensure_player():
            return
        if not self.index_to_audio:
            return
        if self.current_index is None:
            self.current_index = 0
        else:
            self.current_index = (self.current_index + 1) % len(self.index_to_audio)

        self.current_offset = 0.0
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.current_index)
        self.listbox.see(self.current_index)
        self.listbox.event_generate("<<ListboxSelect>>")
        self.play_current()

    def play_prev(self):
        if not self._ensure_player():
            return
        if not self.index_to_audio:
            return
        if self.current_index is None:
            self.current_index = 0
        else:
            self.current_index = (self.current_index - 1) % len(self.index_to_audio)

        self.current_offset = 0.0
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.current_index)
        self.listbox.see(self.current_index)
        self.listbox.event_generate("<<ListboxSelect>>")
        self.play_current()

    def toggle_mute(self):
        if not self._ensure_player():
            return
        try:
            if not self.muted:
                self._stored_volume = self.volume
                self.volume = 0.0
                pygame.mixer.music.set_volume(0.0)
                self.muted = True
                self.btn_vol.config(text="🔈")
            else:
                self.volume = self._stored_volume or 0.8
                pygame.mixer.music.set_volume(self.volume)
                self.muted = False
                self.btn_vol.config(text="🔊")
        except Exception as e:
            print("Erreur mute :", e)

    def toggle_repeat(self):
        self.repeat = not self.repeat
        if self.repeat:
            self.btn_repeat.config(style="Accent.TButton")
        else:
            self.btn_repeat.config(style="TButton")

    # --------- Seek via Slider ---------

    def _on_progress_press(self, event):
        self.user_dragging_progress = True

    def _on_progress_release(self, event):
        if not self.user_dragging_progress:
            return
        self.user_dragging_progress = False
        self._seek_to(self.progress_var.get())

    def _seek_to(self, percent: float):
        if not self._ensure_player():
            return
        if self.current_index is None:
            return
        dur_str = self.var_duration.get()
        if not dur_str:
            return
        try:
            dur = float(dur_str)
        except ValueError:
            return
        percent = max(0.0, min(100.0, percent))
        new_pos = (percent / 100.0) * dur
        self.current_offset = new_pos
        self.play_current()
        self.progress_var.set(percent)

    # ------------- Recherche simple locale -------------

    def do_search(self):
        term = self.var_search.get().strip().lower()
        if not term:
            messagebox.showinfo("Recherche", "Entrez un terme de recherche.")
            return
        if not self.audio_files:
            messagebox.showinfo("Recherche", "Aucun fichier chargé.")
            return

        matches: List[AudioFile] = []
        for audio in self.audio_files:
            try:
                md = audio.extract_metadata()
            except Exception:
                md = {}
            haystack = " ".join(
                [
                    md.get("title", ""),
                    md.get("artist", ""),
                    md.get("album", ""),
                    audio.filepath.name,
                ]
            ).lower()
            if term in haystack:
                matches.append(audio)

        if not matches:
            messagebox.showinfo("Recherche", "Aucun morceau trouvé.")
            return

        self.listbox.delete(0, tk.END)
        self.index_to_audio.clear()
        for idx, audio in enumerate(matches):
            self.listbox.insert(tk.END, audio.filepath.name)
            self.index_to_audio[idx] = audio

        self.current_index = None
        self.current_offset = 0.0
        self._clear_details()

    # ------------- Actions haut niveau -------------

    def open_directory(self):
        directory = filedialog.askdirectory(title="Choisir un dossier de musique")
        if not directory:
            return
        directory = Path(directory)

        try:
            self.library = MusicLibrary()
            self.library.load_directory(directory)
            self.audio_files = list(self.library.files)
        except Exception as e:
            messagebox.showerror(
                "Erreur", f"Erreur lors du chargement du dossier : {e}"
            )
            return

        self._refresh_file_list()

    def open_playlist(self):
        xspf_path = filedialog.askopenfilename(
            title="Ouvrir une playlist XSPF",
            filetypes=[("Playlist XSPF", "*.xspf"), ("Tous les fichiers", "*.*")],
        )
        if not xspf_path:
            return

        xspf_path = Path(xspf_path)
        if not xspf_path.exists():
            messagebox.showerror("Erreur", "Le fichier sélectionné n'existe pas.")
            return

        import xml.etree.ElementTree as ET
        from urllib.parse import urlparse, unquote

        try:
            tree = ET.parse(xspf_path)
            root = tree.getroot()
            ns = {"x": "http://xspf.org/ns/0/"}
            tracklist = root.find("x:trackList", ns)
            if tracklist is None:
                raise ValueError("Pas de trackList dans ce XSPF.")

            self.library = MusicLibrary()
            self.audio_files = []

            for track in tracklist.findall("x:track", ns):
                loc_el = track.find("x:location", ns)
                if loc_el is None or not loc_el.text:
                    continue
                uri = loc_el.text
                parsed = urlparse(uri)
                filepath = Path(unquote(parsed.path))

                if not filepath.exists():
                    print(f" Fichier introuvable : {filepath}")
                    continue

                self.library.load_file(filepath)

            self.audio_files = list(self.library.files)
            self._refresh_file_list()

        except Exception as e:
            messagebox.showerror(
                "Erreur", f"Erreur lors de l'ouverture de la playlist : {e}"
            )

    def generate_playlist_all(self):
        if not self.audio_files:
            messagebox.showinfo("Info", "Aucun fichier chargé.")
            return

        outfile = filedialog.asksaveasfilename(
            title="Enregistrer la playlist XSPF",
            defaultextension=".xspf",
            filetypes=[("Playlist XSPF", "*.xspf")],
        )
        if not outfile:
            return

        try:
            pg = PlaylistGenerator(dossier=Path("."), fichier_sortie=outfile)
            pg.set_audio_files(self.audio_files)
            pg.construire_piste()
            pg.ecrire_xspf(outfile, titre="Playlist GUI - tous", createur="GUI")
            messagebox.showinfo("Succès", f"Playlist générée : {outfile}")
        except Exception as e:
            messagebox.showerror(
                "Erreur", f"Erreur lors de la génération : {e}"
            )

    def generate_playlist_selection(self):
        selected_indices = list(self.listbox.curselection())
        if not selected_indices:
            messagebox.showinfo("Info", "Aucun morceau sélectionné.")
            return

        outfile = filedialog.asksaveasfilename(
            title="Enregistrer la playlist XSPF",
            defaultextension=".xspf",
            filetypes=[("Playlist XSPF", "*.xspf")],
        )
        if not outfile:
            return

        selected_files = [self.index_to_audio[i] for i in selected_indices]

        try:
            pg = PlaylistGenerator(dossier=Path("."), fichier_sortie=outfile)
            pg.set_audio_files(selected_files)
            pg.construire_piste()
            pg.ecrire_xspf(outfile, titre="Playlist GUI - sélection", createur="GUI")
            messagebox.showinfo("Succès", f"Playlist générée : {outfile}")
        except Exception as e:
            messagebox.showerror(
                "Erreur", f"Erreur lors de la génération : {e}"
            )

    # ------------- Liste / sélection -------------

    def _refresh_file_list(self):
        self.listbox.delete(0, tk.END)
        self.index_to_audio.clear()

        for idx, audio in enumerate(self.audio_files):
            display_name = audio.filepath.name
            self.listbox.insert(tk.END, display_name)
            self.index_to_audio[idx] = audio

        self.current_index = None
        self.current_offset = 0.0
        self._clear_details()
        self._update_highlights()

    def _clear_details(self):
        self.var_title.set("")
        self.var_artist.set("")
        self.var_album.set("")
        self.var_year.set("")
        self.var_duration.set("")
        self.var_format.set("")
        self.var_path.set("")
        self._set_lyrics_text("")
        self._clear_cover()
        self.progress_var.set(0.0)

    def _clear_cover(self):
        if HAS_PIL and self.placeholder_image is not None:
            self.cover_image_ref = self.placeholder_image
            self.cover_label.configure(image=self.placeholder_image, text="")
        else:
            self.cover_image_ref = None
            self.cover_label.configure(image="", text="[Cover]")

    def on_selection_change(self, event=None):
        selection = self.listbox.curselection()
        if not selection:
            self._clear_details()
            return

        idx = selection[0]
        self.current_index = idx
        self.current_offset = 0.0
        audio = self.index_to_audio.get(idx)
        if not audio:
            self._clear_details()
            return

        try:
            md = audio.extract_metadata()
        except Exception:
            md = {}

        self.var_title.set(md.get("title", "") or audio.filepath.stem)
        self.var_artist.set(md.get("artist", ""))
        self.var_album.set(md.get("album", ""))
        self.var_year.set(md.get("year", ""))
        self.var_format.set(md.get("format", ""))
        self.var_path.set(str(audio.filepath))

        try:
            duree = audio.get_duration()
            self.var_duration.set(str(int(round(duree))))
        except Exception:
            self.var_duration.set("")

        self._update_cover(audio)
        self._set_lyrics_text("")

        self._register_play(audio)

        if self.audio_player_enabled:
            self.play_current()

    def _update_cover(self, audio: AudioFile):
        if not HAS_PIL:
            self.cover_image_ref = None
            self.cover_label.configure(image="", text="[Cover]")
            return
        cover_data = audio.get_cover_art()
        if not cover_data:
            self._clear_cover()
            return
        try:
            img = Image.open(BytesIO(cover_data))
            img = img.convert("RGB")
            img.thumbnail((200, 200))
            photo = ImageTk.PhotoImage(img)
            self.cover_image_ref = photo
            self.cover_label.configure(image=photo, text="")
        except Exception as e:
            print(f"⚠️ Erreur affichage cover : {e}")
            self._clear_cover()

    def _get_card_cover_image(self, audio: AudioFile):
        if not HAS_PIL:
            return None
        try:
            cover_data = audio.get_cover_art()
            if not cover_data:
                # Pas de cover → mini placeholder
                return self.card_placeholder_image or self.placeholder_image

            img = Image.open(BytesIO(cover_data))
            img = img.convert("RGB")
            img.thumbnail((120, 120))
            return ImageTk.PhotoImage(img)
        except Exception:
            return self.card_placeholder_image or self.placeholder_image

    def _update_highlights(self):
        for child in self.highlights_frame.winfo_children():
            child.destroy()
        self.highlight_covers = []

        if not self.audio_files:
            ttk.Label(
                self.highlights_frame,
                text="Aucun fichier chargé",
                style="Normal.TLabel",
            ).pack(anchor="w", padx=5, pady=5)
            return

        for idx, audio in enumerate(self.audio_files[:4]):
            card = tk.Frame(
                self.highlights_frame,
                bg="#2b2f33" if not HAS_SV_TTK else None,
                cursor="hand2",
            )
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

            cover_zone = tk.Frame(
                card, bg="#202020" if not HAS_SV_TTK else None
            )
            cover_zone.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

            img = self._get_card_cover_image(audio)
            lbl_cover = tk.Label(
                cover_zone,
                image=img,
                bg="#202020" if not HAS_SV_TTK else None,
            )
            lbl_cover.pack(expand=True)
            if img is not None:
                self.highlight_covers.append(img)
            lbl_cover.bind("<Button-1>", lambda e, i=idx: self.play_from_index(i))

            footer = tk.Frame(
                card, bg="#ffc107" if not HAS_SV_TTK else None
            )
            footer.pack(fill=tk.X, padx=6, pady=(0, 6))

            try:
                md = audio.extract_metadata()
            except Exception:
                md = {}
            title = md.get("title") or audio.filepath.stem
            artist = md.get("artist") or ""

            tk.Label(
                footer,
                text=title,
                bg="#ffc107" if not HAS_SV_TTK else None,
                fg="black" if not HAS_SV_TTK else None,
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                footer,
                text=artist,
                bg="#ffc107" if not HAS_SV_TTK else None,
                fg="black" if not HAS_SV_TTK else None,
                anchor="w",
            ).pack(anchor="w")

            card.bind("<Button-1>", lambda e, i=idx: self.play_from_index(i))
            cover_zone.bind("<Button-1>", lambda e, i=idx: self.play_from_index(i))
            footer.bind("<Button-1>", lambda e, i=idx: self.play_from_index(i))

    def play_from_index(self, idx: int):
        if idx not in self.index_to_audio:
            return
        self.current_index = idx
        self.current_offset = 0.0
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.listbox.event_generate("<<ListboxSelect>>")
        self.play_current()

    # ------------- Stats -------------

    def _register_play(self, audio: AudioFile):
        try:
            md = audio.extract_metadata()
        except Exception:
            md = {}

        title = md.get("title") or audio.filepath.stem
        artist = md.get("artist", "")
        display = f"{title} – {artist}" if artist else title

        if display in self.recent_history:
            self.recent_history.remove(display)
        self.recent_history.insert(0, display)
        self.recent_history = self.recent_history[:5]
        self._refresh_recent_box()

        key = str(audio.filepath)
        self.play_count[key] = self.play_count.get(key, 0) + 1
        self._refresh_top_box()

    def _refresh_recent_box(self):
        self.recent_box.delete(0, tk.END)
        for item in self.recent_history:
            self.recent_box.insert(tk.END, item)

    def _refresh_top_box(self):
        self.top_box.delete(0, tk.END)
        if not self.play_count:
            return
        sorted_items = sorted(
            self.play_count.items(), key=lambda kv: kv[1], reverse=True
        )[:5]
        for path_str, count in sorted_items:
            name = Path(path_str).name
            self.top_box.insert(tk.END, f"{name} ({count}×)")

    # ------------- Paroles -------------

    def _set_lyrics_text(self, text: str):
        self.lyrics_text.config(state=tk.NORMAL)
        self.lyrics_text.delete("1.0", tk.END)
        if text:
            self.lyrics_text.insert(tk.END, text)
        self.lyrics_text.config(state=tk.DISABLED)

    # ------------- Métadonnées / API -------------

    def save_metadata_current(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Info", "Aucun morceau sélectionné.")
            return

        idx = selection[0]
        audio = self.index_to_audio.get(idx)
        if not audio:
            return

        if not hasattr(audio, "metadata") or audio.metadata is None:
            audio.metadata = {}

        audio.metadata["title"] = self.var_title.get()
        audio.metadata["artist"] = self.var_artist.get()
        audio.metadata["album"] = self.var_album.get()
        audio.metadata["year"] = self.var_year.get()

        try:
            audio.save_metadata()
            messagebox.showinfo("Succès", "Métadonnées sauvegardées dans le fichier.")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la sauvegarde : {e}")

    def fetch_api_current(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Info", "Aucun morceau sélectionné.")
            return

        idx = selection[0]
        audio = self.index_to_audio.get(idx)
        if not audio:
            return

        enriched = self.metadata_fetcher.update_audio_file_metadata(audio)
        if enriched:
            try:
                md = audio.extract_metadata()
            except Exception:
                md = {}
            self.var_title.set(md.get("title", "") or audio.filepath.stem)
            self.var_artist.set(md.get("artist", ""))
            self.var_album.set(md.get("album", ""))
            self.var_year.set(md.get("year", ""))
            self._update_cover(audio)
        else:
            messagebox.showinfo("Info", "Aucune métadonnée trouvée via Spotify.")

        lyrics = self.metadata_fetcher.fetch_lyrics_for_audio(audio)
        if lyrics:
            self._set_lyrics_text(lyrics)
        else:
            self._set_lyrics_text("[Aucune parole trouvée via l’API]")


if __name__ == "__main__":
    app = MusicLibraryGUI()
    app.mainloop()
