#!/usr/bin/env python3
"""Android webcam UI; --desktop opens the Windows/Linux LAN camera prototype."""
import sys

# Dispatch before importing the legacy Linux service modules.
if __name__ == '__main__' and (sys.platform == 'win32' or '--desktop' in sys.argv):
    from desktop_camera import main
    sys.exit(main())

import queue
from pathlib import Path
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageOps, ImageTk

import backend as api
import controller
import preferences
import phone_screen
from preview import Reader
import wireless
from stream_service import runtime_dir

BG = '#1c1c1b'
SURFACE = '#242423'
TEXT = '#eeeeec'
MUTED = '#b0b0ad'
BORDER = '#3d3d3a'
ACCENT = '#a14b45'
ACCENT_HOVER = '#b35851'
SELECTED = '#2e2e2c'
SUCCESS = '#b0b0ad'
ERROR = '#d68a82'
FONT = 'Sans'


def label(parent, text='', size=10, color=TEXT, bold=False, **kwargs):
    return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                    font=(FONT, size, 'bold' if bold else 'normal'), **kwargs)


class Button(tk.Canvas):
    def __init__(self, parent, text, command, width=120, primary=False, height=32):
        super().__init__(parent, width=width, height=height, bg=parent.cget('bg'),
                         bd=0, highlightthickness=0, takefocus=1, cursor='hand2')
        self.text, self.command, self.primary = text, command, primary
        self.enabled, self.selected, self.hover = True, False, False
        self.bind('<Enter>', lambda _: self.set_hover(True))
        self.bind('<Leave>', lambda _: self.set_hover(False))
        self.bind('<FocusIn>', lambda _: self.draw())
        self.bind('<FocusOut>', lambda _: self.draw())
        self.bind('<Button-1>', self.invoke)
        self.bind('<Return>', self.invoke)
        self.bind('<space>', self.invoke)
        self.bind('<Configure>', lambda _: self.draw())

    def invoke(self, _=None):
        if self.enabled:
            self.focus_set()
            self.command()
        return 'break'

    def set_hover(self, value):
        self.hover = value
        self.draw()

    def set(self, text=None, enabled=None, selected=None):
        if text is not None: self.text = text
        if enabled is not None: self.enabled = enabled
        if selected is not None: self.selected = selected
        self.configure(cursor='hand2' if self.enabled else 'arrow', takefocus=int(self.enabled))
        self.draw()

    def draw(self):
        self.delete('all')
        w, h = max(2, self.winfo_width()), max(2, self.winfo_height())
        fill = ACCENT if self.primary else SELECTED if self.selected else SURFACE
        ink = TEXT
        stroke = ACCENT if self.selected else BORDER
        if self.hover and self.enabled: fill = ACCENT_HOVER if self.primary else SELECTED
        if not self.enabled: fill, ink, stroke = BG, MUTED, BORDER
        if self.primary and self.enabled: stroke = fill
        if self.focus_get() == self: stroke = TEXT
        self.create_rectangle(1, 1, w-1, h-1, fill=fill, outline=stroke, width=1)
        self.create_text(w/2, h/2, text=self.text, fill=ink, font=(FONT, 10))



class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = self.scanning = self.closed = False
        self.running = self.want_running = False
        self.records, self.capabilities, self.dialogs, self.log_lines = [], {}, {}, []
        self.frame_image = self.photo = None
        self.frame_stamp = self.last_frame = 0
        self.preview_count = 0
        self.reader = Reader()
        self.live_item = None
        self.preview_rate = 0
        self.rate_started = time.monotonic()
        self.rate_frames = 0
        self.next_retry = 0
        self.retry_interval = 5
        self.pending_settings = None
        self.expected_camera = None
        self.scan_generation = 0
        saved = preferences.load()
        existing = controller.current()
        self.mode = tk.StringVar(value=saved['mode'] if saved['mode'] in ('usb', 'wifi') else 'usb')
        self.serial = tk.StringVar(value=saved['last_device'])
        self.facing = tk.StringVar(value=saved['facing'] if saved['facing'] in ('back','front') else 'back')
        self.size = tk.StringVar(value=saved['size'] if saved['size'] in ('1920x1080','1280x720') else '1920x1080')
        self.fps = tk.StringVar(value='30')
        self.auto_connect = tk.BooleanVar(value=bool(saved['auto_connect']))
        self.screen_off = bool(saved['screen_off'])
        if existing:
            self.serial.set(existing['serial'])
            self.mode.set('wifi' if ':' in existing['serial'] or '._tcp' in existing['serial'] else 'usb')
            self.facing.set(existing['facing']); self.size.set(existing['size'])
            self.want_running = True
            self.expected_camera = self.hardware_key(existing['serial'])
        self.quality = tk.StringVar(value='Full HD · 1080p' if self.size.get()=='1920x1080' else 'Ringan · 720p')
        self.status = tk.StringVar(value='Mencari HP yang terhubung…')
        self.wizard_status = tk.StringVar(value='')
        self.pair_address, self.pair_code, self.address = (tk.StringVar() for _ in range(3))
        root.title('Camera Mirror')
        root.geometry('1040x640')
        root.minsize(800, 520)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.option_add('*TCombobox*Listbox.background', SURFACE)
        root.option_add('*TCombobox*Listbox.foreground', TEXT)
        root.option_add('*TCombobox*Listbox.selectBackground', SELECTED)
        root.option_add('*TCombobox*Listbox.selectForeground', TEXT)
        style = ttk.Style(); style.theme_use('clam')
        style.configure('TCombobox', fieldbackground=SURFACE, background=SURFACE, foreground=TEXT,
                        arrowcolor=MUTED, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=6, font=(FONT,10))
        style.map('TCombobox', fieldbackground=[('readonly',SURFACE)], foreground=[('readonly',TEXT)],
                  selectbackground=[('readonly',SURFACE)], selectforeground=[('readonly',TEXT)])
        outer = tk.Frame(root, bg=BG, padx=16, pady=16)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        header = tk.Frame(outer, bg=BG)
        header.grid(row=0, column=0, sticky='ew', pady=(0,16))
        label(header, 'Camera Mirror', 12, bold=True).pack(side='left')
        label(header, ' /  Kamera HP Android', 10, MUTED).pack(side='left', padx=(8,0))
        Button(header, 'Bantuan', self.help, 80).pack(side='right')
        Button(header, 'Kamera komputer', self.open_desktop, 144).pack(side='right', padx=(0,8))

        content = tk.Frame(outer, bg=BG)
        content.grid(row=1, column=0, sticky='nsew')
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        side = tk.Frame(content, bg=SURFACE, padx=12, pady=12)
        side.grid(row=0, column=0, sticky='ns', padx=(0,16))
        label(side, 'Koneksi', 10, MUTED).pack(anchor='w', pady=(0,8))
        row = tk.Frame(side, bg=SURFACE)
        row.pack(fill='x')
        self.usb = Button(row, 'Kabel USB', lambda:self.change_mode('usb'), 108)
        self.wifi = Button(row, 'Wi-Fi', lambda:self.change_mode('wifi'), 108)
        self.usb.pack(side='left', padx=(0,4))
        self.wifi.pack(side='left')
        device = tk.Frame(side, bg=SURFACE, pady=8)
        device.pack(fill='x')
        self.device_title = label(device, 'Mencari HP…', 10, anchor='w', wraplength=216)
        self.device_title.pack(fill='x')
        self.device_hint = label(device, 'Sambungkan kabel USB.', 9, MUTED,
                                 wraplength=216, justify='left', anchor='w')
        self.device_hint.pack(fill='x', pady=(4,0))
        self.connection_button = Button(side, 'Hubungkan HP', self.connection_action, 220)
        self.connection_button.pack(fill='x', pady=(0,8))
        self.separator(side)
        label(side, 'Kamera', 10, MUTED).pack(anchor='w', pady=(8,8))
        row = tk.Frame(side, bg=SURFACE)
        row.pack(fill='x')
        self.front = Button(row, 'Depan', lambda:self.change_facing('front'), 108)
        self.back = Button(row, 'Belakang', lambda:self.change_facing('back'), 108)
        self.front.pack(side='left', padx=(0,4))
        self.back.pack(side='left')
        label(side, 'Kualitas gambar', 10, MUTED).pack(anchor='w', pady=(8,8))
        self.quality_select = ttk.Combobox(side, textvariable=self.quality,
            values=('Ringan · 720p','Full HD · 1080p'), state='readonly', width=20)
        self.quality_select.pack(fill='x')
        self.quality_select.bind('<<ComboboxSelected>>',self.change_quality)
        self.fps_hint = label(side, '30 fps · otomatis', 9, MUTED, anchor='w')
        self.fps_hint.pack(fill='x', pady=(8,0))
        tk.Frame(side, bg=SURFACE, height=16).pack(fill='x', expand=True)

        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=1, sticky='nsew')
        preview_header = tk.Frame(right, bg=BG)
        preview_header.pack(fill='x', pady=(0,12))
        label(preview_header, 'Pratinjau', 10).pack(side='left')
        self.badge = label(preview_header, 'Kamera belum aktif', 9, MUTED)
        self.badge.pack(side='right')
        self.canvas = tk.Canvas(right, bg=BG, highlightbackground=BORDER,
                                highlightthickness=1, height=180, width=1)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', self.resize_preview)
        meta = tk.Frame(right, bg=BG)
        meta.pack(fill='x', pady=(8,12))
        self.preview_info = label(meta, 'Preview otomatis saat kamera aktif.', 9, MUTED,
                                  wraplength=220, justify='left')
        self.preview_info.pack(side='left')
        self.screen_button = Button(meta, 'Padamkan layar HP', self.toggle_screen, 164)
        self.screen_button.pack(side='right', padx=(8,0))
        self.separator(right)
        self.state_title = label(right, 'Menunggu HP', 10)
        self.state_title.pack(anchor='w', pady=(12,4))
        self.notice = label(right, textvariable=self.status, size=9, color=MUTED,
                            wraplength=440, justify='left', anchor='w')
        self.notice.pack(fill='x')
        right.bind('<Configure>', lambda e:self.notice.configure(wraplength=max(200,e.width)))

        footer = tk.Frame(outer, bg=BG)
        footer.grid(row=2, column=0, sticky='ew', pady=(16,0))
        self.main_button = Button(footer, 'Mulai kamera', self.toggle, 164, True)
        self.main_button.pack(side='right', padx=(16,0))
        Button(footer, 'Pengaturan lanjutan', self.settings, 172).pack(side='right', padx=(8,0))
        label(footer, 'Output  /  Android Webcam', 9, MUTED).pack(anchor='w')
        label(footer, 'Menutup panel membiarkan kamera berjalan.', 9, MUTED).pack(anchor='w', pady=(4,0))
        self.root.after(50,self.drain)
        self.root.after(16,self.preview_tick)
        self.scan()
        self.root.after(4000,self.periodic)
        self.update_ui()

    def open_desktop(self):
        root = Path(__file__).resolve().parent
        environment = root / '.venv' / 'bin' / 'python'
        executable = str(environment) if environment.exists() else sys.executable
        subprocess.Popen([executable, str(root/'desktop_camera.py')], cwd=str(root))

    def separator(self,parent):
        tk.Frame(parent,bg=BORDER,height=1).pack(fill='x')

    def emit(self,kind,value): self.events.put((kind,value))

    def selected(self):
        return next((d for d in self.records if d['serial']==self.serial.get() and d['mode']==self.mode.get()),None)

    def choose_device(self):
        candidates=[d for d in self.records if d['mode']==self.mode.get()]
        if self.selected(): return
        if self.want_running and self.expected_camera:
            candidates=[d for d in candidates if self.hardware_key(d['serial'])==self.expected_camera]
        self.serial.set(candidates[0]['serial'] if candidates else '')

    def hardware_key(self,serial):
        return next((d['serial'] for d in preferences.load()['wireless']
                     if d.get('address')==serial and d.get('serial')),serial)

    def save(self):
        preferences.save(mode=self.mode.get(),facing=self.facing.get(),size=self.size.get(),
                         fps=self.fps.get(),auto_connect=self.auto_connect.get(),last_device=self.serial.get())

    def work(self,fn,message,success=None):
        if self.busy:return
        self.busy=True;self.scan_generation+=1
        self.status.set(message);self.wizard_status.set(message);self.notice.configure(fg=MUTED)
        self.update_ui()
        def worker():
            try:
                value=fn()
                if success:self.emit('success',(success,value))
            except Exception as exc:self.emit('error',str(exc))
            finally:
                try:self.emit('running',api.active())
                except Exception:pass
                self.emit('done',None)
        threading.Thread(target=worker,daemon=True).start()

    def scan(self,force=False):
        if self.scanning or self.busy:return
        self.scanning=True
        generation=self.scan_generation
        mode=self.mode.get()
        cached=dict(self.capabilities)
        def worker():
            try:
                records=api.device_details()
                if mode=='wifi' and not any(d['mode']=='wifi' for d in records):
                    if wireless.reconnect(records):records=api.device_details()
                modes={}
                for d in records:
                    if d['serial'] not in cached or force:
                        try:modes[d['serial']]=api.camera_modes(d['serial'])
                        except Exception:pass
                active=api.active()
                self.emit('snapshot',(generation,records,modes,active))
            except Exception as exc:
                self.emit('scan_error',str(exc))
            finally:self.emit('scanned',None)
        threading.Thread(target=worker,daemon=True).start()

    def periodic(self):
        self.scan()
        if not self.closed:self.root.after(4000,self.periodic)

    def drain(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=='snapshot':
                generation,records,modes,running=value
                if generation==self.scan_generation and not self.busy:
                    self.records=records;self.capabilities.update(modes);self.choose_device()
                    if self.running and not running and self.want_running:
                        self.status.set('Koneksi terputus. Mencoba menyambungkan ulang…')
                    self.set_running(running)
                    if self.status.get() == 'Mencari HP yang terhubung…':
                        self.status.set('Siap dipakai di OBS, browser, dan panggilan video.' if running else
                                        'HP terhubung. Klik Mulai kamera.' if self.selected() else 'Sambungkan HP untuk memulai.')
                    if self.want_running and not running and self.selected() and time.monotonic()>self.next_retry:
                        self.next_retry=time.monotonic()+self.retry_interval
                        self.retry_interval=min(60,self.retry_interval*2)
                        self.start()
            elif kind=='scanned':self.scanning=False
            elif kind=='scan_error':self.log_lines.append(value)
            elif kind=='running':self.set_running(value)
            elif kind=='done':self.busy=False
            elif kind=='success':
                callback,result=value;callback(result)
            elif kind=='error':
                self.log_lines.append(value)
                self.status.set(value.split('\n')[0]);self.wizard_status.set(value.split('\n')[0]);self.notice.configure(fg=ERROR)
            elif kind=='log':
                widget,output=value
                if widget.winfo_exists():
                    widget.configure(state='normal');widget.insert('end','\n\n'+output);widget.see('end');widget.configure(state='disabled')
            self.update_ui()
        if not self.closed:self.root.after(50,self.drain)

    def set_running(self,running):
        if self.running != running:self.reader.reset()
        self.running=running
        self.reader.enabled=running
        if not running:
            self.frame_image=self.photo=None;self.frame_stamp=self.last_frame=0
            self.render_preview()

    def update_ui(self):
        device=self.selected()
        self.usb.set(enabled=not self.busy,selected=self.mode.get()=='usb')
        self.wifi.set(enabled=not self.busy,selected=self.mode.get()=='wifi')
        self.front.set(enabled=not self.busy,selected=self.facing.get()=='front')
        self.back.set(enabled=not self.busy,selected=self.facing.get()=='back')
        self.quality_select.configure(state='disabled' if self.busy else 'readonly')
        self.connection_button.set(enabled=not self.busy,text='Ganti HP' if device else 'Hubungkan HP' if self.mode.get()=='wifi' else 'Cari HP')
        count=sum(d['mode']==self.mode.get() for d in self.records)
        if device and count==1:
            self.connection_button.pack_forget()
        elif not self.connection_button.winfo_manager():
            self.connection_button.pack(fill='x',pady=(4,8),after=self.device_title.master)
        self.device_title.configure(text=device['name'] if device else 'Belum ada HP')
        if device:
            hint='Terhubung lewat kabel.' if device['mode']=='usb' else 'Terhubung lewat Wi-Fi. Kabel boleh dilepas.'
        else:hint='Pasang kabel dan izinkan USB debugging di HP.' if self.mode.get()=='usb' else 'Siapkan sekali, lalu sambungkan otomatis.'
        self.device_hint.configure(text=hint)
        self.main_button.set(text='Sebentar…' if self.busy else 'Matikan kamera' if self.running else 'Mulai kamera',
                             enabled=not self.busy and (bool(device) or self.running))
        self.screen_button.set(text='Nyalakan layar HP' if self.screen_off else 'Padamkan layar HP',
                               enabled=self.running and not self.busy)
        live=self.running and time.time()-self.last_frame<2
        self.badge.configure(text='●  Langsung' if live else 'Menghubungkan…' if self.busy else 'Menunggu gambar' if self.running else 'Kamera belum aktif',fg=SUCCESS if live else MUTED)
        self.state_title.configure(text='Menyiapkan kamera…' if self.busy else 'Kamera aktif' if self.running else 'Menunggu HP' if not device else 'Siap digunakan')
        actual=controller.current() if self.running else None
        if actual:
            route='Wi-Fi' if ':' in actual['serial'] else 'USB'
            resolution='1080p' if actual['size']=='1920x1080' else '720p'
            self.preview_info.configure(text=f"{resolution}   ·   {actual['fps']} fps   ·   {route}")
        else:self.preview_info.configure(text='Preview otomatis saat kamera aktif.')

    def toggle_screen(self):
        actual=controller.current()
        if not actual or self.busy:return
        desired=not self.screen_off
        def task():
            if desired:phone_screen.start(actual['serial'])
            else:phone_screen.restore(actual['serial'])
        def success(_):
            self.screen_off=desired
            preferences.save(screen_off=desired)
            self.status.set('Layar padam, kamera tetap aktif. HP tidak dikunci.' if desired else 'Layar HP dinyalakan kembali.')
        self.work(task,'Mengatur layar HP…',success)

    def change_mode(self,mode):
        if self.busy or mode==self.mode.get():return
        self.mode.set(mode);self.choose_device();self.scan_generation+=1;self.save();self.update_ui()
        self.status.set('Pilih Mulai kamera setelah HP terhubung.' if not self.running else 'Kamera saat ini tetap aktif. Perubahan koneksi dipakai saat mulai berikutnya.')
        if self.running and self.selected():
            self.want_running=True
            self.start()
            return
        self.scan()

    def change_facing(self,facing):
        if self.busy or self.facing.get()==facing:return
        self.facing.set(facing);self.settings_changed()

    def change_quality(self,_=None):
        self.size.set('1280x720' if self.quality.get().startswith('Ringan') else '1920x1080')
        self.settings_changed()

    def settings_changed(self):
        self.save();self.update_ui()
        if self.pending_settings:self.root.after_cancel(self.pending_settings)
        if self.running:
            self.status.set('Menerapkan pengaturan kamera…')
            self.pending_settings=self.root.after(450,self.apply_settings)

    def apply_settings(self):
        self.pending_settings=None
        if self.running and not self.busy:self.start()

    def toggle(self):
        if self.running:
            self.want_running=False
            if self.pending_settings:self.root.after_cancel(self.pending_settings);self.pending_settings=None
            self.work(lambda:api.stop(),'Mematikan kamera…',lambda _:self.status.set('Kamera dimatikan. Kamu bisa mulai lagi kapan saja.'))
        else:
            self.want_running=True;self.start()

    def start(self):
        serial,facing,size,fps=self.serial.get(),self.facing.get(),self.size.get(),self.fps.get()
        def success(result):
            self.want_running=True;self.retry_interval=5
            self.expected_camera=self.hardware_key(serial)
            self.save();self.status.set('Siap dipakai di OBS, browser, dan panggilan video.')
        self.work(lambda:controller.start(serial,facing,size,fps),'Menghubungkan kamera HP…',success)

    def preview_tick(self):
        if self.running:
            try:
                stamp,frame,generation=self.reader.frames.get_nowait()
                if generation==self.reader.generation:
                    self.frame_image,self.last_frame=frame,stamp
                    self.preview_count+=1;self.rate_frames+=1;self.render_live()
            except queue.Empty:pass
            if time.time()-self.last_frame>2 and self.frame_image is not None:
                self.frame_image=self.photo=None;self.render_preview()
        now=time.monotonic()
        if now-self.rate_started>=1:
            self.preview_rate=self.rate_frames/(now-self.rate_started)
            self.rate_started=now;self.rate_frames=0;self.update_ui()
        if not self.closed:self.root.after(5,self.preview_tick)

    def resize_preview(self,_=None):
        self.reader.viewport=(max(self.canvas.winfo_width(),1),max(self.canvas.winfo_height(),1))
        self.render_preview()

    def render_live(self):
        if self.frame_image is None:return
        c=self.canvas;w,h=c.winfo_width(),c.winfo_height()
        frame=self.frame_image
        if self.photo is not None and self.live_item is not None and (self.photo.width(),self.photo.height())==frame.size:
            self.photo.paste(frame)
            c.coords(self.live_item,w/2,h/2)
        else:
            c.delete('all');c.configure(bg='#1c1c1b')
            self.photo=ImageTk.PhotoImage(frame)
            self.live_item=c.create_image(w/2,h/2,image=self.photo)

    def render_preview(self):
        c=self.canvas;w,h=max(c.winfo_width(),1),max(c.winfo_height(),1)
        c.delete('all');self.live_item=None
        if self.frame_image is not None:
            c.configure(bg='#1c1c1b')
            image=ImageOps.contain(self.frame_image,(w,h),Image.Resampling.BILINEAR)
            self.photo=ImageTk.PhotoImage(image);self.live_item=c.create_image(w/2,h/2,image=self.photo)
        else:
            c.configure(bg=BG)
            x,y=w/2,h/2
            c.create_text(x,y-12,text='Menghubungkan kamera…' if self.busy or self.running else 'Kamera tidak aktif',fill=TEXT,font=(FONT,11))
            c.create_text(x,y+12,text='Menunggu gambar dari HP.' if self.busy or self.running else 'Hubungkan HP, lalu mulai kamera.',fill=MUTED,font=(FONT,9))

    def connection_action(self):
        if self.selected():self.device_picker()
        elif self.mode.get()=='wifi':self.wireless_dialog()
        else:
            self.status.set('Di HP, aktifkan USB debugging dan izinkan komputer ini.');self.scan(force=True)

    def dialog(self,name,title):
        if name in self.dialogs and self.dialogs[name].winfo_exists():self.dialogs[name].lift();return None
        win=tk.Toplevel(self.root,bg=BG);win.title(title);win.transient(self.root);win.resizable(False,False)
        win.geometry(f'+{self.root.winfo_x()+150}+{self.root.winfo_y()+90}')
        win.bind('<Escape>',lambda _:win.destroy());self.dialogs[name]=win
        body=tk.Frame(win,bg=BG,padx=16,pady=16);body.pack(fill='both',expand=True)
        label(body,title,12,bold=True).pack(anchor='w',pady=(0,10))
        return body

    def field(self,parent,title,var,secret=False):
        label(parent,title,9,MUTED).pack(anchor='w',pady=(10,5))
        entry=tk.Entry(parent,textvariable=var,show='•' if secret else '',bg=SURFACE,fg=TEXT,
                       insertbackground=ACCENT,font=(FONT,11),relief='flat',highlightthickness=1,
                       highlightbackground=BORDER,highlightcolor=ACCENT)
        entry.pack(fill='x',ipady=6)
        return entry

    def wireless_dialog(self):
        body=self.dialog('wireless','Hubungkan tanpa kabel')
        if body is None:return
        label(body,'Siapkan sekali. Setelah itu aplikasi akan mencari HP-mu\ndan menyambungkannya kembali secara otomatis.',10,MUTED,justify='left').pack(anchor='w')
        steps=tk.Frame(body,bg=SURFACE,padx=12,pady=12);steps.pack(fill='x',pady=12)
        for number,text in [('1','Hubungkan HP ke Wi-Fi yang sama dengan komputer.'),('2','Pasang kabel USB dan izinkan USB debugging.'),('3','Klik tombol di bawah. Setelah terhubung, lepas kabel.')]:
            row=tk.Frame(steps,bg=SURFACE);row.pack(fill='x',pady=5)
            label(row,number,10,ACCENT,True,width=2).pack(side='left',padx=(0,10))
            label(row,text,10,wraplength=330,justify='left').pack(side='left')
        self.wizard_status.set('Kabel hanya diperlukan untuk penyiapan awal.')
        label(body,textvariable=self.wizard_status,size=10,color=SUCCESS,wraplength=410,justify='left').pack(anchor='w',pady=(0,12))
        self.wifi_setup_button=Button(body,'Hubungkan otomatis',self.setup_wireless,430,True,32)
        self.wifi_setup_button.pack(fill='x')
        Button(body,'Tidak punya kabel USB?',self.pairing_dialog,430).pack(fill='x',pady=(8,0))
        label(body,'Gunakan jaringan pribadi yang kamu percaya.\nSetelah HP restart, penyiapan lewat kabel mungkin perlu diulang.',9,MUTED,justify='left').pack(anchor='w',pady=(14,0))

    def setup_wireless(self):
        if self.busy:return
        candidates=[d for d in self.records if d['mode']=='usb']
        if len(candidates)!=1:
            self.wizard_status.set('Hubungkan satu HP melalui USB, lalu izinkan debugging.');self.scan(force=True);return
        device=candidates[0];was_running=self.running
        def task():
            if api.active():api.stop()
            address=wireless.setup_usb(device)
            if was_running:controller.start(address,self.facing_value,self.size_value,self.fps_value)
            return address
        # Snapshot every Tk value before starting a background worker.
        self.facing_value,self.size_value,self.fps_value=self.facing.get(),self.size.get(),self.fps.get()
        def success(address):
            self.mode.set('wifi');self.serial.set(address)
            self.records=[d for d in self.records if d['serial']!=address]+[dict(device,serial=address,mode='wifi')]
            if device['serial'] in self.capabilities:self.capabilities[address]=self.capabilities[device['serial']]
            self.save();self.status.set('Wi-Fi terhubung. Kabel USB boleh dilepas.')
            self.wizard_status.set('Berhasil. Kabel USB boleh dilepas. Tutup panel ini untuk mulai memakai kamera.')
            if self.dialogs.get('wireless') and self.dialogs['wireless'].winfo_exists():
                self.wifi_setup_button.set(text='Selesai')
                self.wifi_setup_button.command=self.dialogs['wireless'].destroy
        self.work(task,'Menyiapkan koneksi Wi-Fi…',success)

    def pairing_dialog(self):
        body=self.dialog('pairing','Pasangkan dari HP')
        if body is None:return
        label(body,'Di HP: opsi developer → Wireless debugging\n→ Pair device with pairing code.',10,MUTED,justify='left').pack(anchor='w')
        Button(body,'Cari HP di jaringan',self.find_pairing,400).pack(fill='x',pady=12)
        self.field(body,'Alamat pairing (IP:port)',self.pair_address)
        self.field(body,'Kode enam angka dari HP',self.pair_code,True)
        Button(body,'Pasangkan',self.pair,400,True).pack(fill='x',pady=12)
        self.field(body,'Alamat koneksi dari halaman utama Wireless debugging',self.address)
        Button(body,'Hubungkan',self.connect_manual,400).pack(fill='x',pady=12)
        label(body,textvariable=self.wizard_status,size=9,color=SUCCESS,wraplength=390,justify='left').pack(anchor='w')

    def find_pairing(self):
        def success(services):
            if len(services)==1:
                self.pair_address.set(services[0]['address']);self.wizard_status.set('HP ditemukan. Masukkan kode enam angka dari HP.')
            else:self.wizard_status.set('Isi alamat dari HP. Pastikan halaman kode pairing masih terbuka.')
        self.work(lambda:wireless.discover('_adb-tls-pairing._tcp'),'Mencari HP di jaringan…',success)

    def pair(self):
        if self.busy:return
        address,code=self.pair_address.get(),self.pair_code.get();self.pair_code.set('')
        def task():
            result=api.pair(address,code)
            services=wireless.discover()
            host=address.rsplit(':',1)[0]
            found=[s for s in services if s['address'].rsplit(':',1)[0]==host]
            if len(found)==1:
                target=found[0]['address'];serial=wireless.connect_checked(target)
                preferences.remember(serial,target,'HP Android',found[0]['name'])
                return target
            return None
        def success(address):
            if address:self.on_connected(address)
            else:self.wizard_status.set('Pairing berhasil. Isi alamat koneksi dari halaman utama Wireless debugging, lalu Hubungkan.')
        self.work(task,'Memasangkan HP…',success)

    def connect_manual(self):
        address=self.address.get().strip()
        def task():
            serial=wireless.connect_checked(address)
            preferences.remember(serial,address,'HP Android')
            return address
        self.work(task,'Menghubungkan HP…',self.on_connected)

    def on_connected(self,address):
        self.mode.set('wifi');self.serial.set(address)
        self.records=[d for d in self.records if d['serial']!=address]+[dict(serial=address,name='HP Android',mode='wifi')]
        self.save();self.status.set('Wi-Fi terhubung. Klik Mulai kamera.')
        self.wizard_status.set('Berhasil terhubung. Tutup panel ini dan mulai kamera.')

    def device_picker(self):
        body=self.dialog('devices','Pilih HP')
        if body is None:return
        for device in self.records:
            if device['mode']!=self.mode.get():continue
            def choose(device=device):
                self.serial.set(device['serial']);self.save();self.dialogs['devices'].destroy();self.update_ui()
                if self.running:self.start()
                else:self.status.set('HP dipilih. Klik Mulai kamera untuk menggunakannya.')
            Button(body,device['name'],choose,360).pack(fill='x',pady=5)
        if self.mode.get()=='wifi':Button(body,'Hubungkan HP lain',self.wireless_dialog,360).pack(fill='x',pady=(12,0))

    def settings(self):
        body=self.dialog('settings','Pengaturan lanjutan')
        if body is None:return
        tk.Checkbutton(body,text='Sambungkan ulang Wi-Fi secara otomatis',variable=self.auto_connect,command=self.save,
                       bg=BG,fg=TEXT,activebackground=BG,activeforeground=TEXT,selectcolor=SURFACE,highlightcolor=TEXT,font=(FONT,10)).pack(anchor='w',pady=(5,16))
        for title,callback in [('Siapkan perangkat webcam',lambda:self.work(controller.prepare,'Menyiapkan webcam…',lambda _:self.status.set('Perangkat webcam siap.'))),
                               ('Perbaiki deteksi aplikasi',lambda:self.work(controller.rediscover,'Menyegarkan deteksi…',lambda result:self.status.set(result))),
                               ('Log kamera',self.show_logs)]:
            Button(body,title,callback,410).pack(fill='x',pady=5)
        label(body,'Penyiapan meminta izin administrator melalui dialog sistem.\nPerbaikan deteksi bisa memutus audio desktop sesaat.',9,MUTED,justify='left').pack(anchor='w',pady=(12,0))

    def help(self):
        body=self.dialog('help','Mulai dari sini')
        if body is None:return
        text=('1. Hubungkan HP lewat kabel USB atau pilih Wi-Fi.\n\n'
              '2. Pilih kamera depan atau belakang, lalu Mulai kamera.\n\n'
              '3. Di OBS, Zoom, atau browser, pilih Android Webcam.\n\n'
              'Untuk gerakan lebih responsif, gunakan USB dan 720p.\n'
              'Video diatur ke 30 fps secara otomatis.\n\n'
              'Untuk menghemat daya, gunakan Padamkan layar HP.\n'
              'Ini memadamkan panel tanpa mengunci HP.\n\n'
              'Menutup panel tidak mematikan kamera. Gunakan\n'
              'Matikan kamera untuk berhenti.')
        label(body,text,11,justify='left',wraplength=440).pack(anchor='w',pady=(4,16))
        Button(body,'Log kamera',self.show_logs,430).pack(fill='x')

    def show_logs(self):
        body=self.dialog('logs','Log kamera')
        if body is None:return
        text=tk.Text(body,bg=SURFACE,fg=TEXT,relief='flat',width=78,height=22,wrap='word',font=('Monospace',9))
        text.pack(fill='both',expand=True,pady=10);text.insert('end','\n\n'.join(self.log_lines));text.configure(state='disabled')
        def worker():
            try:output=api.logs()
            except Exception as exc:output=str(exc)
            self.emit('log',(text,output))
        threading.Thread(target=worker,daemon=True).start()

    def close(self):
        if self.busy:self.status.set('Tunggu proses selesai sebelum menutup panel.');return
        self.closed=True;self.reader.close();self.save();self.root.destroy()


def main():
    root=tk.Tk();App(root);root.mainloop()


if __name__=='__main__':main()
