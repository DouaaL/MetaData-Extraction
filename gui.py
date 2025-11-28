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

# Importations
try:
    from library.models.music_library import MusicLibrary
    from library.models.audio_file import AudioFile
    from library.core.playlist_generator import PlaylistGenerator
    from library.core.metadatafetcher import MetadataFetcher
except ImportError:
    print("Erreur d'import des modules library. Vérifiez votre structure de dossiers.")
    sys.exit(1)


class MusicLibraryGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PyMetaPlay")
        self.geometry("1150x780")
        self.minsize(950, 650)

        # --- COULEURS ---
        self.colors = {
            "bg": "#121212",        # Fond très sombre
            "sidebar": "#1e1e1e",   # Fond sidebar
            "player": "#181818",    # Fond barre du bas
            "accent": "#ffc107",    # JAUNE (Votre couleur)
            "text": "#ffffff",
            "text_dim": "#b3b3b3",
            "text_on_accent": "#000000" # Noir sur jaune pour le contraste
        }
        
        self.configure(bg=self.colors["bg"])

        # Chargement du thème sombre
        if HAS_SV_TTK:
            sv_ttk.use_dark_theme()
        
        # Données
        self.library = MusicLibrary()
        self.audio_files: List[AudioFile] = []     
        self.displayed_files: List[AudioFile] = [] 
        self.index_to_audio: Dict[int, AudioFile] = {}
        
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

        # Images
        self.cover_image_ref = None
        self.placeholder_image = None
        if HAS_PIL:
            # On génère la cover par défaut (Clef de sol)
            self.placeholder_image = self._create_placeholder_cover(size=320)

        self._setup_styles()
        self._build_layout()
        self._build_menu()

        # Loop
        self.after(500, self._progress_loop)

    def _setup_styles(self):
        style = ttk.Style(self)
        
        # Styles des conteneurs
        style.configure("Sidebar.TFrame", background=self.colors["sidebar"])
        style.configure("Player.TFrame", background=self.colors["player"])
        style.configure("Main.TFrame", background=self.colors["bg"])
        
        # Styles des textes
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("Artist.TLabel", font=("Segoe UI", 14, "bold"), background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("Detail.TLabel", font=("Segoe UI", 11), background=self.colors["bg"], foreground=self.colors["text_dim"])
        style.configure("SidebarHeader.TLabel", font=("Segoe UI", 11, "bold"), background=self.colors["sidebar"], foreground=self.colors["text_dim"])
        
        # --- NOUVEAU STYLE JAUNE PERSONNALISÉ ---
        # On crée un style spécifique pour forcer le jaune sur les boutons importants
        # au lieu d'utiliser le bleu par défaut du thème.
        style.configure("Yellow.TButton",
            font=("Segoe UI", 10, "bold"),
            background=self.colors["accent"],      # Fond JAUNE
            foreground=self.colors["text_on_accent"], # Texte NOIR
            borderwidth=0,
            focusthickness=3,
            focuscolor=self.colors["accent"]
        )
        # Effet au survol (un peu plus clair) et au clic (un peu plus foncé)
        style.map("Yellow.TButton",
            background=[("pressed", "#e0a800"), ("active", "#ffd54f")],
            foreground=[("pressed", self.colors["text_on_accent"]), ("active", self.colors["text_on_accent"])]
        )

        # Style spécifique pour le gros bouton PLAY (hérite du jaune)
        style.configure("Play.TButton",
            font=("Segoe UI Symbol", 22),
            padding=(10, 5),
            background=self.colors["accent"],
            foreground=self.colors["text_on_accent"]
        )
        style.map("Play.TButton", background=[("pressed", "#e0a800"), ("active", "#ffd54f")])

    def _build_layout(self):
        self.columnconfigure(0, weight=0) # Sidebar fixe
        self.columnconfigure(1, weight=1) # Contenu
        self.rowconfigure(0, weight=1)    # Contenu
        self.rowconfigure(1, weight=0)    # Player bar

        # 1. SIDEBAR
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=15)
        sidebar.grid(row=0, column=0, sticky="nsew")
        self._build_sidebar(sidebar)

        # 2. MAIN CONTENT
        main_content = ttk.Frame(self, style="Main.TFrame", padding=30)
        main_content.grid(row=0, column=1, sticky="nsew")
        self._build_main_content(main_content)

        # 3. PLAYER BAR
        player_bar = ttk.Frame(self, style="Player.TFrame", height=100)
        player_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        player_bar.pack_propagate(False) 
        self._build_player_bar(player_bar)

    def _build_sidebar(self, parent):
        # Titre
        lbl = ttk.Label(parent, text="🎵 PyMetaPlay", font=("Segoe UI", 16, "bold"), background=self.colors["sidebar"], foreground=self.colors["accent"])
        lbl.pack(anchor="w", pady=(0, 25))

        # Recherche
        ttk.Label(parent, text="RECHERCHE", style="SidebarHeader.TLabel").pack(anchor="w", pady=(5, 5))
        search_frame = ttk.Frame(parent, style="Sidebar.TFrame")
        search_frame.pack(fill=tk.X, pady=(0, 10))
        self.var_search = tk.StringVar()
        self.var_search.trace("w", self.on_search_change) 
        entry = ttk.Entry(search_frame, textvariable=self.var_search)
        entry.pack(fill=tk.X)
        
        # Boutons Menu
        ttk.Label(parent, text="BIBLIOTHÈQUE", style="SidebarHeader.TLabel").pack(anchor="w", pady=(20, 5))
        btn_style = {"bg": self.colors["sidebar"], "fg": "white", "bd": 0, "anchor": "w", "padx": 10, "pady": 5, "cursor": "hand2", "activebackground": "#333", "activeforeground": "white", "relief": "flat"}
        tk.Button(parent, text="📂 Ouvrir Dossier", command=self.open_directory, **btn_style).pack(fill=tk.X, pady=1)
        tk.Button(parent, text="📄 Playlist XSPF", command=self.open_playlist, **btn_style).pack(fill=tk.X, pady=1)
        tk.Button(parent, text="💾 Sauvegarder Playlist", command=self.generate_playlist_selection, **btn_style).pack(fill=tk.X, pady=1)

        # Liste
        ttk.Label(parent, text="PISTES", style="SidebarHeader.TLabel").pack(anchor="w", pady=(20, 5))
        list_container = ttk.Frame(parent)
        list_container.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox = tk.Listbox(
            list_container, bg="#252525", fg="#e0e0e0", bd=0, highlightthickness=0,
            selectbackground=self.colors["accent"], selectforeground="black",
            font=("Segoe UI", 10), yscrollcommand=scrollbar.set, activestyle="none"
        )
        self.listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.on_selection_change)

    def _build_main_content(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)

        # COVER (Gauche)
        cover_frame = ttk.Frame(parent, style="Main.TFrame")
        cover_frame.grid(row=0, column=0, sticky="n", padx=(0, 30), pady=10)
        self.cover_label = tk.Label(cover_frame, bg=self.colors["bg"], bd=0)
        self.cover_label.pack()
        self._clear_cover()

        # INFO (Droite)
        info_frame = ttk.Frame(parent, style="Main.TFrame")
        info_frame.grid(row=0, column=1, sticky="nsew")

        self.var_title = tk.StringVar(value="Aucune lecture")
        self.var_artist = tk.StringVar(value="--")
        self.var_details = tk.StringVar(value="") 
        
        ttk.Label(info_frame, textvariable=self.var_title, style="Title.TLabel", wraplength=500).pack(anchor="w", fill=tk.X)
        ttk.Label(info_frame, textvariable=self.var_artist, style="Artist.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(info_frame, textvariable=self.var_details, style="Detail.TLabel").pack(anchor="w", pady=(2, 15))

        # Paroles
        ttk.Label(info_frame, text="PAROLES", style="SidebarHeader.TLabel", background=self.colors["bg"]).pack(anchor="w", pady=(10, 5))
        self.lyrics_text = tk.Text(info_frame, height=12, bg="#1a1a1a", fg="#cccccc", bd=0, highlightthickness=0, font=("Segoe UI", 10), wrap=tk.WORD, state=tk.DISABLED)
        self.lyrics_text.pack(fill=tk.BOTH, expand=True)

        # Boutons API
        action_frame = ttk.Frame(info_frame, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=20)
        
        # --- UTILISATION DU STYLE JAUNE ---
        # Le bouton API utilise maintenant "Yellow.TButton"
        ttk.Button(action_frame, text="☁️ Recherche API (Spotify)", command=self.fetch_api_current, style="Yellow.TButton").pack(side=tk.LEFT, padx=(0, 10))
        # Le bouton Sauvegarder reste standard (gris) pour le contraste, ou mettez "Yellow.TButton" si vous le voulez jaune aussi.
        ttk.Button(action_frame, text="💾 Sauvegarder Tags", command=self.save_metadata_current).pack(side=tk.LEFT)

        self.var_album_internal = ""
        self.var_year_internal = ""
        self.var_duration = tk.StringVar()
        self.var_path = tk.StringVar()

    def _build_player_bar(self, parent):
        center_frame = tk.Frame(parent, bg=self.colors["player"])
        center_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=40)

        # 1. Contrôles
        controls = tk.Frame(center_frame, bg=self.colors["player"])
        controls.pack(side=tk.TOP, pady=(15, 5))

        btn_sec_style = {"bg": self.colors["player"], "fg": "white", "activebackground": self.colors["player"], "activeforeground": self.colors["accent"], "bd": 0, "font": ("Segoe UI Symbol", 14), "cursor": "hand2", "relief": "flat"}

        self.btn_repeat = tk.Button(controls, text="🔁", command=self.toggle_repeat, **btn_sec_style)
        self.btn_repeat.pack(side=tk.LEFT, padx=15)
        tk.Button(controls, text="⏮", command=self.play_prev, **btn_sec_style).pack(side=tk.LEFT, padx=15)
        
        # --- UTILISATION DU STYLE PLAY JAUNE ---
        self.btn_play = ttk.Button(controls, text="▶", command=self.toggle_play_pause, style="Play.TButton", width=5)
        self.btn_play.pack(side=tk.LEFT, padx=20)

        tk.Button(controls, text="⏭", command=self.play_next, **btn_sec_style).pack(side=tk.LEFT, padx=15)
        self.btn_vol = tk.Button(controls, text="🔊", command=self.toggle_mute, **btn_sec_style)
        self.btn_vol.pack(side=tk.LEFT, padx=15)

        # 2. Barre de progression
        progress_frame = tk.Frame(center_frame, bg=self.colors["player"])
        progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 15))
        self.lbl_current_time = tk.Label(progress_frame, text="0:00", bg=self.colors["player"], fg="grey", font=("Segoe UI", 9))
        self.lbl_current_time.pack(side=tk.LEFT, padx=10)
        self.progress_var = tk.DoubleVar()
        # Note: La couleur du slider reste gérée par le thème sv_ttk (souvent bleu), difficile à changer simplement.
        self.progress_scale = ttk.Scale(progress_frame, variable=self.progress_var, from_=0, to=100)
        self.progress_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_scale.bind("<Button-1>", self._on_progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self._on_progress_release)
        self.lbl_total_time = tk.Label(progress_frame, text="0:00", bg=self.colors["player"], fg="grey", font=("Segoe UI", 9))
        self.lbl_total_time.pack(side=tk.RIGHT, padx=10)

    def _build_menu(self):
        menubar = tk.Menu(self)
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Ouvrir dossier", command=self.open_directory)
        menu_file.add_command(label="Quitter", command=self.quit)
        menubar.add_cascade(label="Fichier", menu=menu_file)
        self.config(menu=menubar)

    # ------------------ LOGIQUE ------------------

    def open_directory(self):
        directory = filedialog.askdirectory()
        if not directory: return
        try:
            self.library = MusicLibrary()
            self.library.load_directory(Path(directory))
            self.audio_files = list(self.library.files)
            self.displayed_files = list(self.audio_files)
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
                md = getattr(audio, 'metadata', {}) or {}
                txt_search = f"{audio.filepath.stem} {md.get('title','')} {md.get('artist','')}".lower()
                if query in txt_search:
                    filtered.append(audio)
            self.displayed_files = filtered
        self._refresh_listbox()

    def _refresh_listbox(self):
        self.listbox.delete(0, tk.END)
        self.index_to_audio.clear()
        if not self.displayed_files:
            self.listbox.insert(tk.END, "(Aucun résultat)")
            return
        for idx, audio in enumerate(self.displayed_files):
            name = audio.filepath.stem
            md = getattr(audio, 'metadata', {}) or {}
            if md.get('title'):
                name = md.get('title')
                if md.get('artist'):
                    name += f" - {md.get('artist')}"
            self.listbox.insert(tk.END, f"{idx+1}. {name}")
            self.index_to_audio[idx] = audio

    def on_selection_change(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx not in self.index_to_audio: return
        self.play_from_index(idx)

    def play_from_index(self, idx):
        self.current_index = idx
        self.current_offset = 0.0
        audio = self.index_to_audio.get(idx)
        if not audio: return

        try: md = audio.extract_metadata()
        except: md = {}
        
        self.var_title.set(md.get("title") or audio.filepath.stem)
        self.var_artist.set(md.get("artist") or "Artiste inconnu")
        self.var_path.set(str(audio.filepath))
        
        self.var_album_internal = md.get("album") or ""
        self.var_year_internal = str(md.get("year") or "")

        details = []
        if self.var_album_internal: details.append(self.var_album_internal)
        if self.var_year_internal: details.append(self.var_year_internal)
        self.var_details.set(" • ".join(details) if details else "")
        
        self._update_cover(audio)
        self._set_lyrics_text("")

        try:
            dur = audio.get_duration()
            self.var_duration.set(str(dur))
            self.lbl_total_time.config(text=self._fmt_time(dur))
        except:
            self.var_duration.set("0")
        
        if self.audio_player_enabled:
            try:
                pygame.mixer.music.load(str(audio.filepath))
                pygame.mixer.music.play()
                self.is_playing = True
                self.is_paused = False
                self.btn_play.config(text="⏸")
            except Exception as e:
                print("Erreur lecture:", e)

    def _progress_loop(self):
        if self.audio_player_enabled and self.is_playing and not self.is_paused and not self.user_dragging_progress:
            try:
                current_ms = pygame.mixer.music.get_pos()
                if current_ms >= 0:
                    actual_seconds = self.current_offset + (current_ms / 1000.0)
                    total_str = self.var_duration.get()
                    if total_str:
                        total = float(total_str)
                        if total > 0:
                            pct = (actual_seconds / total) * 100
                            self.progress_var.set(pct)
                            self.lbl_current_time.config(text=self._fmt_time(actual_seconds))
            except: pass
        if self.audio_player_enabled and not pygame.mixer.music.get_busy() and self.is_playing and not self.is_paused:
            self.play_next()
        self.after(500, self._progress_loop)

    def _fmt_time(self, seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    # --- Contrôles ---
    def toggle_play_pause(self):
        if not self.audio_player_enabled: return
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
            next_idx = (self.current_index + 1) % len(self.displayed_files)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(next_idx)
            self.listbox.see(next_idx)
            self.play_from_index(next_idx)

    def play_prev(self):
        if self.current_index is not None and self.displayed_files:
            prev_idx = (self.current_index - 1) % len(self.displayed_files)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(prev_idx)
            self.listbox.see(prev_idx)
            self.play_from_index(prev_idx)

    def toggle_repeat(self):
        self.repeat = not self.repeat
        color = self.colors["accent"] if self.repeat else "white"
        self.btn_repeat.config(fg=color)

    def toggle_mute(self):
        self.muted = not self.muted
        vol = 0.0 if self.muted else self.volume
        pygame.mixer.music.set_volume(vol)
        self.btn_vol.config(text="🔈" if self.muted else "🔊")

    # --- Seek ---
    def _on_progress_press(self, event):
        self.user_dragging_progress = True

    def _on_progress_release(self, event):
        self.user_dragging_progress = False
        val = self.progress_scale.get()
        self._seek_absolute(val)

    def _seek_absolute(self, percent):
        if not self.audio_player_enabled or not self.var_duration.get(): return
        total = float(self.var_duration.get())
        new_time = (float(percent) / 100.0) * total
        self.current_offset = new_time
        try: pygame.mixer.music.play(start=new_time) 
        except:
            pygame.mixer.music.rewind()
            pygame.mixer.music.set_pos(new_time) 
        self.is_playing = True
        self.is_paused = False
        self.btn_play.config(text="⏸")

    # --- API & Save ---
    def fetch_api_current(self):
        if self.current_index is None: return
        audio = self.index_to_audio[self.current_index]
        messagebox.showinfo("Recherche API", f"Recherche pour : {audio.filepath.stem}...")
        try:
            self.metadata_fetcher.update_audio_file_metadata(audio)
            lyrics = self.metadata_fetcher.fetch_lyrics_for_audio(audio)
            self.play_from_index(self.current_index)
            if lyrics: self._set_lyrics_text(lyrics)
            messagebox.showinfo("Succès", "Données mises à jour depuis Spotify/API !")
        except Exception as e:
            messagebox.showerror("Erreur API", f"Erreur : {e}")

    def save_metadata_current(self):
        if self.current_index is None: return
        audio = self.index_to_audio[self.current_index]
        audio.metadata = audio.metadata or {}
        try:
            audio.save_metadata()
            messagebox.showinfo("Succès", "Tags sauvegardés")
        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            
    def open_playlist(self): pass 
    def generate_playlist_selection(self): pass 

    # --- Images (CLEF DE SOL) ---
    def _create_placeholder_cover(self, size=320):
        """ Crée une image noire avec une CLEF DE SOL JAUNE """
        img = Image.new("RGB", (size, size), "#121212")
        draw = ImageDraw.Draw(img)
        
        # --- Changement ici : Utilisation de la Clef de Sol ---
        text = "𝄞" 
        
        # On essaie de trouver une police qui supporte ce symbole
        font = None
        try:
            # Segoe UI Symbol (Windows) est le meilleur pour ça
            font = ImageFont.truetype("seguisym.ttf", 180) 
        except:
            try:
                # Fallback Arial Unicode ou autre
                font = ImageFont.truetype("arialuni.ttf", 180)
            except:
                try:
                     # Dernier recours : une police standard grosse, 
                     # mais si elle n'a pas le symbole, ça fera un carré vide.
                    font = ImageFont.truetype("arial.ttf", 180)
                except:
                    # Vraiment si rien ne marche, on revient à la note simple
                    text = "♪"
                    font = ImageFont.load_default()

        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
        except:
            w, h = draw.textsize(text, font=font)
            
        x = (size - w) / 2
        y = (size - h) / 2
        
        # Dessin du symbole en JAUNE
        draw.text((x, y), text, font=font, fill=self.colors["accent"])
        
        # Pas de rectangle !
        return ImageTk.PhotoImage(img)

    def _clear_cover(self):
        if self.placeholder_image:
            self.cover_label.config(image=self.placeholder_image)
            self.cover_image_ref = self.placeholder_image

    def _update_cover(self, audio):
        if not HAS_PIL: return
        data = audio.get_cover_art()
        if data:
            try:
                img = Image.open(BytesIO(data))
                img.thumbnail((320, 320))
                photo = ImageTk.PhotoImage(img)
                self.cover_label.config(image=photo)
                self.cover_image_ref = photo
            except:
                self._clear_cover()
        else:
            self._clear_cover()
    
    def _set_lyrics_text(self, text):
        self.lyrics_text.config(state=tk.NORMAL)
        self.lyrics_text.delete("1.0", tk.END)
        self.lyrics_text.insert(tk.END, text if text else "Paroles non disponibles.")
        self.lyrics_text.config(state=tk.DISABLED)

if __name__ == "__main__":
    app = MusicLibraryGUI()
    app.mainloop()