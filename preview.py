"""Synchronized, native-resolution comparison viewer. No Canon DLL needed."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk
import numpy as np
from PIL import Image, ImageTk
from lut import apply_cube
from i18n import tr as localize


def viewport_box(size, viewport, zoom, center):
    """Return a clamped source box and destination size, shared by both panes."""
    iw, ih = size
    vw, vh = viewport
    sw, sh = min(iw, vw / zoom), min(ih, vh / zoom)
    x = max(0, min(iw - sw, center[0] - sw / 2))
    y = max(0, min(ih - sh, center[1] - sh / 2))
    return (x, y, x + sw, y + sh), (max(1, round(sw * zoom)), max(1, round(sh * zoom)))


class Renderer:
    """Worker-owned LRU, limited to 64 MiB of RGB image data."""
    def __init__(self):
        self.cache = OrderedDict()
        self.bytes = 0
        self.limit = 64 * 1024 * 1024

    def render(self, photo, cube, strength, revision, box, size, comparison=None):
        key = (revision, strength, box, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        original = photo.resize(size, Image.Resampling.LANCZOS, box=box)
        altered = comparison.resize(size, Image.Resampling.LANCZOS, box=box) if comparison is not None else original.copy()
        if comparison is None and cube is not None and strength > 0:
            # Bounded row chunks avoid full-photo float arrays and interpolation temporaries.
            for y in range(0, size[1], 128):
                end = min(size[1], y + 128)
                rgb = np.asarray(original.crop((0, y, size[0], end)), dtype=np.float32) / 255
                mapped = np.clip(apply_cube(cube, rgb), 0, 1)
                result = rgb * (1 - strength) + mapped * strength
                altered.paste(Image.fromarray(np.round(result * 255).astype('uint8')), (0, y))
        pair = (original, altered)
        cost = size[0] * size[1] * 6
        if cost <= self.limit:
            while self.cache and self.bytes + cost > self.limit:
                _, old = self.cache.popitem(last=False)
                self.bytes -= old[0].width * old[0].height * 6
            self.cache[key] = pair
            self.bytes += cost
        return pair


class ComparisonView(ttk.Frame):
    def __init__(self, master, translator=None):
        super().__init__(master)
        self._translate = translator or (lambda key, **args: localize('ko', key, **args))
        self._title_keys = ('viewer_original', 'viewer_look')
        self._info_key = 'viewer_no_photo'
        self._info_values = {}
        self.photo = self.cube = self.comparison = None
        self.strength = 1.0
        self.revision = 0
        self.zoom = 1.0
        self.fit = True
        self.center = (0, 0)
        self.sequence = 0
        self.pending = self.future = None
        self.timer = None
        self.closed = False
        self.renderer = Renderer()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='preview')
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        for label, action in [(self._translate('fit'), self.fit_view), ('100%', lambda: self.set_zoom(1)),
                              ('−', lambda: self.set_zoom(self.zoom / 1.25)),
                              ('+', lambda: self.set_zoom(self.zoom * 1.25))]:
            button = ttk.Button(bar, text=label, command=action)
            button.pack(side='left')
            if action == self.fit_view:
                self.fit_button = button
        self.info = tk.StringVar(value=self._translate('viewer_no_photo'))
        ttk.Label(bar, textvariable=self.info).pack(side='left', padx=10)
        panes = ttk.Frame(self)
        panes.pack(fill='both', expand=True)
        self.canvases = []
        self.titles = []
        for title in (self._translate('viewer_original'), self._translate('viewer_look')):
            frame = ttk.Frame(panes)
            frame.pack(side='left', fill='both', expand=True)
            label = ttk.Label(frame, text=title, anchor='center')
            label.pack(fill='x')
            self.titles.append(label)
            canvas = tk.Canvas(frame, background='#202124', highlightthickness=0, width=1, height=1)
            canvas.pack(fill='both', expand=True)
            canvas.bind('<Configure>', lambda e: self.request())
            canvas.bind('<MouseWheel>', self.wheel)
            canvas.bind('<ButtonPress-1>', self.start_pan)
            canvas.bind('<B1-Motion>', self.pan)
            canvas.bind('<Double-Button-1>', lambda e: self.fit_view())
            self.canvases.append(canvas)
        self.bind('<Destroy>', self.destroyed, add='+')
        self.poll_timer = self.after(30, self.poll)

    def destroyed(self, event):
        if event.widget is self:
            self.closed = True
            for timer in (self.timer, self.poll_timer):
                if timer:
                    self.after_cancel(timer)
            self.executor.shutdown(wait=False, cancel_futures=True)

    def set_content(self, photo, cube, strength):
        self.comparison = None
        changed_photo = photo is not self.photo
        self.photo, self.cube, self.strength = photo, cube, strength
        self.revision += 1
        if changed_photo and photo is not None:
            self.center = (photo.width / 2, photo.height / 2)
            self.fit = True
        self.request()

    def set_pair(self, original, altered):
        if original.size != altered.size:
            raise ValueError('Comparison frames must have equal dimensions')
        preserve = self.photo is not None and self.photo.size == original.size
        state = (self.fit,self.center,self.zoom)
        self.set_content(original,None,1)
        self.comparison = altered
        if preserve:
            self.fit,self.center,self.zoom = state
        self.request()

    def set_titles(self, left, right):
        self._title_keys = None
        for label, title in zip(self.titles, (left, right)):
            label.configure(text=title)

    def set_titles_keys(self, left_key, right_key):
        self._title_keys = (left_key, right_key)
        for label, key in zip(self.titles, self._title_keys):
            label.configure(text=self._translate(key))

    def _set_info(self, key, **values):
        self._info_key = key
        self._info_values = values
        self.info.set(self._translate(key, **values))

    def refresh_language(self):
        """Update UI text without touching loaded pixels, zoom or worker state."""
        self.fit_button.configure(text=self._translate('fit'))
        if self._title_keys:
            for label, key in zip(self.titles, self._title_keys):
                label.configure(text=self._translate(key))
        if self._info_key:
            self.info.set(self._translate(self._info_key, **self._info_values))

    def clear(self, message):
        self.sequence += 1
        self.pending = None
        if self.timer:
            self.after_cancel(self.timer)
            self.timer = None
        self.photo = self.comparison = None
        for canvas in self.canvases:
            canvas.delete('all')
            canvas.create_text(canvas.winfo_width()/2,canvas.winfo_height()/2,
                               text=message,fill='white',width=max(100,canvas.winfo_width()-30))
        self._info_key = None
        self.info.set(message)

    def fit_view(self):
        self.fit = True
        if self.photo:
            self.center = (self.photo.width / 2, self.photo.height / 2)
        self.request()

    def set_zoom(self, value):
        self.fit = False
        self.zoom = max(.01, min(16, value))
        self.request()

    def wheel(self, event):
        if self.photo is None or not event.delta:
            return
        canvas = event.widget
        old = self.zoom
        new = max(.01, min(16, old * (1.25 if event.delta > 0 else .8)))
        box, size = viewport_box(self.photo.size, self.viewport(), old, self.center)
        # Anchor the source pixel under the pointer while zooming.
        px = event.x - (canvas.winfo_width() - size[0]) / 2
        py = event.y - (canvas.winfo_height() - size[1]) / 2
        source = (box[0] + px / old, box[1] + py / old)
        self.center = (source[0] - (event.x - canvas.winfo_width()/2) / new,
                       source[1] - (event.y - canvas.winfo_height()/2) / new)
        self.set_zoom(new)

    def start_pan(self, event):
        if self.photo is None:
            return
        box, _ = viewport_box(self.photo.size, self.viewport(), self.zoom, self.center)
        self.center = ((box[0]+box[2])/2, (box[1]+box[3])/2)
        self.drag = (event.x, event.y, self.center)

    def pan(self, event):
        if self.photo is None or not hasattr(self, 'drag'):
            return
        x, y, center = self.drag
        self.fit = False
        self.center = (center[0] - (event.x-x)/self.zoom, center[1] - (event.y-y)/self.zoom)
        self.request()

    def viewport(self):
        return (max(1, min(c.winfo_width() for c in self.canvases)),
                max(1, min(c.winfo_height() for c in self.canvases)))

    def request(self):
        self.sequence += 1  # Immediately invalidate any in-flight result.
        self.pending = None
        if self.timer:
            self.after_cancel(self.timer)
        self.timer = self.after(75, self.prepare)

    def prepare(self):
        self.timer = None
        if self.photo is None:
            return
        viewport = self.viewport()
        if self.fit:
            self.zoom = min(viewport[0]/self.photo.width, viewport[1]/self.photo.height)
        box, size = viewport_box(self.photo.size, viewport, self.zoom, self.center)
        self._set_info('viewer_busy', width=self.photo.width, height=self.photo.height, zoom=self.zoom*100)
        self.pending = (self.sequence, (self.photo, self.cube, self.strength, self.revision, box, size, self.comparison))

    def poll(self):
        if self.closed:
            return
        if self.future is not None and self.future.done():
            sequence, future = self.active_sequence, self.future
            self.future = None
            try:
                pair = future.result()
                if sequence == self.sequence:
                    self.images = [ImageTk.PhotoImage(p) for p in pair]
                    for canvas, image in zip(self.canvases, self.images):
                        canvas.delete('all')
                        canvas.create_image(canvas.winfo_width()/2, canvas.winfo_height()/2, image=image)
                    self._set_info('viewer_ready', width=self.photo.width, height=self.photo.height, zoom=self.zoom*100)
            except Exception as error:
                if sequence == self.sequence:
                    self._set_info('viewer_error', error=str(error))
        if self.future is None and self.pending is not None:
            self.active_sequence, args = self.pending
            self.pending = None
            self.future = self.executor.submit(self.renderer.render, *args)
        self.poll_timer = self.after(30, self.poll)
