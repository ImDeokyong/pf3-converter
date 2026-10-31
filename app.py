"""PF3 Converter: CUBE/XMP to Canon PF3, Adobe XMP and LUMIX CUBE."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from app_info import APP_NAME, APP_VERSION, APP_AUTHOR, display_name
from canon_render import render_pair
from i18n import LANGUAGES, LANGUAGE_LABELS, load_language, save_language, tr
from lut import load_cube, write_cube
from lumix_export import export_lumix_cube, export_srgb_cube, PHOTO_STYLES
from lut_classifier import classify_lut
from pf3_native import STYLE_IDS, export_pf3, find_canon_library
from photo_loader import load_photo, patterns, RAW_EXTENSIONS, RASTER_EXTENSIONS
from raw_strength import recommend_strength
from preview import ComparisonView
from xmp_bridge import load_xmp, export_xmp

PSE_URL = 'https://app.ssw.imaging-saas.canon/app/en/pse.html'


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.language = load_language()
        self._translatables = []
        self._dynamic = {}
        self.root.title(self.tr('app_title', name=display_name()))
        self.root.minsize(850, 725)
        self.root.geometry('1100x870')
        self.photo_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='photo-load')
        self.native_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='canon-preview')
        self.strength_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='raw-strength')
        self.strength_future = None
        self.strength_timer = None
        self.strength_paths = ()
        self.strength_cube = None
        self.strength_lut_kind = None
        self.strength_message = tk.StringVar(value=self.tr('raw_strength_ready'))
        self.lut_classification = None
        self.lut_kind_override = 'auto'
        self.lut_kind_selection = tk.StringVar()
        self.lut_class_message = tk.StringVar(value=self.tr('lut_class_empty'))
        self.native_future = None
        self.native_pending = None
        self.native_timer = None
        self.native_poll_timer = None
        self.native_sequence = 0
        self.native_report = None
        self.raw_path = None
        self.source_photo = None
        self.preview_mode = tk.StringVar(value=self.tr('mode_canon'))
        self.photo_future = None
        self.photo_timer = None
        self.closed = False
        self.root.bind('<Destroy>', self.on_destroy, add='+')
        self.cube = None
        self.cube_path: Path | None = None
        self.input_kind = 'cube'
        self.input_info = None
        self.photo = None
        self.preview = None
        self.base = tk.StringVar(value='Neutral')
        self.lumix_style = tk.StringVar(value='STD')
        self.name = tk.StringVar(value='')
        self.strength = tk.DoubleVar(value=50)
        self.dll_path = tk.StringVar(value='')
        self.status = tk.StringVar()
        self.photo_status = tk.StringVar()
        self._set_dynamic(self.status, 'choose_lut')
        self._set_dynamic(self.photo_status, 'photo_ready')

        outer = ttk.Frame(root, padding=18)
        outer.pack(fill='both', expand=True)
        heading = ttk.Frame(outer)
        heading.pack(fill='x')
        ttk.Label(heading, text=APP_NAME, font=('Segoe UI', 23, 'bold')).pack(side='left')
        language_bar = ttk.Frame(heading)
        language_bar.pack(side='right')
        self._label(language_bar, 'language').pack(side='left', padx=(0, 6))
        self.language_label = tk.StringVar(value=LANGUAGES[self.language])
        self.language_picker = ttk.Combobox(language_bar, textvariable=self.language_label, state='readonly',
                                            width=12, values=list(LANGUAGES.values()))
        self.language_picker.pack(side='left', padx=(0, 12))
        self.language_picker.bind('<<ComboboxSelected>>', self.change_language)
        self._button(language_bar, 'about', self.show_about).pack(side='left')
        self._label(outer, 'credit', version=APP_VERSION, author=APP_AUTHOR,
                    font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 2))
        self._label(outer, 'description').pack(anchor='w', pady=(3, 13))

        input_row = ttk.Frame(outer)
        input_row.pack(fill='x', pady=(0, 8))
        self._button(input_row, 'open_lut', self.open_cube).pack(side='left', padx=(0, 8))
        self.photo_button = self._button(input_row, 'open_photo', self.open_photo)
        self.photo_button.pack(side='left', padx=(0, 8))
        self._button(input_row, 'resample', self.resample).pack(side='left')
        status_label = ttk.Label(outer, textvariable=self.status, wraplength=1000)
        status_label.pack(fill='x', anchor='w', pady=(0, 9))
        status_label.bind('<Configure>', lambda e: status_label.configure(wraplength=max(200, e.width - 12)))
        photo_status_label = ttk.Label(outer, textvariable=self.photo_status, wraplength=1000)
        photo_status_label.pack(fill='x', anchor='w', pady=(0, 5))
        photo_status_label.bind('<Configure>', lambda e: photo_status_label.configure(wraplength=max(200, e.width - 12)))

        modes = ttk.Frame(outer)
        modes.pack(fill='x', pady=(0, 5))
        self._label(modes, 'comparison_mode').pack(side='left')
        self.mode_selector = ttk.Combobox(modes, textvariable=self.preview_mode, state='readonly', width=32,
                                         values=self._mode_options())
        self.mode_selector.pack(side='left', padx=8)
        self.mode_selector.bind('<<ComboboxSelected>>', lambda e: self.update_preview())
        self._label(modes, 'canon_preview_note').pack(side='left')
        self.preview_view = ComparisonView(outer, translator=self.tr)
        self.preview_view.pack(fill='both', expand=True)

        options = self._frame(outer, 'pf3_settings', padding=12)
        options.pack(fill='x', pady=(14, 0))
        row = ttk.Frame(options)
        row.pack(fill='x', pady=(0, 9))
        self._label(row, 'style_name', width=13).pack(side='left')
        ttk.Entry(row, textvariable=self.name, width=32).pack(side='left', padx=(0, 16))
        self._label(row, 'base_style').pack(side='left', padx=(0, 6))
        base_selector = ttk.Combobox(row, textvariable=self.base, values=list(STYLE_IDS), width=16, state='readonly')
        base_selector.pack(side='left')
        base_selector.bind('<<ComboboxSelected>>', lambda e: self.update_preview())
        row = ttk.Frame(options)
        row.pack(fill='x', pady=(0, 10))
        self._label(row, 'strength', width=13).pack(side='left')
        ttk.Scale(row, variable=self.strength, from_=0, to=100, orient='horizontal',
                  command=self.on_strength).pack(side='left', fill='x', expand=True)
        self.strength_label = ttk.Label(row, text='50%', width=6)
        self.strength_label.pack(side='left', padx=(10, 4))
        class_row = ttk.Frame(options)
        class_row.pack(fill='x', pady=(0, 9))
        self._label(class_row, 'lut_class_label', width=13).pack(side='left')
        self.lut_class_info = ttk.Label(class_row, textvariable=self.lut_class_message)
        self.lut_class_info.pack(side='left', padx=(0, 12))
        self.lut_class_picker = ttk.Combobox(class_row, textvariable=self.lut_kind_selection,
                                             state='readonly', width=19,
                                             values=self._lut_class_options())
        self.lut_class_picker.pack(side='right')
        self.lut_class_picker.bind('<<ComboboxSelected>>', self.on_lut_class_override)
        self.lut_kind_selection.set(self.tr('lut_class_override_auto'))
        self._label(class_row, 'lut_class_override_label').pack(side='right', padx=(0, 8))
        raw_row = ttk.Frame(options)
        raw_row.pack(fill='x', pady=(0, 9))
        self.raw_strength_button = self._button(raw_row, 'raw_strength_button', self.start_raw_strength)
        self.raw_strength_button.pack(side='left', padx=(0, 10))
        self.raw_strength_label = ttk.Label(raw_row, textvariable=self.strength_message, wraplength=720)
        self.raw_strength_label.pack(side='left', fill='x', expand=True)
        self.raw_strength_label.bind('<Configure>', lambda e: self.raw_strength_label.configure(
            wraplength=max(200, e.width - 12)))
        row = ttk.Frame(options)
        row.pack(fill='x', pady=(0, 9))
        self._label(row, 'canon_engine', width=13).pack(side='left')
        ttk.Entry(row, textvariable=self.dll_path).pack(side='left', fill='x', expand=True)
        self._button(row, 'choose_path', self.pick_dll).pack(side='left', padx=(7, 0))
        self._button(row, 'check_installation', self.check_dll).pack(side='left', padx=(7, 0))
        self._label(options, 'dll_note', foreground='#5d5d5d').pack(anchor='w')

        action = ttk.Frame(outer)
        action.pack(fill='x', pady=(11, 4))
        self._button(action, 'save_pf3', self.save_pf3).pack(side='left')
        self.xmp_button = self._button(action, 'save_xmp', self.save_xmp, state='disabled')
        self.xmp_button.pack(side='left', padx=(12, 0))
        self._button(action, 'install_pse', lambda: webbrowser.open(PSE_URL)).pack(side='left', padx=(12, 0))
        lumix_row = ttk.Frame(outer)
        lumix_row.pack(fill='x', pady=(5, 1))
        self._label(lumix_row, 'lumix_base_label').pack(side='left', padx=(0, 8))
        self.lumix_selector = ttk.Combobox(lumix_row, textvariable=self.lumix_style,
             values=list(PHOTO_STYLES), state='readonly', width=12)
        self.lumix_selector.pack(side='left', padx=(0, 10))
        self._button(lumix_row, 'save_lumix', self.save_lumix).pack(side='left', padx=(0, 10))
        self._label(lumix_row, 'lumix_note', foreground='#5d5d5d').pack(side='left', fill='x', expand=True)

    def tr(self, key: str, **values) -> str:
        return tr(self.language, key, **values)

    def _label(self, parent, key, **options):
        placeholders = {k: options.pop(k) for k in list(options) if k in ('version', 'author')}
        widget = ttk.Label(parent, text=self.tr(key, **placeholders), **options)
        self._translatables.append((widget, key, placeholders))
        return widget

    def _button(self, parent, key, command, **options):
        widget = ttk.Button(parent, text=self.tr(key), command=command, **options)
        self._translatables.append((widget, key, {}))
        return widget

    def _frame(self, parent, key, **options):
        widget = ttk.LabelFrame(parent, text=self.tr(key), **options)
        self._translatables.append((widget, key, {}))
        return widget

    def _set_dynamic(self, variable, key, **values):
        self._dynamic[str(variable)] = (variable, key, values)
        variable.set(self.tr(key, **values))

    def _mode_options(self):
        return (self.tr('mode_canon'), self.tr('mode_reference'))

    def _lut_class_options(self):
        return tuple(self.tr('lut_class_override_' + key)
                     for key in ('auto', 'creative', 'technical', 'hybrid'))

    def _effective_lut_kind(self):
        if self.input_kind != 'cube' or self.lut_classification is None:
            return 'other'
        return (self.lut_kind_override if self.lut_kind_override != 'auto'
                else self.lut_classification.kind)

    def _refresh_lut_class(self):
        if self.input_kind != 'cube' or self.lut_classification is None:
            self.lut_class_message.set(self.tr('lut_class_empty'))
        else:
            report = self.lut_classification
            self.lut_class_message.set(self.tr('lut_class_result',
                kind=self.tr('lut_class_kind_' + self._effective_lut_kind()),
                confidence=self.tr('lut_class_confidence_' + report.confidence)))
        # Never block PF3 conversion. The optimizer is exclusively intended
        # for creative LUTs; uncertain types remain opt-in because uncertain
        # signatures are explicitly not proof of a technical input domain.
        permitted = self._effective_lut_kind() in ('creative', 'uncertain', 'other')
        if hasattr(self, 'raw_strength_button') and self.strength_future is None:
            self.raw_strength_button.configure(state='normal' if permitted else 'disabled')
        if (self._effective_lut_kind() in ('technical', 'hybrid')
                and self.strength_future is None and not hasattr(self, 'strength_result')):
            self.strength_message.set(self.tr('lut_class_raw_unavailable'))
        elif (self.strength_future is None and not hasattr(self, 'strength_result')):
            self.strength_message.set(self.tr('raw_strength_ready'))

    def on_lut_class_override(self, _=None):
        selected = self.lut_kind_selection.get()
        for key in ('auto', 'creative', 'technical', 'hybrid'):
            if selected == self.tr('lut_class_override_' + key):
                self.lut_kind_override = key
                if (self._effective_lut_kind() in ('technical', 'hybrid')
                        and hasattr(self, 'strength_result')):
                    del self.strength_result  # Old Creative recommendation no longer applies.
                self._refresh_lut_class()
                return

    def _is_canon_mode(self):
        # Keep both the current localized values and legacy Korean constants
        # recognizable so callers/tests that directly set preview_mode still work.
        current = self.preview_mode.get()
        return current in {tr(lang, 'mode_canon') for lang in LANGUAGES}

    def change_language(self, _=None):
        language = LANGUAGE_LABELS.get(self.language_label.get())
        if not language or language == self.language:
            return
        was_canon = self._is_canon_mode()
        self.language = language
        save_language(language)
        self.root.title(self.tr('app_title', name=display_name()))
        for widget, key, values in self._translatables:
            widget.configure(text=self.tr(key, **values))
        for var, key, values in self._dynamic.values():
            var.set(self.tr(key, **values))
        if self.cube is not None and str(self.status) not in self._dynamic:
            self._show_loaded_status()
        self.mode_selector.configure(values=self._mode_options())
        self.preview_mode.set(self.tr('mode_canon' if was_canon else 'mode_reference'))
        self.preview_view.refresh_language()
        if self.strength_future is None:
            if hasattr(self, 'strength_result'):
                r = self.strength_result
                self.strength_message.set(self.tr('raw_strength_result',
                    percent=r.recommended_percent, count=r.photos))
            else:
                self.strength_message.set(self.tr('raw_strength_ready'))
        self.lut_class_picker.configure(values=self._lut_class_options())
        self.lut_kind_selection.set(self.tr('lut_class_override_' + self.lut_kind_override))
        self._refresh_lut_class()
        # Switching the display language must not restart Canon or LUT rendering.

    def show_about(self):
        messagebox.showinfo(self.tr('about'),
                            f'{display_name()}\n{self.tr("credit", version=APP_VERSION, author=APP_AUTHOR)}\n\n'
                            '.cube / .xmp → .pf3\n.cube → .xmp\n.xmp → .cube\n.cube / .xmp → LUMIX .cube\n\n' + self.tr('license'))

    def _file_filters(self):
        return [(self.tr('file_filter_lut_xmp'), '*.cube *.xmp'),
                (self.tr('file_filter_cube'), '*.cube'),
                (self.tr('file_filter_xmp'), '*.xmp'),
                (self.tr('file_filter_all'), '*.*')]

    def _photo_filters(self):
        return [(self.tr('file_filter_photos'), patterns(RASTER_EXTENSIONS + RAW_EXTENSIONS)),
                (self.tr('file_filter_canon_raw'), patterns(('.cr2', '.cr3', '.crw'))),
                (self.tr('file_filter_camera_raw'), patterns(RAW_EXTENSIONS)),
                (self.tr('file_filter_raster'), patterns(RASTER_EXTENSIONS)),
                (self.tr('file_filter_all'), '*.*')]

    def _xmp_warnings(self, info):
        """Localize known importer diagnostics without altering source metadata."""
        localized = []
        for note in info.warnings:
            if note.startswith('Adobe XMP profile RGB table is imported;'):
                localized.append(self.tr('xmp_warning_profile'))
            elif note.startswith('Embedded table color-space converted from '):
                localized.append(self.tr('xmp_warning_conversion', space=info.color_space))
            elif note.startswith('Develop preset values are APPROXIMATED'):
                localized.append(self.tr('xmp_warning_preset'))
            elif note.startswith('Scene-aware RAW adjustments'):
                localized.append(self.tr('xmp_warning_scene'))
            elif note.startswith('Referenced camera profile not embedded: '):
                localized.append(self.tr('xmp_warning_camera', profile=note.partition(': ')[2]))
            elif note.startswith('Referenced creative look is not embedded'):
                localized.append(self.tr('xmp_warning_look'))
            elif note.startswith('Unsupported/omitted settings: '):
                localized.append(self.tr('xmp_warning_omitted', items=note.partition(': ')[2]))
            else:
                localized.append(note)  # Keep any future diagnostics visible.
        return '\n\n'.join(localized)

    def open_cube(self):
        filename = filedialog.askopenfilename(filetypes=self._file_filters())
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.lower() == '.cube':
                cube = load_cube(path)
                kind, info = 'cube', None
            elif path.suffix.lower() == '.xmp':
                info = load_xmp(path)
                cube = info.cube
                kind = 'xmp'
            else:
                raise ValueError(self.tr('wrong_extension'))
            self.cube, self.cube_path = cube, path
            if hasattr(self, 'strength_result'):
                del self.strength_result
            self.strength_message.set(self.tr('raw_strength_ready'))
            self.input_kind, self.input_info = kind, info
            # Only RGB table samples are classified; file names and comments
            # never participate in LUT type estimation.
            self.lut_classification = classify_lut(cube) if kind == 'cube' else None
            self.lut_kind_override = 'auto'
            self.lut_kind_selection.set(self.tr('lut_class_override_auto'))
            self._refresh_lut_class()
            self.name.set(path.stem[:31])
            self.strength.set(50)
            self.on_strength()
            self.xmp_button.configure(state='normal' if kind == 'cube' else 'disabled')
            # Status must remain localized even after switching languages.
            self._show_loaded_status()
            self.update_preview()
            if info is not None and info.warnings:
                messagebox.showwarning(self.tr('xmp_warning_title'), self._xmp_warnings(info))
        except Exception as error:
            messagebox.showerror(self.tr('read_error'), str(error))

    def _show_loaded_status(self):
        if self.cube is None or self.cube_path is None:
            return
        cube, path, info = self.cube, self.cube_path, self.input_info
        if self.input_kind == 'cube':
            self._set_dynamic(self.status, 'cube_loaded', name=path.name, size=cube.size,
                              count=cube.size ** 3, domain_min=cube.domain_min.tolist(),
                              domain_max=cube.domain_max.tolist())
        else:
            typ = self.tr('xmp_profile' if info.kind == 'profile' else 'xmp_preset')
            # Use a localized category string; refresh it on language changes.
            label = self.tr('xmp_loaded', name=path.name, kind=typ, size=cube.size)
            if info.ignored:
                label += self.tr('ignored_settings', items=', '.join(info.ignored[:7]))
            self.status.set(label)
            self._dynamic.pop(str(self.status), None)

    def on_destroy(self, event):
        if event.widget is self.root:
            self.closed = True
            if self.photo_timer:
                self.root.after_cancel(self.photo_timer)
            for timer in (self.native_timer, self.native_poll_timer):
                if timer:
                    self.root.after_cancel(timer)
            if self.strength_timer:
                self.root.after_cancel(self.strength_timer)
            self.strength_executor.shutdown(wait=False, cancel_futures=True)
            self.native_executor.shutdown(wait=False, cancel_futures=True)
            self.photo_executor.shutdown(wait=False, cancel_futures=True)

    def open_photo(self):
        if self.photo_future is not None:
            return
        filename = filedialog.askopenfilename(filetypes=self._photo_filters())
        if not filename:
            return
        self._set_dynamic(self.photo_status, 'photo_loading', name=Path(filename).name)
        self.photo_button.configure(state='disabled')
        self.opening_filename = filename
        self.photo_future = self.photo_executor.submit(load_photo, filename)
        self.photo_timer = self.root.after(50, self.poll_photo)

    def poll_photo(self):
        self.photo_timer = None
        if self.closed:
            return
        if not self.photo_future.done():
            self.photo_timer = self.root.after(50, self.poll_photo)
            return
        future, self.photo_future = self.photo_future, None
        self.photo_button.configure(state='normal')
        try:
            photo, note = future.result()
            self.photo = self.source_photo = photo
            suffix = Path(self.opening_filename).suffix.lower()
            self.raw_path = self.opening_filename if suffix in ('.cr2', '.cr3', '.crw') else None
            if suffix in RAW_EXTENSIONS:
                self.photo_note = self.tr('raw_photo_note', name=Path(self.opening_filename).name)
                self._set_dynamic(self.photo_status, 'raw_photo_note', name=Path(self.opening_filename).name)
            else:
                self.photo_note = note
                self.photo_status.set(note)
                self._dynamic.pop(str(self.photo_status), None)
            self.update_preview()
        except Exception as error:
            self._set_dynamic(self.photo_status, 'photo_load_failed')
            messagebox.showerror(self.tr('photo_error'), str(error))

    def start_raw_strength(self):
        # The RAW optimizer is intended for Creative / uncertain looks only.
        # A technical Log/gamut transform cannot be repaired by attenuation.
        if self.cube is None:
            messagebox.showwarning(self.tr('lut_required_title'), self.tr('lut_required'))
            return
        if self.strength_future is not None:
            return
        # No technical-LUT warning or PF3 export block. Simply reserve RAW
        # safety optimisation for creative/uncertain LUTs, unless user has
        # explicitly corrected the estimated type with the override control.
        if self._effective_lut_kind() in ('technical', 'hybrid'):
            self.strength_message.set(self.tr('lut_class_raw_unavailable'))
            return
        selected = filedialog.askopenfilenames(title=self.tr('raw_strength_select'),
                     filetypes=[(self.tr('file_filter_camera_raw'), patterns(RAW_EXTENSIONS)),
                                (self.tr('file_filter_all'), '*.*')])
        if not selected:
            return
        if not 1 <= len(selected) <= 5 or any(Path(p).suffix.lower() not in RAW_EXTENSIONS for p in selected):
            messagebox.showwarning(self.tr('raw_strength_title'), self.tr('raw_strength_bad_selection'))
            return
        self.strength_paths = tuple(selected)
        self.strength_cube = self.cube
        self.strength_lut_kind = self._effective_lut_kind()
        self.raw_strength_button.configure(state='disabled')
        self.strength_message.set(self.tr('raw_strength_processing', count=len(selected)))
        self.strength_future = self.strength_executor.submit(recommend_strength,
                                                               self.strength_cube, self.strength_paths)
        self.strength_timer = self.root.after(80, self.poll_raw_strength)

    def poll_raw_strength(self):
        self.strength_timer = None
        if self.closed or self.strength_future is None:
            return
        if not self.strength_future.done():
            self.strength_timer = self.root.after(80, self.poll_raw_strength)
            return
        future, self.strength_future = self.strength_future, None
        self._refresh_lut_class()
        try:
            result = future.result()
        except Exception as error:
            self.strength_message.set(self.tr('raw_strength_failed'))
            messagebox.showerror(self.tr('raw_strength_title'),
                                 self.tr('raw_strength_error', error=str(error)))
            return
        # Do not apply a stale recommendation to a different LUT.
        if (self.cube is not self.strength_cube
                or self._effective_lut_kind() != self.strength_lut_kind):
            self.strength_message.set(self.tr('raw_strength_stale'))
            return
        self.strength_result = result
        self.strength.set(result.recommended_percent)
        self.on_strength()
        self.strength_message.set(self.tr('raw_strength_result',
                          percent=result.recommended_percent, count=result.photos))
        summary = self.tr('raw_strength_summary',
                          percent=result.recommended_percent, count=result.photos)
        if not result.minimum_passed:
            summary += '\n\n' + self.tr('raw_strength_floor_warning')
        summary += '\n\n' + self.tr('raw_strength_caveat')
        messagebox.showinfo(self.tr('raw_strength_title'), summary)

    def on_strength(self, _=None):
        self.strength_label.configure(text=f'{self.strength.get():.0f}%')
        self.update_preview()

    def update_preview(self):
        self.native_sequence += 1
        self.native_pending = None
        self.native_report = None
        if self.native_timer:
            self.root.after_cancel(self.native_timer)
            self.native_timer = None
        photo = self.source_photo if self.source_photo is not None else self.photo
        if photo is None:
            return
        if self._is_canon_mode() and self.raw_path and self.cube is not None:
            self._set_dynamic(self.photo_status, 'preview_canon_progress')
            self.native_timer = self.root.after(250, self.prepare_native)
        else:
            self.preview_view.set_titles_keys('preview_source', 'preview_lut_target')
            self.preview_view.set_content(photo, self.cube, self.strength.get()/100)

    def prepare_native(self):
        self.native_timer = None
        try:
            dll = find_canon_library(self.dll_path.get().strip() or None)
            self.native_pending = (self.native_sequence, (self.raw_path, self.cube, self.strength.get()/100,
                                   self.base.get(), str(dll), self.source_photo.size))
            if self.native_poll_timer is None:
                self.poll_native()
        except Exception as error:
            self.preview_view.clear(str(error))
            self._set_dynamic(self.photo_status, 'preview_canon_unavailable')

    def poll_native(self):
        self.native_poll_timer = None
        if self.closed:
            return
        if self.native_future is not None and self.native_future.done():
            sequence = self.native_active_sequence
            future, self.native_future = self.native_future, None
            try:
                original, altered, report = future.result()
                if sequence == self.native_sequence:
                    self.native_report = report
                    self.preview_view.set_titles_keys('preview_canon_base', 'preview_canon_result')
                    self.preview_view.set_pair(original, altered)
                    w, h = self.source_photo.size
                    self._set_dynamic(self.photo_status, 'preview_canon_report',
                                      width=w, height=h, render_w=original.width, render_h=original.height,
                                      mae=report['native_rgb_mae_255'], p95=report['native_rgb_p95_255'])
            except Exception as error:
                if sequence == self.native_sequence:
                    self.preview_view.clear(self.tr('preview_canon_failed', error=str(error)))
                    self._set_dynamic(self.photo_status, 'preview_failed')
        if self.native_future is None and self.native_pending is not None:
            self.native_active_sequence, args = self.native_pending
            self.native_pending = None
            self.native_future = self.native_executor.submit(render_pair, *args)
        if self.native_future is not None or self.native_pending is not None:
            self.native_poll_timer = self.root.after(50, self.poll_native)

    def resample(self):
        if self.cube is None:
            messagebox.showwarning(self.tr('lut_required_title'), self.tr('lut_required'))
            return
        filename = filedialog.asksaveasfilename(defaultextension='.cube',
            initialfile=f'{self.cube_path.stem}_33.cube', filetypes=[(self.tr('file_filter_cube'), '*.cube')])
        if not filename:
            return
        try:
            if self.cube_path is not None and Path(filename).resolve() == self.cube_path.resolve():
                raise ValueError(self.tr('lumix_no_overwrite'))
            info = export_srgb_cube(self.cube, filename, strength=self.strength.get()/100,
                title=self.name.get().strip() or self.cube_path.stem)
            messagebox.showinfo(self.tr('save_success'),
                self.tr('save_cube_success', path=filename) + '\n' +
                self.tr('save_cube_strength_note', strength=round(info['strength']*100)))
        except Exception as error:
            messagebox.showerror(self.tr('save_failure'), str(error))

    def save_lumix(self):
        if self.cube is None or self.cube_path is None:
            messagebox.showwarning(self.tr('lut_required_title'), self.tr('lut_required'))
            return
        source = self.cube_path
        default_name = ''.join(ch if ch.isascii() and (ch.isalnum() or ch in '-_') else '_'
                               for ch in source.stem)[:32].strip('_') or 'PB_LUT'
        target = filedialog.asksaveasfilename(defaultextension='.cube',
            initialfile=f'{default_name}_LUMIX.cube',
            filetypes=[(self.tr('file_filter_cube'), '*.cube')])
        if not target:
            return
        if Path(target).resolve() == source.resolve():
            messagebox.showerror(self.tr('save_failure'), self.tr('lumix_no_overwrite'))
            return
        try:
            self.root.configure(cursor='watch')
            self.root.update_idletasks()
            info = export_lumix_cube(
                self.cube, target,
                style=self.lumix_style.get(),
                strength=self.strength.get()/100,
                title=self.name.get().strip() or source.stem)
            extra = self.tr('lumix_source_preset') if self.input_kind == 'xmp' and self.input_info.kind == 'preset' else ''
            messagebox.showinfo(self.tr('lumix_saved_title'),
                self.tr('lumix_saved_body', path=info['file'], style=info['style'],
                        strength=round(info['strength']*100),
                        clipped=info['clamped_component_fraction']*100) + extra)
        except Exception as error:
            messagebox.showerror(self.tr('save_failure'), str(error))
        finally:
            self.root.configure(cursor='')

    def save_xmp(self):
        if self.cube is None or self.cube_path is None or self.input_kind != 'cube':
            messagebox.showwarning(self.tr('cube_required_title'), self.tr('cube_required'))
            return
        target = filedialog.asksaveasfilename(defaultextension='.xmp',
            initialfile=f'{self.cube_path.stem}.xmp', filetypes=[(self.tr('file_filter_xmp'), '*.xmp')])
        if not target:
            return
        try:
            self.root.configure(cursor='watch')
            self.root.update_idletasks()
            info = export_xmp(self.cube, target, name=self.name.get().strip() or self.cube_path.stem)
            self._set_dynamic(self.status, 'xmp_saved_status', size=info['size'], path=info['file'])
            warnings = '\n'.join([self.tr('xmp_export_warning_import'),
                                  self.tr('xmp_export_warning_srgb'), self.tr('xmp_export_warning_resample')])
            messagebox.showinfo(self.tr('xmp_saved_title'),
                                self.tr('xmp_saved_body', path=info['file'], mae=info['resample_mae_255'],
                                        warnings=warnings))
        except Exception as error:
            messagebox.showerror(self.tr('xmp_failed'), str(error))
        finally:
            self.root.configure(cursor='')

    def pick_dll(self):
        if sys.platform == 'darwin':
            # PictureStyleEditor.app is a folder; find_canon_library looks inside it.
            filename = filedialog.askdirectory(title=self.tr('dll_dialog_title'),
                        initialdir='/Applications/Canon Utilities/Picture Style Editor')
        else:
            filename = filedialog.askopenfilename(title=self.tr('dll_dialog_title'),
                        filetypes=[('Canon PF3 Library', 'EdsCFParse.dll'), ('DLL', '*.dll')])
        if filename:
            self.dll_path.set(filename)

    def check_dll(self):
        try:
            found = find_canon_library(self.dll_path.get().strip() or None)
            messagebox.showinfo(self.tr('dll_found'), str(found))
        except Exception as error:
            messagebox.showerror(self.tr('dll_not_found'), str(error))

    def save_pf3(self):
        if self.cube is None or self.cube_path is None:
            messagebox.showwarning(self.tr('lut_required_title'), self.tr('lut_required'))
            return
        if sys.platform not in ('win32', 'darwin'):
            messagebox.showerror(self.tr('os_unsupported'), self.tr('pf3_windows_only'))
            return
        target = filedialog.asksaveasfilename(defaultextension='.pf3',
            initialfile=f'{self.cube_path.stem}.pf3', filetypes=[('Canon Picture Style', '*.pf3')])
        if not target:
            return
        try:
            self.root.configure(cursor='watch')
            self.root.update_idletasks()
            info = export_pf3(self.cube, target,
                  name=self.name.get().strip() or self.cube_path.stem,
                  dll=self.dll_path.get().strip() or None,
                  base=self.base.get(), strength=self.strength.get()/100)
            mae = info['fit']['estimated_rgb_mae_255']
            self._set_dynamic(self.status, 'pf3_saved_status', mae=mae, path=info['file'])
            note = self.tr('pf3_xmp_caveat') if self.input_kind == 'xmp' else ''
            messagebox.showinfo(self.tr('pf3_saved_title'),
                self.tr('pf3_saved_body', path=info['file'], bytes=info['bytes'],
                        sha=info['sha256'][:20], mae=mae, xmp_note=note))
        except Exception as error:
            messagebox.showerror(self.tr('pf3_failed'), self.tr('pf3_failure_hint', error=str(error)))
        finally:
            self.root.configure(cursor='')


def main():
    # Prevent Windows bitmap scaling of high-resolution previews.
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--canon-render-worker':
        from canon_render import render_worker
        render_worker(sys.argv[2])
    else:
        main()
