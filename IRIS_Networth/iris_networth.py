#!/usr/bin/env python3
"""IRIS Networth Calculator v1.2.0"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import json, csv, hashlib, secrets, datetime, shutil
from pathlib import Path

try:
    import matplotlib; matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_OK = True
except: MATPLOTLIB_OK = False

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_OK = True
except: REPORTLAB_OK = False

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_OK = True
except: PIL_OK = False

# ── Constants ──────────────────────────────────────────────────────────────────
APP_NAME, APP_VERSION = "IRIS Networth Calculator", "1.2.0"
DATA_DIR      = Path.home() / ".iris_networth"
USERS_FILE    = DATA_DIR / "users.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
DATA_DIR.mkdir(exist_ok=True)

EXPENSE_CATEGORIES = ["Housing","Utilities","Insurance","Transportation",
    "Food & Dining","Entertainment","Healthcare","Education",
    "Subscriptions","Taxes","Investments","Other"]

INCOME_CATEGORIES = ["Employment","Rental","Investment","Business",
    "Freelance","Government/Benefits","Side Income","Other"]

SECURITY_QUESTIONS = [
    "What is your mother's maiden name?", "What was your first pet's name?",
    "What city were you born in?",        "What is your favorite book?",
    "What was your childhood nickname?",  "What street did you grow up on?",
]
FREQ_OPTIONS = ["Weekly","Bi-Weekly","Monthly","Quarterly","Semi-Annual","Annual"]
FREQ_TO_KEY  = {"Weekly":"weekly","Bi-Weekly":"biweekly","Monthly":"monthly",
                "Quarterly":"quarterly","Semi-Annual":"semiannual","Annual":"annual"}
KEY_TO_LABEL = {v:k for k,v in FREQ_TO_KEY.items()}
MONTHLY_MULT = {"weekly":52/12,"biweekly":26/12,"monthly":1,
                "quarterly":1/3,"semiannual":1/6,"annual":1/12}
ANNUAL_MULT  = {"weekly":52,"biweekly":26,"monthly":12,
                "quarterly":4,"semiannual":2,"annual":1}
MONTH_NAMES  = ["January","February","March","April","May","June",
                "July","August","September","October","November","December"]
MONTH_SHORT  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
DAY_SUFFIXES = {1:"st",2:"nd",3:"rd",**{i:"th" for i in range(4,32)}}

ACCENT, SUCCESS, DANGER, WARNING, GOLD, ACCENT2 = \
    "#6c63ff","#00c896","#ff4757","#ffa502","#f7931a","#00d4ff"
_HOVER = {ACCENT:"#5a52d5",SUCCESS:"#00a878",DANGER:"#cc2233",
           WARNING:"#cc8800",GOLD:"#d4780f",ACCENT2:"#0099cc"}

# ── Helpers ────────────────────────────────────────────────────────────────────
def hash_pw(pw, salt=None):
    if not salt: salt = secrets.token_hex(32)
    return hashlib.pbkdf2_hmac("sha256",pw.encode(),salt.encode(),200_000).hex(), salt

def verify_pw(pw, h, salt): return hash_pw(pw,salt)[0] == h

def fmt(v):
    try: v=float(v); return f"${v:,.2f}" if v>=0 else f"-${abs(v):,.2f}"
    except: return "$0.00"

def day_label(d):
    d=int(d); return f"{d}{DAY_SUFFIXES.get(d,'th')}"

def now_str(): return datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
def ts():      return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def exp_monthly(e):
    if e.get("variable") and e.get("monthly_amounts"):
        ma=e["monthly_amounts"]
        if ma: return sum(float(v) for v in ma.values())/12
    return float(e.get("amount",0))*MONTHLY_MULT.get(e.get("frequency","monthly"),1)

def exp_annual(e):
    if e.get("variable") and e.get("monthly_amounts"):
        ma=e["monthly_amounts"]
        if ma: return sum(float(v) for v in ma.values())
    return float(e.get("amount",0))*ANNUAL_MULT.get(e.get("frequency","monthly"),12)

def amount_for_month(e, month_num):
    """Per-month amount — uses the specific monthly override when set, else monthly equiv."""
    if e.get("variable") and e.get("monthly_amounts"):
        val=e["monthly_amounts"].get(str(month_num))
        if val is not None: return float(val)
    return exp_monthly(e)

def months_for_expense(e):
    freq = e.get("frequency","monthly")
    dm   = max(1, min(12, int(e.get("due_month",1))))
    if freq in ("weekly","biweekly","monthly"): return list(range(1,13))
    if freq == "quarterly":  return sorted(set(((dm-1+i*3)%12)+1 for i in range(4)))
    if freq == "semiannual": return sorted({dm, ((dm-1+6)%12)+1})
    if freq == "annual":     return [dm]
    return list(range(1,13))

def make_avatar(path, size=40):
    if not PIL_OK: return None
    try:
        img  = Image.open(path).convert("RGBA").resize((size,size),Image.LANCZOS)
        mask = Image.new("L",(size,size),0)
        ImageDraw.Draw(mask).ellipse([0,0,size,size],fill=255)
        out  = Image.new("RGBA",(size,size),(0,0,0,0))
        out.paste(img,(0,0),mask)
        return ImageTk.PhotoImage(out)
    except: return None

def load_logo(parent, size=80):
    if PIL_OK:
        for name in ("iris_logo.png","logo.png","iris_logo.jpg"):
            for base in (Path(__file__).parent if "__file__" in dir() else Path("."), Path(".")):
                p = base/name
                if p.exists():
                    try:
                        img = Image.open(p).resize((size,size),Image.LANCZOS)
                        ph  = ImageTk.PhotoImage(img)
                        lbl = ctk.CTkLabel(parent,image=ph,text="")
                        lbl.image = ph; lbl.pack(); return
                    except: pass
    ctk.CTkLabel(parent,text="◈",font=ctk.CTkFont(size=int(size*.75),weight="bold"),
                 text_color=ACCENT).pack()

# ── UI primitives ──────────────────────────────────────────────────────────────
def card(parent,**kw):
    kw.setdefault("fg_color",("#ffffff","#1a1d27")); kw.setdefault("corner_radius",12)
    return ctk.CTkFrame(parent,**kw)

def divider(parent):
    ctk.CTkFrame(parent,height=1,fg_color=("#e2e8f0","#2d3446")).pack(fill="x",padx=15)

def section_lbl(parent,text):
    ctk.CTkLabel(parent,text=text,font=ctk.CTkFont(size=12,weight="bold"),
                 text_color=(ACCENT,"#a09bff")).pack(anchor="w",pady=(12,3))

def abtn(parent,text,cmd,color=ACCENT,height=38,width=None,**kw):
    b = ctk.CTkButton(parent,text=text,command=cmd,fg_color=color,
                      hover_color=_HOVER.get(color,color),height=height,
                      corner_radius=8,font=ctk.CTkFont(size=12,weight="bold"),**kw)
    if width: b.configure(width=width)
    return b

def ghost_btn(parent,text,cmd,height=36,**kw):
    return ctk.CTkButton(parent,text=text,command=cmd,fg_color="transparent",
                         hover_color=("#e2e8f0","#2d3446"),
                         text_color=("#6b7280","#8892a4"),height=height,**kw)

def lbl_entry(parent,label,ph="",secret=False,height=40):
    ctk.CTkLabel(parent,text=label,anchor="w",font=ctk.CTkFont(size=11)).pack(
        fill="x",padx=22,pady=(5,2))
    e = ctk.CTkEntry(parent,placeholder_text=ph,show="•" if secret else "",
                     height=height,corner_radius=8)
    e.pack(fill="x",padx=22,pady=(0,5))
    return e

def initials_avatar(parent, username, size=40):
    """Draw a coloured circle with initials — PIL-free fallback."""
    r = size//2
    f = ctk.CTkFrame(parent, width=size, height=size, fg_color=ACCENT, corner_radius=r)
    f.pack_propagate(False); f.pack()
    ctk.CTkLabel(f, text=username[:2].upper(),
                 font=ctk.CTkFont(size=int(size*.35), weight="bold"),
                 text_color="white").pack(expand=True)
    return f

# ── Data Manager ───────────────────────────────────────────────────────────────
class DataManager:
    def __init__(self, username):
        self.username    = username
        self.user_dir    = DATA_DIR/username
        self.user_dir.mkdir(exist_ok=True)
        self.history_dir = self.user_dir/"history"
        self.history_dir.mkdir(exist_ok=True)
        self.current_file = self.user_dir/"current.json"

    def empty(self):
        return {"net_worth":{"banks":[],"crypto":[],"stocks":[],"assets":[]},
                "expenses":[],"income":[],"goals":[],"last_saved":""}

    def load(self):
        if self.current_file.exists():
            try:
                with open(self.current_file,encoding="utf-8") as f:
                    d = json.load(f)
                    d.setdefault("income",[])   # migrate old files
                    return d
            except: pass
        return self.empty()

    def save(self, data):
        data["last_saved"] = now_str()
        with open(self.current_file,"w",encoding="utf-8") as f: json.dump(data,f,indent=2)
        snap = self.history_dir/f"snap_{ts()}.json"
        with open(snap,"w",encoding="utf-8") as f: json.dump(data,f,indent=2)
        return snap.stem

    def history(self):
        out = []
        for p in sorted(self.history_dir.iterdir(),reverse=True):
            if p.suffix==".json":
                try:
                    with open(p,encoding="utf-8") as f: d=json.load(f)
                    out.append({"file":p.name,"path":str(p),"date":d.get("last_saved",p.stem)})
                except: pass
        return out

    def load_snap(self, path):
        with open(path,encoding="utf-8") as f: return json.load(f)

    def avatar_path(self): return self.user_dir/"avatar.png"

# ── User Manager ───────────────────────────────────────────────────────────────
class UserManager:
    def __init__(self):
        self._db = self._load()

    def _load(self):
        if USERS_FILE.exists():
            try:
                with open(USERS_FILE,encoding="utf-8") as f: return json.load(f)
            except: pass
        return {}

    def _save(self):
        with open(USERS_FILE,"w",encoding="utf-8") as f: json.dump(self._db,f,indent=2)

    def register(self,u,pw,email=""):
        if len(u)<3:     return False,"Username must be 3+ characters."
        if len(pw)<6:    return False,"Password must be 6+ characters."
        if u in self._db: return False,"Username already taken."
        h,salt = hash_pw(pw)
        self._db[u]={"hash":h,"salt":salt,"email":email,"created":now_str(),"sq":"","sa":""}
        self._save(); return True,"Account created!"

    def login(self,u,pw):
        d = self._db.get(u)
        if not d: return False,"Invalid credentials."
        return (True,"OK") if verify_pw(pw,d["hash"],d["salt"]) else (False,"Invalid credentials.")

    def change_pw(self,u,old,new):
        ok,_ = self.login(u,old)
        if not ok: return False,"Current password is incorrect."
        if len(new)<6: return False,"New password must be 6+ characters."
        h,salt = hash_pw(new); self._db[u]["hash"]=h; self._db[u]["salt"]=salt
        self._save(); return True,"Password changed."

    def set_sq(self,u,q,a):
        if u in self._db:
            self._db[u]["sq"]=q
            self._db[u]["sa"]=hashlib.sha256(a.strip().lower().encode()).hexdigest()
            self._save()

    def get_sq(self,u): return self._db.get(u,{}).get("sq","")

    def reset_pw(self,u,answer,new_pw):
        d = self._db.get(u)
        if not d: return False,"User not found."
        if not d.get("sa"): return False,"No security question set for this account."
        if hashlib.sha256(answer.strip().lower().encode()).hexdigest()!=d["sa"]:
            return False,"Incorrect answer."
        if len(new_pw)<6: return False,"Password must be 6+ characters."
        h,salt = hash_pw(new_pw); self._db[u]["hash"]=h; self._db[u]["salt"]=salt
        self._save(); return True,"Password reset successfully."

# ── Settings ───────────────────────────────────────────────────────────────────
class SettingsManager:
    def __init__(self):
        self._d = {"theme":"dark"}
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE,encoding="utf-8") as f: self._d=json.load(f)
            except: pass

    def get(self,k,default=None): return self._d.get(k,default)
    def set(self,k,v):
        self._d[k]=v
        with open(SETTINGS_FILE,"w",encoding="utf-8") as f: json.dump(self._d,f,indent=2)

# ── Login Window ───────────────────────────────────────────────────────────────
class LoginWindow(ctk.CTk):
    def __init__(self, um, sm):
        super().__init__()
        self.um=um; self.sm=sm; self.logged_in=None
        ctk.set_appearance_mode(sm.get("theme","dark"))
        ctk.set_default_color_theme("blue")
        self.title(APP_NAME); self.geometry("460x680"); self.resizable(False,False)
        self.update_idletasks()
        x=(self.winfo_screenwidth()-460)//2; y=(self.winfo_screenheight()-680)//2
        self.geometry(f"460x680+{x}+{y}"); self._build()

    def _build(self):
        wrap=ctk.CTkFrame(self,fg_color="transparent")
        wrap.pack(fill="both",expand=True,padx=35,pady=20)
        lf=ctk.CTkFrame(wrap,fg_color="transparent"); lf.pack(pady=(10,5))
        load_logo(lf,72)
        ctk.CTkLabel(wrap,text=APP_NAME,font=ctk.CTkFont(size=20,weight="bold")).pack(pady=(4,2))
        ctk.CTkLabel(wrap,text="Your Personal Finance Hub",font=ctk.CTkFont(size=11),
                     text_color=("#6b7280","#8892a4")).pack(pady=(0,16))
        tb=ctk.CTkFrame(wrap,fg_color=("#e2e8f0","#1a1d27"),corner_radius=10)
        tb.pack(fill="x",pady=(0,16))
        self._tl=ctk.CTkButton(tb,text="Sign In",height=36,corner_radius=8,fg_color=ACCENT,
            hover_color=_HOVER[ACCENT],command=lambda:self._switch("login"))
        self._tl.pack(side="left",fill="x",expand=True,padx=4,pady=4)
        self._tr=ctk.CTkButton(tb,text="Register",height=36,corner_radius=8,fg_color="transparent",
            hover_color=("#d1d5db","#2d3446"),text_color=("#6b7280","#9ca3af"),
            command=lambda:self._switch("register"))
        self._tr.pack(side="left",fill="x",expand=True,padx=4,pady=4)
        self._form=ctk.CTkFrame(wrap,fg_color=("#f9fafb","#1a1d27"),corner_radius=12)
        self._form.pack(fill="both",expand=True); self._build_login()

    def _switch(self,tab):
        if tab=="login":
            self._tl.configure(fg_color=ACCENT,text_color="white")
            self._tr.configure(fg_color="transparent",text_color=("#6b7280","#9ca3af"))
            self._build_login()
        else:
            self._tr.configure(fg_color=ACCENT,text_color="white")
            self._tl.configure(fg_color="transparent",text_color=("#6b7280","#9ca3af"))
            self._build_register()

    def _clear(self):
        for w in self._form.winfo_children(): w.destroy()

    def _build_login(self):
        self._clear(); f=self._form
        ctk.CTkLabel(f,text="Welcome back!",font=ctk.CTkFont(size=15,weight="bold")).pack(pady=(18,4))
        ctk.CTkLabel(f,text="Sign in to continue",font=ctk.CTkFont(size=11),
                     text_color=("#9ca3af","#6b7280")).pack(pady=(0,14))
        self._lu=lbl_entry(f,"Username","Your username")
        self._lp=lbl_entry(f,"Password","Your password",secret=True)
        self._lp.bind("<Return>",lambda _:self._do_login())
        ctk.CTkButton(f,text="Forgot password?",fg_color="transparent",hover=False,
                      text_color=(ACCENT,"#a09bff"),font=ctk.CTkFont(size=11),
                      command=self._forgot).pack(anchor="e",padx=22)
        abtn(f,"Sign In",self._do_login,height=42).pack(fill="x",padx=22,pady=(12,20))

    def _do_login(self):
        ok,msg=self.um.login(self._lu.get().strip(),self._lp.get())
        if ok: self.logged_in=self._lu.get().strip(); self.destroy()
        else: messagebox.showerror("Login Failed",msg,parent=self)

    def _build_register(self):
        self._clear()
        sc=ctk.CTkScrollableFrame(self._form,fg_color="transparent"); sc.pack(fill="both",expand=True)
        ctk.CTkLabel(sc,text="Create Account",font=ctk.CTkFont(size=15,weight="bold")).pack(pady=(18,4))
        ctk.CTkLabel(sc,text="Fill in your details",font=ctk.CTkFont(size=11),
                     text_color=("#9ca3af","#6b7280")).pack(pady=(0,12))
        self._rf={}
        for lbl,ph,sec in [("Username *","3+ characters",False),("Email (optional)","your@email.com",False),
                            ("Password *","6+ characters",True),("Confirm Password *","Repeat",True)]:
            self._rf[lbl]=lbl_entry(sc,lbl,ph,sec)
        ctk.CTkLabel(sc,text="Security Question",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=22,pady=(5,2))
        self._sq=ctk.CTkComboBox(sc,values=SECURITY_QUESTIONS,height=40,corner_radius=8)
        self._sq.set(SECURITY_QUESTIONS[0]); self._sq.pack(fill="x",padx=22,pady=(0,5))
        self._sa=lbl_entry(sc,"Security Answer","Your answer (for password reset)")
        abtn(sc,"Create Account",self._do_register,height=42).pack(fill="x",padx=22,pady=(14,20))

    def _do_register(self):
        u=self._rf["Username *"].get().strip(); e=self._rf["Email (optional)"].get().strip()
        p=self._rf["Password *"].get(); c=self._rf["Confirm Password *"].get()
        if p!=c: messagebox.showerror("Error","Passwords do not match.",parent=self); return
        ok,msg=self.um.register(u,p,e)
        if ok:
            if self._sa.get().strip(): self.um.set_sq(u,self._sq.get(),self._sa.get())
            messagebox.showinfo("Success",f"{msg}\nYou can now sign in.",parent=self)
            self._switch("login")
        else: messagebox.showerror("Error",msg,parent=self)

    def _forgot(self):
        dlg=ctk.CTkToplevel(self); dlg.title("Reset Password")
        dlg.geometry("380x380"); dlg.resizable(False,False); dlg.grab_set()
        ctk.CTkLabel(dlg,text="Reset Password",font=ctk.CTkFont(size=16,weight="bold")).pack(pady=20)
        u_e=lbl_entry(dlg,"Username","Your username")
        q_lbl=ctk.CTkLabel(dlg,text="Enter username to see your security question",
                           wraplength=320,text_color=("#9ca3af","#6b7280"),font=ctk.CTkFont(size=11))
        q_lbl.pack(padx=25,pady=4)
        a_e=lbl_entry(dlg,"Answer","Your security answer")
        np_e=lbl_entry(dlg,"New Password","6+ characters",secret=True)
        def on_key(_=None):
            q=self.um.get_sq(u_e.get().strip())
            q_lbl.configure(text=q if q else "No question found.",
                            text_color=(("#1a1d27","#e5e7eb") if q else ("#9ca3af","#6b7280")))
        u_e.bind("<KeyRelease>",on_key)
        def do():
            ok,msg=self.um.reset_pw(u_e.get().strip(),a_e.get(),np_e.get())
            if ok: messagebox.showinfo("Done",msg,parent=dlg); dlg.destroy()
            else: messagebox.showerror("Error",msg,parent=dlg)
        abtn(dlg,"Reset Password",do,height=42).pack(fill="x",padx=25,pady=12)

# ── Main App ───────────────────────────────────────────────────────────────────
class IRISApp(ctk.CTk):
    def __init__(self, username, sm, um):
        super().__init__()
        self.username=username; self.sm=sm; self.um=um
        self.dm=DataManager(username); self.data=self.dm.load()
        self._avatar_img=None
        ctk.set_appearance_mode(sm.get("theme","dark"))
        self.title(f"{APP_NAME}  —  {username}")
        self.geometry("1300x800"); self.minsize(960,620)
        self.update_idletasks()
        x=(self.winfo_screenwidth()-1300)//2; y=(self.winfo_screenheight()-800)//2
        self.geometry(f"1300x800+{x}+{y}")
        self._build(); self.protocol("WM_DELETE_WINDOW",self._on_close)

    def _build(self):
        self._sb=ctk.CTkFrame(self,width=235,corner_radius=0,fg_color=("#1a1d27","#0d0f18"))
        self._sb.pack(side="left",fill="y"); self._sb.pack_propagate(False)
        self._ct=ctk.CTkFrame(self,corner_radius=0,fg_color=("#f0f2f5","#0f1117"))
        self._ct.pack(side="right",fill="both",expand=True)
        self._nav_btns={}; self._build_sidebar(); self._show("dashboard")

    def _build_sidebar(self):
        sb=self._sb
        # Logo row
        lf=ctk.CTkFrame(sb,fg_color="transparent"); lf.pack(fill="x",padx=14,pady=(18,6))
        logo_placed=False
        if PIL_OK:
            for name in("iris_logo.png","logo.png"):
                for base in(Path(__file__).parent if "__file__" in dir() else Path("."),Path(".")):
                    p=base/name
                    if p.exists():
                        try:
                            img=Image.open(p).resize((32,32),Image.LANCZOS)
                            self._sb_logo=ImageTk.PhotoImage(img)
                            ctk.CTkLabel(lf,image=self._sb_logo,text="").pack(side="left",padx=(0,8))
                            logo_placed=True; break
                        except: pass
                if logo_placed: break
        if not logo_placed:
            ctk.CTkLabel(lf,text="◈",font=ctk.CTkFont(size=24,weight="bold"),
                         text_color=ACCENT).pack(side="left",padx=(0,8))
        ctk.CTkLabel(lf,text="IRIS",font=ctk.CTkFont(size=18,weight="bold"),
                     text_color="#ffffff").pack(side="left")
        ctk.CTkFrame(sb,height=1,fg_color="#2d3446").pack(fill="x",padx=14,pady=8)
        # User chip
        self._user_chip=ctk.CTkFrame(sb,fg_color=("#21253a","#21253a"),corner_radius=10)
        self._user_chip.pack(fill="x",padx=14,pady=(0,14))
        self._render_avatar()
        # Nav
        nw=ctk.CTkFrame(sb,fg_color="transparent"); nw.pack(fill="both",expand=True,padx=10)
        nav_items=[("📊","Dashboard","dashboard"),("💰","Net Worth","networth"),
                   ("💵","Income","income"),("📋","Expenses","expenses"),
                   ("🗓","Calendar","calendar"),("🎯","Goals","goals"),
                   ("📅","History","history"),("⚙️","Settings","settings")]
        self._nav_btns={}
        for icon,label,pid in nav_items:
            b=ctk.CTkButton(nw,text=f"  {icon}   {label}",anchor="w",height=42,corner_radius=8,
                fg_color="transparent",hover_color=("#2d3446","#2d3446"),
                text_color=("#8892a4","#8892a4"),font=ctk.CTkFont(size=13),
                command=lambda p=pid:self._show(p))
            b.pack(fill="x",pady=2); self._nav_btns[pid]=b
        btm=ctk.CTkFrame(sb,fg_color="transparent"); btm.pack(fill="x",padx=10,pady=14,side="bottom")
        abtn(btm,"💾  Save Data",self._save,color=SUCCESS).pack(fill="x",pady=2)
        ghost_btn(btm,"🚪  Logout",self._logout).pack(fill="x",pady=2)

    def _render_avatar(self):
        """Render avatar chip — robust, works with or without PIL/photo."""
        for w in self._user_chip.winfo_children(): w.destroy()
        chip=self._user_chip; ap=self.dm.avatar_path()
        # Left: avatar circle
        av_wrap=ctk.CTkFrame(chip,width=42,height=42,fg_color="transparent")
        av_wrap.pack(side="left",padx=(10,8),pady=10)
        av_wrap.pack_propagate(False)
        placed=False
        if ap.exists() and PIL_OK:
            ph=make_avatar(str(ap),40)
            if ph:
                self._avatar_img=ph   # keep reference on self
                il=ctk.CTkLabel(av_wrap,image=ph,text="",width=40,height=40)
                il.image=ph; il.pack(expand=True); placed=True
        if not placed:
            initials_avatar(av_wrap, self.username, 40)
        # Right: text
        tf=ctk.CTkFrame(chip,fg_color="transparent")
        tf.pack(side="left",fill="both",expand=True,padx=(0,10),pady=4)
        ctk.CTkLabel(tf,text=self.username,font=ctk.CTkFont(size=12,weight="bold"),
                     text_color="#ffffff").pack(anchor="w",pady=(6,0))
        ctk.CTkLabel(tf,text="Personal Finance",font=ctk.CTkFont(size=9),
                     text_color="#8892a4").pack(anchor="w",pady=(0,6))

    def refresh_avatar(self): self._render_avatar()

    def _show(self,pid):
        for k,b in self._nav_btns.items():
            b.configure(fg_color=ACCENT if k==pid else "transparent",
                        text_color="white" if k==pid else ("#8892a4","#8892a4"))
        for w in self._ct.winfo_children(): w.destroy()
        pages={"dashboard":DashboardPage,"networth":NetWorthPage,"expenses":ExpensesPage,
               "income":IncomePage,"calendar":CalendarPage,"goals":GoalsPage,
               "history":HistoryPage,"settings":SettingsPage}
        if pid in pages: pages[pid](self._ct,self).pack(fill="both",expand=True)

    def _save(self):
        stamp=self.dm.save(self.data)
        messagebox.showinfo("Saved",f"Data saved!\nSnapshot: {stamp}",parent=self)

    def _logout(self):
        if messagebox.askyesno("Logout","Save before logging out?",parent=self): self.dm.save(self.data)
        self.destroy(); main()

    def _on_close(self):
        if messagebox.askyesno("Exit","Save before exiting?",parent=self): self.dm.save(self.data)
        self.destroy()

    # ── Calculations ───────────────────────────────────────────────────────────
    def total_net_worth(self):
        nw=self.data.get("net_worth",{})
        return sum(float(i.get("value",0)) for cat in("banks","crypto","stocks","assets") for i in nw.get(cat,[]))

    def monthly_bills_only(self):
        return sum(float(e.get("amount",0)) for e in self.data.get("expenses",[]) if e.get("frequency","monthly")=="monthly")

    def monthly_equiv(self):
        return sum(exp_monthly(e) for e in self.data.get("expenses",[]))

    def annual_total(self):
        return sum(exp_annual(e) for e in self.data.get("expenses",[]))

    def monthly_income(self):
        return sum(exp_monthly(i) for i in self.data.get("income",[]))

    def annual_income(self):
        return sum(exp_annual(i) for i in self.data.get("income",[]))

    def expenses_for_month(self,month_num):
        return [(e,exp_monthly(e)) for e in self.data.get("expenses",[]) if month_num in months_for_expense(e)]

    def income_for_month(self,month_num):
        return [(i,exp_monthly(i)) for i in self.data.get("income",[]) if month_num in months_for_expense(i)]

    def category_totals_nw(self):
        nw=self.data.get("net_worth",{})
        return {"Banks":sum(float(i.get("value",0)) for i in nw.get("banks",[])),
                "Crypto":sum(float(i.get("value",0)) for i in nw.get("crypto",[])),
                "Stocks":sum(float(i.get("value",0)) for i in nw.get("stocks",[])),
                "Assets":sum(float(i.get("value",0)) for i in nw.get("assets",[]))}

    def expense_by_category(self):
        out={}
        for e in self.data.get("expenses",[]): cat=e.get("category","Other"); out[cat]=out.get(cat,0)+exp_monthly(e)
        return out

# ── Shared expense/income edit dialog ─────────────────────────────────────────
def monthly_amounts_dialog(parent_widget, item):
    """Sub-dialog: enter a different amount for each month (Jan–Dec)."""
    dlg=ctk.CTkToplevel(parent_widget); dlg.title(f"Monthly Amounts — {item.get('name','')}")
    dlg.geometry("340x500"); dlg.resizable(False,False); dlg.grab_set()
    dlg.update_idletasks()
    try:
        x=parent_widget.winfo_rootx()+(parent_widget.winfo_width()-340)//2
        y=parent_widget.winfo_rooty()+(parent_widget.winfo_height()-500)//2
        dlg.geometry(f"340x500+{x}+{y}")
    except: pass
    existing=item.get("monthly_amounts",{}); base=str(item.get("amount",0))
    ctk.CTkLabel(dlg,text="Per-Month Amounts",font=ctk.CTkFont(size=15,weight="bold")).pack(pady=(16,2))
    ctk.CTkLabel(dlg,text="Leave blank → uses the default amount",
                 font=ctk.CTkFont(size=11),text_color=("#6b7280","#8892a4")).pack(pady=(0,8))
    sc=ctk.CTkScrollableFrame(dlg,fg_color="transparent"); sc.pack(fill="both",expand=True,padx=16,pady=4)
    entries={}
    for i,mname in enumerate(MONTH_NAMES,1):
        r=ctk.CTkFrame(sc,fg_color="transparent"); r.pack(fill="x",pady=3)
        ctk.CTkLabel(r,text=mname,width=90,anchor="w",font=ctk.CTkFont(size=12)).pack(side="left")
        e=ctk.CTkEntry(r,height=34,corner_radius=6,placeholder_text=base,width=170)
        val=existing.get(str(i),"")
        if val: e.insert(0,str(val))
        e.pack(side="right"); entries[i]=e
    btn_f=ctk.CTkFrame(dlg,fg_color="transparent"); btn_f.pack(fill="x",padx=16,pady=10)
    def save():
        out={}
        for mnum,ent in entries.items():
            v=ent.get().strip().replace(",","").replace("$","")
            if v:
                try: out[str(mnum)]=float(v)
                except: pass
        item["monthly_amounts"]=out; dlg.destroy()
    abtn(btn_f,"✓ Save Amounts",save,height=40).pack(side="left",fill="x",expand=True,padx=(0,6))
    ghost_btn(btn_f,"Cancel",dlg.destroy,height=40).pack(side="left",fill="x",expand=True)


def edit_item_dialog(parent_widget, app, item, collection_key, on_done,
                     categories=None, title_prefix="Edit Expense"):
    """Universal edit dialog for expenses and income."""
    cats = categories or EXPENSE_CATEGORIES
    dlg=ctk.CTkToplevel(parent_widget); dlg.title(f"{title_prefix}: {item.get('name','')}")
    dlg.geometry("440x620"); dlg.resizable(False,False); dlg.grab_set()
    dlg.update_idletasks()
    try:
        x=parent_widget.winfo_rootx()+(parent_widget.winfo_width()-440)//2
        y=parent_widget.winfo_rooty()+(parent_widget.winfo_height()-620)//2
        dlg.geometry(f"440x620+{x}+{y}")
    except: pass

    sc=ctk.CTkScrollableFrame(dlg,fg_color="transparent"); sc.pack(fill="both",expand=True,padx=16,pady=10)
    ctk.CTkLabel(sc,text=title_prefix,font=ctk.CTkFont(size=15,weight="bold")).pack(pady=(5,14))

    def row(label,widget_fn):
        ctk.CTkLabel(sc,text=label,anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",pady=(4,2))
        w=widget_fn(); w.pack(fill="x",pady=(0,6)); return w

    n_e = ctk.CTkEntry(sc,height=38,corner_radius=6); n_e.insert(0,item.get("name","")); row("Name",lambda:n_e)
    a_e = ctk.CTkEntry(sc,height=38,corner_radius=6); a_e.insert(0,str(item.get("amount",0))); row("Amount ($)",lambda:a_e)

    ctk.CTkLabel(sc,text="Category",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",pady=(4,2))
    c_cb=ctk.CTkComboBox(sc,values=cats,height=38,corner_radius=6)
    c_cb.set(item.get("category",cats[0])); c_cb.pack(fill="x",pady=(0,6))

    ctk.CTkLabel(sc,text="Frequency",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",pady=(4,2))
    f_cb=ctk.CTkComboBox(sc,values=FREQ_OPTIONS,height=38,corner_radius=6)
    f_cb.set(KEY_TO_LABEL.get(item.get("frequency","monthly"),"Monthly")); f_cb.pack(fill="x",pady=(0,6))

    ctk.CTkLabel(sc,text="Starting / Due Month  (used by Quarterly, Semi-Annual, Annual)",
                 anchor="w",font=ctk.CTkFont(size=11),text_color=("#6b7280","#8892a4")).pack(fill="x",pady=(4,2))
    dm_cb=ctk.CTkComboBox(sc,values=MONTH_NAMES,height=38,corner_radius=6)
    dm_cb.set(MONTH_NAMES[max(0,min(11,int(item.get("due_month",1))-1))]); dm_cb.pack(fill="x",pady=(0,6))

    ctk.CTkLabel(sc,text="Day of Month  (1–31, for calendar display)",
                 anchor="w",font=ctk.CTkFont(size=11),text_color=("#6b7280","#8892a4")).pack(fill="x",pady=(4,2))
    day_cb=ctk.CTkComboBox(sc,values=[str(i) for i in range(1,32)],height=38,corner_radius=6,width=100)
    day_cb.set(str(item.get("day_of_month",1))); day_cb.pack(anchor="w",pady=(0,6))

    tags_f=ctk.CTkFrame(sc,fg_color="transparent"); tags_f.pack(fill="x",pady=5)
    rv=tk.BooleanVar(value=item.get("recurring",True)); vv=tk.BooleanVar(value=item.get("variable",False))
    ctk.CTkCheckBox(tags_f,text="Recurring",variable=rv,font=ctk.CTkFont(size=11),
                    checkbox_width=18,checkbox_height=18).pack(side="left",padx=(0,14))
    ctk.CTkCheckBox(tags_f,text="Variable Amount (≈avg)",variable=vv,font=ctk.CTkFont(size=11),
                    checkbox_width=18,checkbox_height=18,
                    fg_color=WARNING,hover_color="#cc8800").pack(side="left")
    # Per-month amounts button — visible only when Variable is checked
    ma_wrap=ctk.CTkFrame(sc,fg_color="transparent"); ma_wrap.pack(fill="x",pady=(0,4))
    _has_overrides=lambda: bool(item.get("monthly_amounts"))
    def _ma_label():
        n=len(item.get("monthly_amounts",{}))
        return f"📝  Set Per-Month Amounts  ({n}/12 set)" if n else "📝  Set Per-Month Amounts"
    ma_btn=abtn(ma_wrap,_ma_label(),lambda:(_open_ma()),color=WARNING,height=34)
    def _open_ma():
        monthly_amounts_dialog(dlg,item)
        ma_btn.configure(text=_ma_label())
    def _toggle_ma(*_):
        if vv.get(): ma_btn.pack(fill="x")
        else: ma_btn.pack_forget()
    vv.trace_add("write",_toggle_ma); _toggle_ma()

    ctk.CTkLabel(sc,text="Notes",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",pady=(8,2))
    nt=ctk.CTkTextbox(sc,height=90,corner_radius=6); nt.pack(fill="x",pady=(0,5))
    if item.get("notes"): nt.insert("1.0",item["notes"])

    if item.get("created"):
        ctk.CTkLabel(sc,text=f"Added: {item['created']}",font=ctk.CTkFont(size=10),
                     text_color=("#9ca3af","#6b7280")).pack(anchor="w",pady=(5,0))

    btn_f=ctk.CTkFrame(dlg,fg_color="transparent"); btn_f.pack(fill="x",padx=16,pady=10)

    def save():
        try: amt=float(a_e.get().replace(",","").replace("$",""))
        except: messagebox.showwarning("Invalid","Enter a valid amount.",parent=dlg); return
        n=n_e.get().strip()
        if not n: messagebox.showwarning("Missing","Enter a name.",parent=dlg); return
        for ex in app.data.get(collection_key,[]):
            if ex.get("id")==item.get("id"):
                ex["name"]=n; ex["amount"]=amt; ex["category"]=c_cb.get()
                ex["frequency"]=FREQ_TO_KEY.get(f_cb.get(),"monthly")
                ex["due_month"]=MONTH_NAMES.index(dm_cb.get())+1
                ex["day_of_month"]=int(day_cb.get())
                ex["recurring"]=rv.get(); ex["variable"]=vv.get()
                ex["notes"]=nt.get("1.0","end-1c").strip()
                # Carry per-month amounts set via sub-dialog; clear if variable unchecked
                ex["monthly_amounts"]=item.get("monthly_amounts",ex.get("monthly_amounts",{})) if ex["variable"] else {}
                break
        on_done(); dlg.destroy()

    abtn(btn_f,"💾 Save Changes",save,height=40).pack(side="left",fill="x",expand=True,padx=(0,6))
    ghost_btn(btn_f,"Cancel",dlg.destroy,height=40).pack(side="left",fill="x",expand=True)


# ── Dashboard Page ─────────────────────────────────────────────────────────────
class DashboardPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent")
        self.app=app; self._build()

    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=25,pady=(20,8))
        ctk.CTkLabel(hdr,text="Dashboard",font=ctk.CTkFont(size=24,weight="bold")).pack(side="left")
        last=self.app.data.get("last_saved","Never saved")
        ctk.CTkLabel(hdr,text=f"Last saved: {last}",font=ctk.CTkFont(size=10),
                     text_color=("#9ca3af","#6b7280")).pack(side="right",padx=10)
        abtn(hdr,"🔄 Refresh",self._refresh,height=36,width=120).pack(side="right",padx=4)
        self._tabs=ctk.CTkTabview(self,fg_color=("#f0f2f5","#0f1117"),
                                   segmented_button_selected_color=ACCENT,
                                   segmented_button_unselected_color=("#e2e8f0","#1a1d27"))
        self._tabs.pack(fill="both",expand=True,padx=20,pady=5)
        for t in ("📊  Overview","📅  Monthly","📆  Annual"): self._tabs.add(t)
        self._render_overview(self._tabs.tab("📊  Overview"))
        self._render_monthly(self._tabs.tab("📅  Monthly"))
        self._render_annual(self._tabs.tab("📆  Annual"))

    def _tc(self):
        dark=ctk.get_appearance_mode()=="Dark"
        return {"bg":"#1a1d27" if dark else "#ffffff","text":"#ffffff" if dark else "#1a1d27",
                "grid":"#2d3446" if dark else "#e2e8f0"}

    def _summary_row(self, parent, cards_data):
        row=ctk.CTkFrame(parent,fg_color="transparent"); row.pack(fill="x",pady=(5,10))
        for title,val,color,sub in cards_data:
            c=card(row); c.pack(side="left",fill="x",expand=True,padx=4)
            ctk.CTkFrame(c,height=4,fg_color=color,corner_radius=2).pack(fill="x")
            ctk.CTkLabel(c,text=title,font=ctk.CTkFont(size=11),
                         text_color=("#6b7280","#8892a4")).pack(anchor="w",padx=14,pady=(9,1))
            ctk.CTkLabel(c,text=val,font=ctk.CTkFont(size=18,weight="bold"),
                         text_color=color).pack(anchor="w",padx=14,pady=(0,1))
            ctk.CTkLabel(c,text=sub,font=ctk.CTkFont(size=10),
                         text_color=("#9ca3af","#6b7280")).pack(anchor="w",padx=14,pady=(0,10))

    # ── Overview Tab ───────────────────────────────────────────────────────────
    def _render_overview(self, parent):
        sc=ctk.CTkScrollableFrame(parent,fg_color="transparent"); sc.pack(fill="both",expand=True)
        nw=self.app.total_net_worth(); mon_in=self.app.monthly_income()
        mon_ex=self.app.monthly_equiv(); net_mon=mon_in-mon_ex
        ann_in=self.app.annual_income(); ann_ex=self.app.annual_total()

        net_color=SUCCESS if net_mon>=0 else DANGER
        self._summary_row(sc,[
            ("💰 Net Worth",       fmt(nw),     ACCENT,   "Total assets"),
            ("💵 Monthly Income",  fmt(mon_in),  SUCCESS,  "All income sources"),
            ("📉 Monthly Expenses",fmt(mon_ex),  DANGER,   "All expenses (equiv.)"),
            ("📊 Net Monthly",     fmt(net_mon), net_color,"Income − expenses"),
        ])

        # Second row: annual
        ann_net=ann_in-ann_ex; ann_net_c=SUCCESS if ann_net>=0 else DANGER
        self._summary_row(sc,[
            ("📆 Annual Income",   fmt(ann_in),  SUCCESS,  "Yearly income total"),
            ("📆 Annual Expenses", fmt(ann_ex),  DANGER,   "Yearly expense total"),
            ("✅ Annual Net",       fmt(ann_net), ann_net_c,"Income − expenses"),
            ("🏦 NW Balance",      fmt(nw-ann_ex),ACCENT,  "Net worth − annual exp."),
        ])

        if MATPLOTLIB_OK:
            cr=ctk.CTkFrame(sc,fg_color="transparent"); cr.pack(fill="x",pady=(0,10))
            self._pie(cr); self._exp_bar(cr)
            self._income_vs_expense_chart(sc)
        self._breakdown(sc)

    def _pie(self, parent):
        c=card(parent); c.pack(side="left",fill="both",expand=True,padx=(0,6))
        ctk.CTkLabel(c,text="Net Worth Breakdown",font=ctk.CTkFont(size=13,weight="bold")).pack(padx=14,pady=10)
        cats=self.app.category_totals_nw(); tc=self._tc()
        fig=Figure(figsize=(4,3.2),dpi=85,facecolor=tc["bg"]); ax=fig.add_subplot(111,facecolor=tc["bg"])
        vals=[v for v in cats.values() if v>0]; lbls=[k for k,v in cats.items() if v>0]
        pcols=[ACCENT,GOLD,SUCCESS,ACCENT2][:len(vals)]
        if vals:
            _,_,autos=ax.pie(vals,labels=lbls,colors=pcols,autopct="%1.1f%%",startangle=140,
                              textprops={"color":tc["text"],"fontsize":9})
            for a in autos: a.set_color("white"); a.set_fontsize(8)
        else: ax.text(0.5,0.5,"No data",ha="center",va="center",color=tc["text"],transform=ax.transAxes)
        fig.tight_layout(); cv=FigureCanvasTkAgg(fig,c); cv.draw()
        cv.get_tk_widget().pack(fill="both",expand=True,padx=10,pady=(0,10))

    def _exp_bar(self, parent):
        c=card(parent); c.pack(side="right",fill="both",expand=True,padx=(6,0))
        ctk.CTkLabel(c,text="Monthly Expenses by Category",font=ctk.CTkFont(size=13,weight="bold")).pack(padx=14,pady=10)
        cats=self.app.expense_by_category(); tc=self._tc()
        fig=Figure(figsize=(4,3.2),dpi=85,facecolor=tc["bg"]); ax=fig.add_subplot(111,facecolor=tc["bg"])
        if cats:
            items=sorted(cats.items(),key=lambda x:x[1],reverse=True)[:8]; ks,vs=zip(*items)
            ax.barh(ks,vs,color=DANGER,alpha=0.85)
            ax.set_xlabel("Monthly ($)",color=tc["text"],fontsize=9); ax.tick_params(colors=tc["text"],labelsize=8)
            for sp in("top","right"): ax.spines[sp].set_visible(False)
            for sp in("bottom","left"): ax.spines[sp].set_color(tc["grid"])
            ax.grid(axis="x",color=tc["grid"],alpha=0.4)
        else: ax.text(0.5,0.5,"No data",ha="center",va="center",color=tc["text"],transform=ax.transAxes)
        fig.tight_layout(); cv=FigureCanvasTkAgg(fig,c); cv.draw()
        cv.get_tk_widget().pack(fill="both",expand=True,padx=10,pady=(0,10))

    def _income_vs_expense_chart(self, parent):
        c=card(parent); c.pack(fill="x",pady=(0,10))
        ctk.CTkLabel(c,text="Income vs Expenses Overview",font=ctk.CTkFont(size=13,weight="bold")).pack(padx=14,pady=10)
        mon_in=self.app.monthly_income(); mon_ex=self.app.monthly_equiv()
        ann_in=self.app.annual_income(); ann_ex=self.app.annual_total(); nw=self.app.total_net_worth()
        tc=self._tc(); fig=Figure(figsize=(9,2.8),dpi=85,facecolor=tc["bg"])
        ax=fig.add_subplot(111,facecolor=tc["bg"])
        lbls=["Net Worth","Monthly Income","Monthly Expenses","Annual Income","Annual Expenses"]
        vals=[nw,mon_in,mon_ex,ann_in,ann_ex]; clrs=[ACCENT,SUCCESS,DANGER,SUCCESS,DANGER]
        bars=ax.bar(lbls,vals,color=clrs,alpha=0.85,width=0.55)
        for bar,v in zip(bars,vals):
            ax.text(bar.get_x()+bar.get_width()/2,bar.get_height(),fmt(v),
                    ha="center",va="bottom",color=tc["text"],fontsize=8)
        ax.tick_params(colors=tc["text"],labelsize=8); ax.set_ylabel("($)",color=tc["text"],fontsize=9)
        for sp in("top","right"): ax.spines[sp].set_visible(False)
        for sp in("bottom","left"): ax.spines[sp].set_color(tc["grid"])
        ax.grid(axis="y",color=tc["grid"],alpha=0.4)
        fig.tight_layout(); cv=FigureCanvasTkAgg(fig,c); cv.draw()
        cv.get_tk_widget().pack(fill="both",expand=True,padx=10,pady=(0,10))

    def _breakdown(self, parent):
        c=card(parent); c.pack(fill="x",pady=(0,14))
        hdr=ctk.CTkFrame(c,fg_color="transparent"); hdr.pack(fill="x",padx=14,pady=12)
        ctk.CTkLabel(hdr,text="Full Net Worth Breakdown",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        ef=ctk.CTkFrame(hdr,fg_color="transparent"); ef.pack(side="right")
        abtn(ef,"📄 PDF",self._export_pdf,color="#e74c3c",width=90,height=32).pack(side="left",padx=3)
        abtn(ef,"📊 CSV",self._export_csv,color="#27ae60",width=90,height=32).pack(side="left",padx=3)
        nwd=self.app.data.get("net_worth",{})
        for key,lbl,color in[("banks","🏦 Bank Accounts",ACCENT),("crypto","₿ Crypto",GOLD),
                               ("stocks","📈 Stocks",SUCCESS),("assets","🏠 Assets",ACCENT2)]:
            items=nwd.get(key,[])
            if items:
                ctk.CTkLabel(c,text=lbl,font=ctk.CTkFont(size=12,weight="bold"),text_color=color).pack(anchor="w",padx=14,pady=(8,3))
                for it in items:
                    r=ctk.CTkFrame(c,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",padx=14,pady=1)
                    ctk.CTkLabel(r,text=it.get("name",""),anchor="w").pack(side="left",padx=10,pady=5)
                    ctk.CTkLabel(r,text=fmt(it.get("value",0)),font=ctk.CTkFont(weight="bold")).pack(side="right",padx=10)
        divider(c)
        tot=ctk.CTkFrame(c,fg_color="transparent"); tot.pack(fill="x",padx=14,pady=10)
        ctk.CTkLabel(tot,text="TOTAL NET WORTH",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        ctk.CTkLabel(tot,text=fmt(self.app.total_net_worth()),font=ctk.CTkFont(size=18,weight="bold"),
                     text_color=SUCCESS).pack(side="right")

    # ── Monthly Tab ────────────────────────────────────────────────────────────
    def _render_monthly(self, parent):
        sc=ctk.CTkScrollableFrame(parent,fg_color="transparent"); sc.pack(fill="both",expand=True)
        mon_in=self.app.monthly_income(); mon_ex=self.app.monthly_equiv()
        net=mon_in-mon_ex; nc=SUCCESS if net>=0 else DANGER
        self._summary_row(sc,[
            ("💵 Monthly Income",    fmt(mon_in), SUCCESS, "All income monthly equiv."),
            ("📉 Monthly Expenses",  fmt(mon_ex), DANGER,  "All expenses monthly equiv."),
            ("📊 Net Monthly",       fmt(net),    nc,      "Income − expenses"),
            ("📅 Monthly Bills Only",fmt(self.app.monthly_bills_only()), WARNING,"Strictly monthly-tagged"),
        ])
        # Income by source
        inc_data=self.app.data.get("income",[])
        if inc_data:
            c=card(sc); c.pack(fill="x",pady=6)
            ctk.CTkLabel(c,text="💵 Income Sources",font=ctk.CTkFont(size=13,weight="bold"),
                         text_color=SUCCESS).pack(anchor="w",padx=14,pady=(12,4))
            for i in inc_data:
                r=ctk.CTkFrame(c,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",padx=14,pady=2)
                ctk.CTkLabel(r,text=i.get("name",""),anchor="w").pack(side="left",padx=10,pady=6)
                ctk.CTkLabel(r,text=i.get("category",""),font=ctk.CTkFont(size=10),
                             text_color=(SUCCESS,"#4ade80")).pack(side="left",padx=8)
                ctk.CTkLabel(r,text=fmt(float(i.get("amount",0))),
                             font=ctk.CTkFont(weight="bold"),text_color=(SUCCESS,SUCCESS)).pack(side="right",padx=(4,4))
                freq=i.get("frequency","monthly")
                if freq!="monthly":
                    ctk.CTkLabel(r,text=f"≈{fmt(exp_monthly(i))}/mo",font=ctk.CTkFont(size=10),
                                 text_color=("#6b7280","#8892a4")).pack(side="right",padx=4)
                ctk.CTkLabel(r,text=KEY_TO_LABEL.get(freq,"Monthly"),font=ctk.CTkFont(size=10),
                             text_color=("#6b7280","#8892a4")).pack(side="right",padx=4)
        # Expenses by frequency group
        freq_groups={}
        for e in self.app.data.get("expenses",[]): f=e.get("frequency","monthly"); freq_groups.setdefault(f,[]).append(e)
        for fk in["weekly","biweekly","monthly","quarterly","semiannual","annual"]:
            items=freq_groups.get(fk,[])
            if not items: continue
            c=card(sc); c.pack(fill="x",pady=6)
            lbl=KEY_TO_LABEL.get(fk,fk.title())
            hdr_f=ctk.CTkFrame(c,fg_color="transparent"); hdr_f.pack(fill="x",padx=14,pady=(12,4))
            ctk.CTkLabel(hdr_f,text=f"{lbl} Expenses",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
            ctk.CTkLabel(hdr_f,text=f"≈{fmt(sum(exp_monthly(e) for e in items))}/mo",
                         font=ctk.CTkFont(size=12,weight="bold"),text_color=DANGER).pack(side="right")
            for e in items:
                r=ctk.CTkFrame(c,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",padx=14,pady=2)
                ctk.CTkLabel(r,text=e.get("name",""),anchor="w").pack(side="left",padx=10,pady=6)
                tags="".join(["🔄" if e.get("recurring") else "","≈" if e.get("variable") else "","📝" if e.get("notes") else ""])
                if tags: ctk.CTkLabel(r,text=tags,font=ctk.CTkFont(size=11)).pack(side="left",padx=4)
                ctk.CTkLabel(r,text=fmt(float(e.get("amount",0))),
                             font=ctk.CTkFont(weight="bold"),text_color=(DANGER,DANGER)).pack(side="right",padx=10)
                if fk!="monthly": ctk.CTkLabel(r,text=f"≈{fmt(exp_monthly(e))}/mo",font=ctk.CTkFont(size=10),
                                               text_color=("#6b7280","#8892a4")).pack(side="right",padx=4)

    # ── Annual Tab ─────────────────────────────────────────────────────────────
    def _render_annual(self, parent):
        sc=ctk.CTkScrollableFrame(parent,fg_color="transparent"); sc.pack(fill="both",expand=True)
        ann_in=self.app.annual_income(); ann_ex=self.app.annual_total(); net=ann_in-ann_ex; nc=SUCCESS if net>=0 else DANGER
        self._summary_row(sc,[
            ("📆 Annual Income",    fmt(ann_in), SUCCESS, "All income sources"),
            ("📆 Annual Expenses",  fmt(ann_ex), DANGER,  "All expenses"),
            ("📊 Annual Net",       fmt(net),    nc,      "Income − expenses"),
            ("📅 Monthly Equiv.",   fmt(ann_ex/12 if ann_ex else 0), WARNING,"Annual ÷ 12"),
        ])
        if MATPLOTLIB_OK:
            c=card(sc); c.pack(fill="x",pady=(0,10))
            ctk.CTkLabel(c,text="Annual Expense Distribution",font=ctk.CTkFont(size=13,weight="bold")).pack(padx=14,pady=10)
            cats={}
            for e in self.app.data.get("expenses",[]): cat=e.get("category","Other"); cats[cat]=cats.get(cat,0)+exp_annual(e)
            tc=self._tc(); fig=Figure(figsize=(9,3),dpi=85,facecolor=tc["bg"])
            ax=fig.add_subplot(111,facecolor=tc["bg"])
            if cats:
                items=sorted(cats.items(),key=lambda x:x[1],reverse=True); ks,vs=zip(*items)
                bars=ax.bar(ks,vs,color=DANGER,alpha=0.85)
                for bar,v in zip(bars,vs):
                    ax.text(bar.get_x()+bar.get_width()/2,bar.get_height(),fmt(v),
                            ha="center",va="bottom",color=tc["text"],fontsize=8)
                ax.tick_params(colors=tc["text"],labelsize=8); ax.set_ylabel("Annual ($)",color=tc["text"],fontsize=9)
                for sp in("top","right"): ax.spines[sp].set_visible(False)
                for sp in("bottom","left"): ax.spines[sp].set_color(tc["grid"])
                ax.grid(axis="y",color=tc["grid"],alpha=0.4)
            fig.tight_layout(); cv=FigureCanvasTkAgg(fig,c); cv.draw()
            cv.get_tk_widget().pack(fill="both",expand=True,padx=10,pady=(0,10))
        dc=card(sc); dc.pack(fill="x",pady=(0,14))
        ctk.CTkLabel(dc,text="Annual Detail",font=ctk.CTkFont(size=13,weight="bold")).pack(anchor="w",padx=14,pady=12)
        hh=ctk.CTkFrame(dc,fg_color=("#e2e8f0","#2d3446"),corner_radius=6); hh.pack(fill="x",padx=14,pady=(0,4))
        for t,w in[("Name",180),("Category",120),("Amount",100),("Frequency",100),("Annual",110)]:
            ctk.CTkLabel(hh,text=t,font=ctk.CTkFont(size=11,weight="bold"),width=w,anchor="w").pack(side="left",padx=5,pady=5)
        for e in sorted(self.app.data.get("expenses",[]),key=lambda x:exp_annual(x),reverse=True):
            r=ctk.CTkFrame(dc,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",padx=14,pady=1)
            ctk.CTkLabel(r,text=e.get("name",""),width=180,anchor="w").pack(side="left",padx=(10,4),pady=6)
            ctk.CTkLabel(r,text=e.get("category",""),width=120,anchor="w",
                         text_color=(ACCENT,"#a09bff"),font=ctk.CTkFont(size=10)).pack(side="left",padx=4)
            ctk.CTkLabel(r,text=fmt(e.get("amount",0)),width=100,anchor="e",
                         font=ctk.CTkFont(weight="bold")).pack(side="left",padx=4)
            ctk.CTkLabel(r,text=KEY_TO_LABEL.get(e.get("frequency","monthly"),"Monthly"),
                         width=100,anchor="w",font=ctk.CTkFont(size=10)).pack(side="left",padx=4)
            ctk.CTkLabel(r,text=fmt(exp_annual(e)),width=110,anchor="e",
                         text_color=(DANGER,DANGER),font=ctk.CTkFont(weight="bold")).pack(side="left",padx=4)
        divider(dc)
        tr=ctk.CTkFrame(dc,fg_color="transparent"); tr.pack(fill="x",padx=14,pady=10)
        ctk.CTkLabel(tr,text="TOTAL ANNUAL EXPENSES",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        ctk.CTkLabel(tr,text=fmt(ann_ex),font=ctk.CTkFont(size=18,weight="bold"),text_color=DANGER).pack(side="right")

    def _refresh(self):
        for w in self.winfo_children(): w.destroy(); self._build()

    def _export_csv(self):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],
              initialfile=f"IRIS_Export_{ts()}.csv",parent=self)
        if not path: return
        try:
            with open(path,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f)
                w.writerow([APP_NAME,"Export"]); w.writerow(["Generated:",now_str()]); w.writerow([])
                w.writerow(["INCOME"]); w.writerow(["Name","Category","Amount","Frequency","Monthly Equiv.","Annual"])
                for i in self.app.data.get("income",[]): w.writerow([i.get("name",""),i.get("category",""),i.get("amount",0),KEY_TO_LABEL.get(i.get("frequency","monthly"),"Monthly"),f"{exp_monthly(i):.2f}",f"{exp_annual(i):.2f}"])
                w.writerow(["TOTAL","","","",f"{self.app.monthly_income():.2f}",f"{self.app.annual_income():.2f}"]); w.writerow([])
                w.writerow(["NET WORTH"]); w.writerow(["Category","Name","Value"])
                nwd=self.app.data.get("net_worth",{})
                for key,lbl in[("banks","Bank"),("crypto","Crypto"),("stocks","Stocks"),("assets","Asset")]:
                    for it in nwd.get(key,[]): w.writerow([lbl,it.get("name",""),it.get("value",0)])
                w.writerow(["TOTAL","",self.app.total_net_worth()]); w.writerow([])
                w.writerow(["EXPENSES"]); w.writerow(["Name","Category","Amount","Frequency","Monthly Equiv.","Annual"])
                for e in self.app.data.get("expenses",[]): w.writerow([e.get("name",""),e.get("category",""),e.get("amount",0),KEY_TO_LABEL.get(e.get("frequency","monthly"),"Monthly"),f"{exp_monthly(e):.2f}",f"{exp_annual(e):.2f}"])
                w.writerow(["TOTAL MONTHLY","","","",f"{self.app.monthly_equiv():.2f}",""])
                w.writerow(["TOTAL ANNUAL","","","","",f"{self.app.annual_total():.2f}"])
            messagebox.showinfo("Exported",f"Saved to:\n{path}",parent=self)
        except Exception as ex: messagebox.showerror("Error",str(ex),parent=self)

    def _export_pdf(self):
        if not REPORTLAB_OK: messagebox.showwarning("Missing","Install: pip install reportlab",parent=self); return
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")],
              initialfile=f"IRIS_Report_{ts()}.pdf",parent=self)
        if not path: return
        try: _generate_pdf(path,self.app); messagebox.showinfo("Exported",f"PDF saved:\n{path}",parent=self)
        except Exception as ex: messagebox.showerror("Error",str(ex),parent=self)


# ── PDF Generator ──────────────────────────────────────────────────────────────
def _generate_pdf(path, app):
    doc=SimpleDocTemplate(path,pagesize=letter,topMargin=.5*inch,bottomMargin=.5*inch,leftMargin=.75*inch,rightMargin=.75*inch)
    styles=getSampleStyleSheet()
    h1=ParagraphStyle("H1",parent=styles["Heading1"],fontSize=14,spaceBefore=14,textColor=colors.HexColor(ACCENT))
    ts_=ParagraphStyle("T",parent=styles["Title"],fontSize=22,spaceAfter=4,textColor=colors.HexColor(ACCENT))
    def tbl(data,cw,hc=ACCENT):
        t=Table(data,colWidths=cw)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(hc)),("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),10),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f8f9fc")]),
            ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#e2e8f0")),("LEFTPADDING",(0,0),(-1,-1),8),
            ("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        return t
    story=[Paragraph(APP_NAME,ts_),Paragraph(f"Report — {now_str()}",styles["Normal"]),
           Paragraph(f"User: {app.username}",styles["Normal"]),Spacer(1,.2*inch),Paragraph("Summary",h1)]
    story.append(tbl([["Metric","Value"],["Net Worth",fmt(app.total_net_worth())],
        ["Monthly Income",fmt(app.monthly_income())],["Monthly Expenses (Equiv.)",fmt(app.monthly_equiv())],
        ["Net Monthly",fmt(app.monthly_income()-app.monthly_equiv())],
        ["Annual Income",fmt(app.annual_income())],["Annual Expenses",fmt(app.annual_total())],
        ["Annual Net",fmt(app.annual_income()-app.annual_total())]],[3.5*inch,3*inch]))
    story.append(Spacer(1,.15*inch)); story.append(Paragraph("Income",h1))
    ir=[["Name","Category","Amount","Frequency","Monthly Equiv.","Annual"]]
    for i in app.data.get("income",[]): ir.append([i.get("name",""),i.get("category",""),fmt(i.get("amount",0)),KEY_TO_LABEL.get(i.get("frequency","monthly"),"Monthly"),fmt(exp_monthly(i)),fmt(exp_annual(i))])
    ir.append(["TOTAL","","","",fmt(app.monthly_income()),fmt(app.annual_income())])
    if len(ir)>1:
        t2=tbl(ir,[2*inch,1.2*inch,1*inch,1*inch,1*inch,1*inch],SUCCESS)
        t2.setStyle(TableStyle([("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#e8f5e9"))])); story.append(t2)
    story.append(Spacer(1,.15*inch)); story.append(Paragraph("Expenses",h1))
    er=[["Name","Category","Amount","Frequency","Monthly Equiv.","Annual"]]
    for e in app.data.get("expenses",[]): er.append([e.get("name",""),e.get("category",""),fmt(e.get("amount",0)),KEY_TO_LABEL.get(e.get("frequency","monthly"),"Monthly"),fmt(exp_monthly(e)),fmt(exp_annual(e))])
    er.append(["TOTAL MONTHLY","","","",fmt(app.monthly_equiv()),""]);er.append(["TOTAL ANNUAL","","","","",fmt(app.annual_total())])
    if len(er)>1:
        t3=tbl(er,[2*inch,1.2*inch,1*inch,1*inch,1*inch,1*inch],DANGER)
        t3.setStyle(TableStyle([("FONTNAME",(0,-2),(-1,-1),"Helvetica-Bold"),("BACKGROUND",(0,-2),(-1,-1),colors.HexColor("#fce4e4"))])); story.append(t3)
    doc.build(story)


# ── Net Worth Page ─────────────────────────────────────────────────────────────
class NetWorthPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self._build()

    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=25,pady=(20,10))
        ctk.CTkLabel(hdr,text="Net Worth",font=ctk.CTkFont(size=24,weight="bold")).pack(side="left")
        self._tl=ctk.CTkLabel(hdr,text=fmt(self.app.total_net_worth()),
                              font=ctk.CTkFont(size=22,weight="bold"),text_color=SUCCESS); self._tl.pack(side="right")
        sc=ctk.CTkScrollableFrame(self,fg_color="transparent"); sc.pack(fill="both",expand=True,padx=25,pady=5)
        for icon,title,key,color in[("🏦","Bank Accounts","banks",ACCENT),("₿","Cryptocurrency","crypto",GOLD),
                                     ("📈","Stocks & ETFs","stocks",SUCCESS),("🏠","Assets","assets",ACCENT2)]:
            self._cat_card(sc,icon,title,key,color)

    def _cat_card(self,parent,icon,title,key,color):
        c=card(parent); c.pack(fill="x",pady=8)
        hdr=ctk.CTkFrame(c,fg_color="transparent"); hdr.pack(fill="x",padx=14,pady=(12,4))
        ctk.CTkLabel(hdr,text=f"{icon}  {title}",font=ctk.CTkFont(size=15,weight="bold"),text_color=color).pack(side="left")
        cl=ctk.CTkLabel(hdr,text="",font=ctk.CTkFont(size=14,weight="bold"),text_color=color); cl.pack(side="right")
        if_=ctk.CTkFrame(c,fg_color=("#f8f9fc","#21253a"),corner_radius=8); if_.pack(fill="x",padx=14,pady=(4,14))
        def refresh():
            for w in if_.winfo_children(): w.destroy()
            items=self.app.data.get("net_worth",{}).get(key,[])
            cl.configure(text=fmt(sum(float(i.get("value",0)) for i in items)))
            if not items: ctk.CTkLabel(if_,text="No items. Click + Add to begin.",text_color=("#9ca3af","#6b7280"),font=ctk.CTkFont(size=11)).pack(pady=10)
            else:
                for idx,it in enumerate(items):
                    r=ctk.CTkFrame(if_,fg_color="transparent"); r.pack(fill="x",padx=8,pady=2)
                    ctk.CTkLabel(r,text=it.get("name",""),font=ctk.CTkFont(size=12),anchor="w").pack(side="left",fill="x",expand=True)
                    vv=tk.StringVar(value=str(it.get("value",0)))
                    def commit(vr=vv,i=idx,k=key,_=None):
                        try: self.app.data["net_worth"][k][i]["value"]=float(vr.get().replace(",","").replace("$","")); refresh(); self._tl.configure(text=fmt(self.app.total_net_worth()))
                        except: pass
                    ve=ctk.CTkEntry(r,textvariable=vv,width=130,height=32,justify="right"); ve.pack(side="right",padx=4)
                    ve.bind("<FocusOut>",commit); ve.bind("<Return>",commit)
                    def delete(i=idx,k=key):
                        self.app.data["net_worth"][k].pop(i); refresh(); self._tl.configure(text=fmt(self.app.total_net_worth()))
                    ctk.CTkButton(r,text="✕",width=30,height=30,fg_color="transparent",hover_color=("#fecaca","#3d1515"),text_color=(DANGER,DANGER),command=delete).pack(side="right",padx=4)
            add=ctk.CTkFrame(if_,fg_color="transparent"); add.pack(fill="x",padx=8,pady=(6,10))
            ne=ctk.CTkEntry(add,placeholder_text="Name / Account label",height=34,corner_radius=6); ne.pack(side="left",fill="x",expand=True,padx=(0,6))
            ve2=ctk.CTkEntry(add,placeholder_text="Value ($)",width=110,height=34,corner_radius=6); ve2.pack(side="left",padx=(0,6))
            def do_add():
                n=ne.get().strip()
                if not n: return
                try: v=float(ve2.get().replace(",","").replace("$",""))
                except: v=0.0
                self.app.data.setdefault("net_worth",{}).setdefault(key,[]).append({"name":n,"value":v})
                ne.delete(0,"end"); ve2.delete(0,"end"); refresh(); self._tl.configure(text=fmt(self.app.total_net_worth()))
            ne.bind("<Return>",lambda _:do_add()); ve2.bind("<Return>",lambda _:do_add())
            abtn(add,"+ Add",do_add,color=color,height=34,width=70).pack(side="left")
        refresh()


# ── Income Page ────────────────────────────────────────────────────────────────
class IncomePage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self._build()

    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=25,pady=(20,10))
        ctk.CTkLabel(hdr,text="Income",font=ctk.CTkFont(size=24,weight="bold")).pack(side="left")
        self._mon_lbl=ctk.CTkLabel(hdr,text="",font=ctk.CTkFont(size=13,weight="bold"),text_color=SUCCESS)
        self._mon_lbl.pack(side="right")
        self._ann_lbl=ctk.CTkLabel(hdr,text="",font=ctk.CTkFont(size=12),text_color=("#6b7280","#8892a4"))
        self._ann_lbl.pack(side="right",padx=16); self._update_totals()
        body=ctk.CTkFrame(self,fg_color="transparent"); body.pack(fill="both",expand=True,padx=25,pady=5)
        form=card(body); form.pack(side="left",fill="y",padx=(0,10)); form.configure(width=300); form.pack_propagate(False)
        self._build_form(form)
        right=ctk.CTkFrame(body,fg_color="transparent"); right.pack(side="right",fill="both",expand=True)
        ctk.CTkLabel(right,text="💡 Click any row to edit. Income is shown in the Dashboard.",
                     font=ctk.CTkFont(size=10),text_color=("#9ca3af","#6b7280")).pack(anchor="e",pady=(0,6))
        self._list_f=ctk.CTkScrollableFrame(right,fg_color=("#f8f9fc","#21253a"),corner_radius=10)
        self._list_f.pack(fill="both",expand=True); self._refresh_list()

    def _build_form(self, f):
        ctk.CTkLabel(f,text="Add Income Source",font=ctk.CTkFont(size=14,weight="bold")).pack(padx=14,pady=(14,10))
        ctk.CTkLabel(f,text="Name",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(4,2))
        self._in=ctk.CTkEntry(f,placeholder_text="e.g. Day Job, Rental Property",height=38,corner_radius=6); self._in.pack(fill="x",padx=14,pady=(0,5))
        ctk.CTkLabel(f,text="Amount ($)",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(4,2))
        self._ia=ctk.CTkEntry(f,placeholder_text="0.00",height=38,corner_radius=6); self._ia.pack(fill="x",padx=14,pady=(0,5))
        ctk.CTkLabel(f,text="Category",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(4,2))
        self._ic=ctk.CTkComboBox(f,values=INCOME_CATEGORIES,height=38,corner_radius=6); self._ic.set("Employment"); self._ic.pack(fill="x",padx=14,pady=(0,5))
        ctk.CTkLabel(f,text="Frequency",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(4,2))
        self._if=ctk.CTkComboBox(f,values=FREQ_OPTIONS,height=38,corner_radius=6); self._if.set("Bi-Weekly"); self._if.pack(fill="x",padx=14,pady=(0,5))
        ctk.CTkLabel(f,text="Starting Month",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(4,2))
        self._idm=ctk.CTkComboBox(f,values=MONTH_NAMES,height=38,corner_radius=6); self._idm.set(MONTH_NAMES[0]); self._idm.pack(fill="x",padx=14,pady=(0,5))
        ctk.CTkLabel(f,text="Notes (optional)",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(4,2))
        self._inotes=ctk.CTkTextbox(f,height=60,corner_radius=6); self._inotes.pack(fill="x",padx=14,pady=(0,5))
        abtn(f,"+ Add Income",self._add,color=SUCCESS,height=42).pack(fill="x",padx=14,pady=(5,14))

    def _add(self):
        name=self._in.get().strip()
        if not name: messagebox.showwarning("Missing","Enter a name.",parent=self); return
        try: amt=float(self._ia.get().replace(",","").replace("$",""))
        except: messagebox.showwarning("Invalid","Enter a valid amount.",parent=self); return
        freq_key=FREQ_TO_KEY.get(self._if.get(),"biweekly"); dm=MONTH_NAMES.index(self._idm.get())+1
        notes=self._inotes.get("1.0","end-1c").strip()
        self.app.data.setdefault("income",[]).append({
            "id":secrets.token_hex(8),"name":name,"category":self._ic.get(),"amount":amt,
            "frequency":freq_key,"due_month":dm,"day_of_month":1,"recurring":True,
            "variable":False,"notes":notes,"created":now_str()})
        self._in.delete(0,"end"); self._ia.delete(0,"end"); self._inotes.delete("1.0","end")
        self._refresh_list(); self._update_totals()

    def _refresh_list(self):
        for w in self._list_f.winfo_children(): w.destroy()
        inc=self.app.data.get("income",[])
        if not inc: ctk.CTkLabel(self._list_f,text="No income sources yet. Add one!",text_color=("#9ca3af","#6b7280")).pack(pady=20); return
        hdr=ctk.CTkFrame(self._list_f,fg_color=("#e2e8f0","#2d3446"),corner_radius=6); hdr.pack(fill="x",padx=4,pady=(6,3))
        for t,w in[("Name",155),("Category",105),("Amount",95),("Frequency",90),("Monthly≈",85),("",36)]:
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11,weight="bold"),width=w,anchor="w").pack(side="left",padx=5,pady=5)
        for i in inc: self._inc_row(i)

    def _inc_row(self, item):
        row=card(self._list_f); row.pack(fill="x",padx=4,pady=2); row.configure(cursor="hand2")
        freq=item.get("frequency","monthly"); amt=float(item.get("amount",0))
        ctk.CTkLabel(row,text=item.get("name",""),width=155,anchor="w").pack(side="left",padx=(10,4),pady=8)
        ctk.CTkLabel(row,text=item.get("category",""),width=105,anchor="w",
                     text_color=(SUCCESS,"#4ade80"),font=ctk.CTkFont(size=10)).pack(side="left",padx=4)
        ctk.CTkLabel(row,text=fmt(amt),width=95,anchor="e",
                     font=ctk.CTkFont(weight="bold"),text_color=(SUCCESS,SUCCESS)).pack(side="left",padx=4)
        fc=("#3b82f6","#60a5fa") if freq=="monthly" else("#8b5cf6","#a78bfa")
        ctk.CTkLabel(row,text=KEY_TO_LABEL.get(freq,"Monthly"),width=90,text_color=fc,font=ctk.CTkFont(size=10)).pack(side="left",padx=4)
        ctk.CTkLabel(row,text=fmt(exp_monthly(item)),width=85,anchor="e",font=ctk.CTkFont(size=10),text_color=("#6b7280","#8892a4")).pack(side="left",padx=4)
        def delete(iid=item.get("id")):
            if messagebox.askyesno("Delete",f"Remove '{item.get('name','')}'?",parent=self):
                self.app.data["income"]=[x for x in self.app.data.get("income",[]) if x.get("id")!=iid]
                self._refresh_list(); self._update_totals()
        ctk.CTkButton(row,text="✕",width=30,height=30,fg_color="transparent",hover_color=("#fecaca","#3d1515"),text_color=(DANGER,DANGER),command=delete).pack(side="right",padx=6)
        def on_click(_=None): edit_item_dialog(self,self.app,item,"income",lambda:(self._refresh_list(),self._update_totals()),categories=INCOME_CATEGORIES,title_prefix="Edit Income")
        for w in(row,*row.winfo_children()): w.bind("<Button-1>",on_click)

    def _update_totals(self):
        self._mon_lbl.configure(text=f"Monthly: {fmt(self.app.monthly_income())}")
        self._ann_lbl.configure(text=f"Annual: {fmt(self.app.annual_income())}")


# ── Expenses Page ──────────────────────────────────────────────────────────────
class ExpensesPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent")
        self.app=app; self._fcat=tk.StringVar(value="All"); self._ffreq=tk.StringVar(value="All")
        self._build()

    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=25,pady=(20,10))
        ctk.CTkLabel(hdr,text="Expenses & Bills",font=ctk.CTkFont(size=24,weight="bold")).pack(side="left")
        self._mon_lbl=ctk.CTkLabel(hdr,text="",font=ctk.CTkFont(size=13,weight="bold"),text_color=DANGER); self._mon_lbl.pack(side="right")
        self._ann_lbl=ctk.CTkLabel(hdr,text="",font=ctk.CTkFont(size=12),text_color=("#6b7280","#8892a4")); self._ann_lbl.pack(side="right",padx=16)
        self._update_totals()
        body=ctk.CTkFrame(self,fg_color="transparent"); body.pack(fill="both",expand=True,padx=25,pady=5)
        form=card(body); form.pack(side="left",fill="y",padx=(0,10)); form.configure(width=305); form.pack_propagate(False)
        self._build_form(form)
        right=ctk.CTkFrame(body,fg_color="transparent"); right.pack(side="right",fill="both",expand=True)
        fb=card(right); fb.pack(fill="x",pady=(0,8))
        ctk.CTkLabel(fb,text="Filter:",font=ctk.CTkFont(size=11)).pack(side="left",padx=12,pady=10)
        ctk.CTkComboBox(fb,values=["All"]+EXPENSE_CATEGORIES,variable=self._fcat,width=160,height=32,command=lambda _:self._refresh_list()).pack(side="left",padx=4,pady=10)
        ctk.CTkComboBox(fb,values=["All"]+FREQ_OPTIONS,variable=self._ffreq,width=130,height=32,command=lambda _:self._refresh_list()).pack(side="left",padx=4,pady=10)
        ctk.CTkLabel(fb,text="💡 Click row to edit / view notes",font=ctk.CTkFont(size=10),text_color=("#9ca3af","#6b7280")).pack(side="right",padx=12)
        self._list_f=ctk.CTkScrollableFrame(right,fg_color=("#f8f9fc","#21253a"),corner_radius=10)
        self._list_f.pack(fill="both",expand=True); self._refresh_list()

    def _build_form(self, f):
        ctk.CTkLabel(f,text="Add Expense / Bill",font=ctk.CTkFont(size=14,weight="bold")).pack(padx=14,pady=(14,8))
        ctk.CTkLabel(f,text="Name",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(3,2))
        self._en=ctk.CTkEntry(f,placeholder_text="e.g. Electric Bill",height=36,corner_radius=6); self._en.pack(fill="x",padx=14,pady=(0,4))
        ctk.CTkLabel(f,text="Amount ($)",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(3,2))
        self._ea=ctk.CTkEntry(f,placeholder_text="0.00",height=36,corner_radius=6); self._ea.pack(fill="x",padx=14,pady=(0,4))
        ctk.CTkLabel(f,text="Category",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(3,2))
        self._ec=ctk.CTkComboBox(f,values=EXPENSE_CATEGORIES,height=36,corner_radius=6); self._ec.set("Utilities"); self._ec.pack(fill="x",padx=14,pady=(0,4))
        ctk.CTkLabel(f,text="Frequency",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(3,2))
        self._ef=ctk.CTkComboBox(f,values=FREQ_OPTIONS,height=36,corner_radius=6); self._ef.set("Monthly"); self._ef.pack(fill="x",padx=14,pady=(0,4))
        ctk.CTkLabel(f,text="Starting / Due Month",anchor="w",font=ctk.CTkFont(size=11),
                     text_color=("#6b7280","#8892a4")).pack(fill="x",padx=14,pady=(3,2))
        self._edm=ctk.CTkComboBox(f,values=MONTH_NAMES,height=36,corner_radius=6); self._edm.set(MONTH_NAMES[0]); self._edm.pack(fill="x",padx=14,pady=(0,4))
        ctk.CTkLabel(f,text="Day of Month (for calendar)",anchor="w",font=ctk.CTkFont(size=11),
                     text_color=("#6b7280","#8892a4")).pack(fill="x",padx=14,pady=(3,2))
        self._eday=ctk.CTkComboBox(f,values=[str(i) for i in range(1,32)],height=36,corner_radius=6,width=90); self._eday.set("1"); self._eday.pack(anchor="w",padx=14,pady=(0,4))
        tags_f=ctk.CTkFrame(f,fg_color="transparent"); tags_f.pack(fill="x",padx=14,pady=(3,4))
        self._rv=tk.BooleanVar(value=True); self._vv=tk.BooleanVar(value=False)
        ctk.CTkCheckBox(tags_f,text="Recurring",variable=self._rv,font=ctk.CTkFont(size=11),checkbox_width=17,checkbox_height=17).pack(side="left",padx=(0,10))
        ctk.CTkCheckBox(tags_f,text="Variable ≈",variable=self._vv,font=ctk.CTkFont(size=11),checkbox_width=17,checkbox_height=17,fg_color=WARNING,hover_color="#cc8800").pack(side="left")
        ctk.CTkLabel(f,text="Notes",anchor="w",font=ctk.CTkFont(size=11)).pack(fill="x",padx=14,pady=(3,2))
        self._enotes=ctk.CTkTextbox(f,height=55,corner_radius=6); self._enotes.pack(fill="x",padx=14,pady=(0,4))
        abtn(f,"+ Add Expense",self._add,height=40).pack(fill="x",padx=14,pady=(5,14))

    def _add(self):
        name=self._en.get().strip()
        if not name: messagebox.showwarning("Missing","Enter a name.",parent=self); return
        try: amt=float(self._ea.get().replace(",","").replace("$",""))
        except: messagebox.showwarning("Invalid","Enter a valid amount.",parent=self); return
        freq_key=FREQ_TO_KEY.get(self._ef.get(),"monthly")
        dm=MONTH_NAMES.index(self._edm.get())+1 if self._edm.get() in MONTH_NAMES else 1
        notes=self._enotes.get("1.0","end-1c").strip()
        try: day=int(self._eday.get())
        except: day=1
        self.app.data.setdefault("expenses",[]).append({
            "id":secrets.token_hex(8),"name":name,"category":self._ec.get(),"amount":amt,
            "frequency":freq_key,"due_month":dm,"day_of_month":day,
            "recurring":self._rv.get(),"variable":self._vv.get(),"notes":notes,"created":now_str()})
        self._en.delete(0,"end"); self._ea.delete(0,"end"); self._enotes.delete("1.0","end")
        self._refresh_list(); self._update_totals()

    def _refresh_list(self):
        for w in self._list_f.winfo_children(): w.destroy()
        cf=self._fcat.get(); ff=self._ffreq.get()
        exps=[e for e in self.app.data.get("expenses",[]) if(cf=="All" or e.get("category")==cf) and(ff=="All" or KEY_TO_LABEL.get(e.get("frequency","monthly"),"Monthly")==ff)]
        if not exps: ctk.CTkLabel(self._list_f,text="No expenses match the filter.",text_color=("#9ca3af","#6b7280")).pack(pady=20); return
        hdr=ctk.CTkFrame(self._list_f,fg_color=("#e2e8f0","#2d3446"),corner_radius=6); hdr.pack(fill="x",padx=4,pady=(6,3))
        for t,w in[("Name",150),("Category",100),("Amount",90),("Frequency",88),("Monthly≈",82),("Tags",48),("",36)]:
            ctk.CTkLabel(hdr,text=t,font=ctk.CTkFont(size=11,weight="bold"),width=w,anchor="w").pack(side="left",padx=5,pady=5)
        for e in exps: self._exp_row(e)

    def _exp_row(self, e):
        row=card(self._list_f); row.pack(fill="x",padx=4,pady=2); row.configure(cursor="hand2")
        freq=e.get("frequency","monthly"); amt=float(e.get("amount",0))
        ctk.CTkLabel(row,text=e.get("name",""),width=150,anchor="w").pack(side="left",padx=(10,4),pady=8)
        ctk.CTkLabel(row,text=e.get("category",""),width=100,anchor="w",text_color=(ACCENT,"#a09bff"),font=ctk.CTkFont(size=10)).pack(side="left",padx=4)
        ctk.CTkLabel(row,text=fmt(amt),width=90,anchor="e",font=ctk.CTkFont(weight="bold"),text_color=(DANGER,DANGER)).pack(side="left",padx=4)
        fc=("#3b82f6","#60a5fa") if freq=="monthly" else("#f59e0b","#fbbf24") if freq=="annual" else("#8b5cf6","#a78bfa")
        ctk.CTkLabel(row,text=KEY_TO_LABEL.get(freq,"Monthly"),width=88,text_color=fc,font=ctk.CTkFont(size=10)).pack(side="left",padx=4)
        ctk.CTkLabel(row,text=fmt(exp_monthly(e)),width=82,anchor="e",font=ctk.CTkFont(size=10),text_color=("#6b7280","#8892a4")).pack(side="left",padx=4)
        tags="".join(["🔄" if e.get("recurring") else "","≈" if e.get("variable") else "","📝" if e.get("notes") else ""])
        ctk.CTkLabel(row,text=tags,width=48,font=ctk.CTkFont(size=11)).pack(side="left",padx=4)
        def delete(eid=e.get("id")):
            if messagebox.askyesno("Delete",f"Remove '{e.get('name','')}'?",parent=self):
                self.app.data["expenses"]=[x for x in self.app.data.get("expenses",[]) if x.get("id")!=eid]
                self._refresh_list(); self._update_totals()
        ctk.CTkButton(row,text="✕",width=30,height=30,fg_color="transparent",hover_color=("#fecaca","#3d1515"),text_color=(DANGER,DANGER),command=delete).pack(side="right",padx=6)
        def on_click(_=None): edit_item_dialog(self,self.app,e,"expenses",lambda:(self._refresh_list(),self._update_totals()),title_prefix="Edit Expense")
        for w in(row,*row.winfo_children()): w.bind("<Button-1>",on_click)

    def _update_totals(self):
        self._mon_lbl.configure(text=f"Monthly: {fmt(self.app.monthly_bills_only())}  |  Equiv: {fmt(self.app.monthly_equiv())}")
        self._ann_lbl.configure(text=f"Annual: {fmt(self.app.annual_total())}")


# ── Calendar Page ──────────────────────────────────────────────────────────────
class CalendarPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self.year=datetime.datetime.now().year; self._build()

    def _build(self):
        hdr=ctk.CTkFrame(self,fg_color="transparent"); hdr.pack(fill="x",padx=25,pady=(20,8))
        ctk.CTkLabel(hdr,text="Expense Calendar",font=ctk.CTkFont(size=24,weight="bold")).pack(side="left")
        # Year nav
        nav=ctk.CTkFrame(hdr,fg_color="transparent"); nav.pack(side="right")
        ctk.CTkButton(nav,text="◀",width=36,height=36,corner_radius=8,fg_color=("#e2e8f0","#2d3446"),text_color=("#374151","#d1d5db"),hover_color=("#d1d5db","#374151"),command=self._prev).pack(side="left",padx=2)
        self._ylbl=ctk.CTkLabel(nav,text=str(self.year),font=ctk.CTkFont(size=16,weight="bold"),width=60); self._ylbl.pack(side="left",padx=8)
        ctk.CTkButton(nav,text="▶",width=36,height=36,corner_radius=8,fg_color=("#e2e8f0","#2d3446"),text_color=("#374151","#d1d5db"),hover_color=("#d1d5db","#374151"),command=self._next).pack(side="left",padx=2)
        # Totals
        ann=self.app.annual_total(); inc=self.app.annual_income()
        info=ctk.CTkFrame(hdr,fg_color="transparent"); info.pack(side="right",padx=20)
        ctk.CTkLabel(info,text=f"Annual Exp: {fmt(ann)}",font=ctk.CTkFont(size=12,weight="bold"),text_color=DANGER).pack(anchor="e")
        ctk.CTkLabel(info,text=f"Annual Inc: {fmt(inc)}",font=ctk.CTkFont(size=12,weight="bold"),text_color=SUCCESS).pack(anchor="e")
        self._grid=ctk.CTkScrollableFrame(self,fg_color="transparent"); self._grid.pack(fill="both",expand=True,padx=25,pady=5)
        self._render()

    def _prev(self): self.year-=1; self._ylbl.configure(text=str(self.year)); self._render()
    def _next(self): self.year+=1; self._ylbl.configure(text=str(self.year)); self._render()

    def _render(self):
        for w in self._grid.winfo_children(): w.destroy()
        now=datetime.datetime.now(); cm=now.month if now.year==self.year else -1
        for col in range(4): self._grid.columnconfigure(col,weight=1)
        for i,mname in enumerate(MONTH_NAMES): self._month_card(self._grid,mname,i+1,i//4,i%4,i+1==cm)

    def _month_card(self, parent, mname, mnum, row, col, is_current):
        c=ctk.CTkFrame(parent,fg_color=("#ffffff","#1a1d27"),corner_radius=12,
                       border_width=2 if is_current else 0,border_color=(ACCENT,"#6c63ff"))
        c.grid(row=row,column=col,padx=6,pady=6,sticky="nsew")
        # Header
        mhdr=ctk.CTkFrame(c,fg_color=(ACCENT if is_current else "#2d3446","#2d3446" if not is_current else ACCENT),corner_radius=8)
        mhdr.pack(fill="x",padx=8,pady=(10,4))
        exps=[(e,amount_for_month(e,mnum)) for e in self.app.data.get("expenses",[]) if mnum in months_for_expense(e)]
        incs=[(i,amount_for_month(i,mnum)) for i in self.app.data.get("income",[])   if mnum in months_for_expense(i)]
        exp_total=sum(m for _,m in exps); inc_total=sum(m for _,m in incs)
        ctk.CTkLabel(mhdr,text=mname,font=ctk.CTkFont(size=12,weight="bold"),text_color="white").pack(side="left",padx=8,pady=5)
        ctk.CTkLabel(mhdr,text=fmt(exp_total),font=ctk.CTkFont(size=10,weight="bold"),text_color="#ffaaaa").pack(side="right",padx=8)
        # Income section
        if incs:
            if_=ctk.CTkFrame(c,fg_color="transparent"); if_.pack(fill="x",padx=6,pady=(4,0))
            for i,_ in incs[:2]:
                r=ctk.CTkFrame(if_,fg_color="transparent"); r.pack(fill="x",pady=1)
                nm=i.get("name",""); nm=nm[:16]+"…" if len(nm)>16 else nm
                dol=i.get("day_of_month",1)
                day_txt=f" ({day_label(dol)})" if dol else ""
                ctk.CTkLabel(r,text=f"💵 {nm}{day_txt}",font=ctk.CTkFont(size=9),anchor="w",
                             text_color=(SUCCESS,"#4ade80")).pack(side="left",fill="x",expand=True)
                ctk.CTkLabel(r,text=fmt(float(i.get("amount",0))),font=ctk.CTkFont(size=9,weight="bold"),
                             text_color=(SUCCESS,"#4ade80")).pack(side="right")
        # Expense section
        if not exps:
            ctk.CTkLabel(c,text="No expenses",font=ctk.CTkFont(size=10),text_color=("#9ca3af","#6b7280")).pack(pady=6)
        else:
            ctk.CTkFrame(c,height=1,fg_color=("#e2e8f0","#2d3446")).pack(fill="x",padx=6,pady=3)
            for e,_ in exps[:5]:
                r=ctk.CTkFrame(c,fg_color="transparent",cursor="hand2"); r.pack(fill="x",padx=6,pady=1)
                nm=e.get("name",""); nm=nm[:16]+"…" if len(nm)>16 else nm
                dol=e.get("day_of_month",1); day_txt=f" ({day_label(dol)})" if dol else ""
                tags=("≈" if e.get("variable") else "")+("🔄" if e.get("recurring") else "")
                ctk.CTkLabel(r,text=f"{tags}{nm}{day_txt}",font=ctk.CTkFont(size=9),anchor="w",
                             text_color=("#374151","#d1d5db")).pack(side="left",fill="x",expand=True)
                ctk.CTkLabel(r,text=fmt(float(e.get("amount",0))),font=ctk.CTkFont(size=9,weight="bold"),
                             text_color=(DANGER,DANGER)).pack(side="right")
                def on_exp_click(_=None,ex=e): edit_item_dialog(self,self.app,ex,"expenses",self._render,title_prefix="Edit Expense")
                for w in(r,*r.winfo_children()): w.bind("<Button-1>",on_exp_click)
            if len(exps)>5: ctk.CTkLabel(c,text=f"+ {len(exps)-5} more…",font=ctk.CTkFont(size=9),text_color=("#9ca3af","#6b7280")).pack(pady=(1,0))
        # Footer totals
        ctk.CTkFrame(c,height=1,fg_color=("#e2e8f0","#2d3446")).pack(fill="x",padx=6,pady=4)
        ft=ctk.CTkFrame(c,fg_color="transparent"); ft.pack(fill="x",padx=8,pady=(0,8))
        ctk.CTkLabel(ft,text=f"In: {fmt(inc_total)}",font=ctk.CTkFont(size=9,weight="bold"),text_color=(SUCCESS,SUCCESS)).pack(side="left")
        net=inc_total-exp_total; nc=SUCCESS if net>=0 else DANGER
        ctk.CTkLabel(ft,text=f"Net: {fmt(net)}",font=ctk.CTkFont(size=9,weight="bold"),text_color=(nc,nc)).pack(side="right")


# ── Goals Page ─────────────────────────────────────────────────────────────────
class GoalsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self._build()

    def _build(self):
        ctk.CTkLabel(self,text="Financial Goals",font=ctk.CTkFont(size=24,weight="bold")).pack(anchor="w",padx=25,pady=(20,5))
        ctk.CTkLabel(self,text="Set targets and track your progress.",font=ctk.CTkFont(size=11),text_color=("#9ca3af","#6b7280")).pack(anchor="w",padx=25,pady=(0,14))
        body=ctk.CTkFrame(self,fg_color="transparent"); body.pack(fill="both",expand=True,padx=25,pady=5)
        form=card(body); form.pack(side="left",fill="y",padx=(0,10)); form.configure(width=280); form.pack_propagate(False)
        ctk.CTkLabel(form,text="New Goal",font=ctk.CTkFont(size=14,weight="bold")).pack(padx=14,pady=(14,10))
        self._gn=lbl_entry(form,"Goal Name","e.g. Emergency Fund"); self._gt=lbl_entry(form,"Target ($)","50000"); self._gc=lbl_entry(form,"Current Amount ($)","0")
        abtn(form,"+ Add Goal",self._add,color=SUCCESS,height=42).pack(fill="x",padx=14,pady=(8,14))
        self._sc=ctk.CTkScrollableFrame(body,fg_color="transparent"); self._sc.pack(side="right",fill="both",expand=True)
        self._refresh()

    def _add(self):
        n=self._gn.get().strip()
        if not n: messagebox.showwarning("Missing","Enter a goal name.",parent=self); return
        try: t=float(self._gt.get().replace(",","").replace("$","")); c=float(self._gc.get().replace(",","").replace("$","") or "0")
        except: messagebox.showwarning("Invalid","Enter valid amounts.",parent=self); return
        self.app.data.setdefault("goals",[]).append({"id":secrets.token_hex(8),"name":n,"target":t,"current":c,"created":now_str()})
        self._gn.delete(0,"end"); self._gt.delete(0,"end"); self._gc.delete(0,"end"); self._refresh()

    def _refresh(self):
        for w in self._sc.winfo_children(): w.destroy()
        goals=self.app.data.get("goals",[])
        if not goals: ctk.CTkLabel(self._sc,text="No goals yet. Add one!",text_color=("#9ca3af","#6b7280")).pack(pady=30); return
        for g in goals: self._goal_card(g)

    def _goal_card(self, g):
        c=card(self._sc); c.pack(fill="x",pady=8)
        hdr=ctk.CTkFrame(c,fg_color="transparent"); hdr.pack(fill="x",padx=14,pady=(12,6))
        ctk.CTkLabel(hdr,text=g.get("name",""),font=ctk.CTkFont(size=14,weight="bold")).pack(side="left")
        t=float(g.get("target",0)); cur=float(g.get("current",0)); pct=min(cur/t*100,100) if t else 0
        pc=SUCCESS if pct>=100 else(ACCENT if pct>=50 else WARNING)
        ctk.CTkLabel(hdr,text=f"{pct:.1f}%",font=ctk.CTkFont(size=14,weight="bold"),text_color=pc).pack(side="right")
        pb=ctk.CTkProgressBar(c,height=14,corner_radius=7,progress_color=pc); pb.set(pct/100); pb.pack(fill="x",padx=14,pady=(0,8))
        info=ctk.CTkFrame(c,fg_color="transparent"); info.pack(fill="x",padx=14,pady=(0,10))
        for txt,col in[(f"Current: {fmt(cur)}",SUCCESS),(f"Target: {fmt(t)}",("#6b7280","#8892a4")),(f"Remaining: {fmt(max(t-cur,0))}",WARNING)]:
            ctk.CTkLabel(info,text=txt,font=ctk.CTkFont(size=12),text_color=col).pack(side="left",padx=(0,16))
        ef=ctk.CTkFrame(c,fg_color=("#f8f9fc","#21253a"),corner_radius=6); ef.pack(fill="x",padx=14,pady=(0,12))
        ctk.CTkLabel(ef,text="Update current:",font=ctk.CTkFont(size=10)).pack(side="left",padx=10,pady=6)
        uv=tk.StringVar(value=str(cur)); ue=ctk.CTkEntry(ef,textvariable=uv,width=110,height=30,justify="right"); ue.pack(side="left",padx=4)
        def upd(gid=g.get("id")):
            try:
                v=float(uv.get().replace(",","").replace("$",""))
                for gg in self.app.data.get("goals",[]):
                    if gg.get("id")==gid: gg["current"]=v
                self._refresh()
            except: pass
        ue.bind("<Return>",lambda _:upd())
        abtn(ef,"Update",upd,color=SUCCESS,height=30,width=70).pack(side="left",padx=4)
        def delete(gid=g.get("id")):
            self.app.data["goals"]=[gg for gg in self.app.data.get("goals",[]) if gg.get("id")!=gid]; self._refresh()
        ctk.CTkButton(ef,text="✕ Remove",width=90,height=30,fg_color="transparent",hover_color=("#fecaca","#3d1515"),text_color=(DANGER,DANGER),command=delete).pack(side="right",padx=8)


# ── History Page ───────────────────────────────────────────────────────────────
class HistoryPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self._build()

    def _build(self):
        ctk.CTkLabel(self,text="History & Snapshots",font=ctk.CTkFont(size=24,weight="bold")).pack(anchor="w",padx=25,pady=(20,5))
        ctk.CTkLabel(self,text="Every save creates a timestamped snapshot.",font=ctk.CTkFont(size=11),text_color=("#9ca3af","#6b7280")).pack(anchor="w",padx=25,pady=(0,14))
        body=ctk.CTkFrame(self,fg_color="transparent"); body.pack(fill="both",expand=True,padx=25,pady=5)
        left=card(body); left.configure(width=280); left.pack(side="left",fill="y",padx=(0,10)); left.pack_propagate(False)
        ctk.CTkLabel(left,text="Saved Snapshots",font=ctk.CTkFont(size=13,weight="bold")).pack(padx=14,pady=12)
        self._snap_sc=ctk.CTkScrollableFrame(left,fg_color="transparent"); self._snap_sc.pack(fill="both",expand=True,padx=6,pady=6)
        self._detail=card(body); self._detail.pack(side="right",fill="both",expand=True)
        ctk.CTkLabel(self._detail,text="Select a snapshot to view details",text_color=("#9ca3af","#6b7280"),font=ctk.CTkFont(size=13)).pack(expand=True)
        self._populate()

    def _populate(self):
        for w in self._snap_sc.winfo_children(): w.destroy()
        snaps=self.app.dm.history()
        if not snaps: ctk.CTkLabel(self._snap_sc,text="No snapshots.\nSave data first.",text_color=("#9ca3af","#6b7280"),font=ctk.CTkFont(size=11)).pack(pady=20); return
        for s in snaps:
            btn=ctk.CTkFrame(self._snap_sc,fg_color=("#f8f9fc","#21253a"),corner_radius=8,cursor="hand2"); btn.pack(fill="x",pady=3)
            ctk.CTkLabel(btn,text=s.get("date",s["file"]),font=ctk.CTkFont(size=11),text_color=("#374151","#d1d5db")).pack(anchor="w",padx=10,pady=(8,2))
            ctk.CTkLabel(btn,text=s["file"],font=ctk.CTkFont(size=9),text_color=("#9ca3af","#6b7280")).pack(anchor="w",padx=10,pady=(0,8))
            for w in(btn,*btn.winfo_children()): w.bind("<Button-1>",lambda _,ss=s:self._show_detail(ss))

    def _show_detail(self, snap):
        for w in self._detail.winfo_children(): w.destroy()
        try: data=self.app.dm.load_snap(snap["path"])
        except Exception as ex: ctk.CTkLabel(self._detail,text=f"Error: {ex}").pack(pady=20); return
        hdr=ctk.CTkFrame(self._detail,fg_color="transparent"); hdr.pack(fill="x",padx=14,pady=12)
        ctk.CTkLabel(hdr,text=snap.get("date","Snapshot"),font=ctk.CTkFont(size=14,weight="bold")).pack(side="left")
        ef=ctk.CTkFrame(hdr,fg_color="transparent"); ef.pack(side="right")
        abtn(ef,"📊 CSV",lambda:self._csv(data,snap),color="#27ae60",height=30,width=90).pack(side="left",padx=3)
        if REPORTLAB_OK: abtn(ef,"📄 PDF",lambda:self._pdf(data,snap),color="#e74c3c",height=30,width=90).pack(side="left",padx=3)
        sc=ctk.CTkScrollableFrame(self._detail,fg_color="transparent"); sc.pack(fill="both",expand=True,padx=10)
        nw=data.get("net_worth",{})
        total=sum(float(i.get("value",0)) for cat in("banks","crypto","stocks","assets") for i in nw.get(cat,[]))
        ctk.CTkLabel(sc,text=f"Net Worth: {fmt(total)}",font=ctk.CTkFont(size=16,weight="bold"),text_color=SUCCESS).pack(anchor="w",pady=6)
        for key,lbl,color in[("banks","Banks",ACCENT),("crypto","Crypto",GOLD),("stocks","Stocks",SUCCESS),("assets","Assets",ACCENT2)]:
            items=nw.get(key,[])
            if items:
                ctk.CTkLabel(sc,text=lbl,font=ctk.CTkFont(size=12,weight="bold"),text_color=color).pack(anchor="w",pady=(8,3))
                for it in items:
                    r=ctk.CTkFrame(sc,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",pady=1)
                    ctk.CTkLabel(r,text=it.get("name",""),anchor="w").pack(side="left",padx=10,pady=5)
                    ctk.CTkLabel(r,text=fmt(it.get("value",0)),font=ctk.CTkFont(weight="bold")).pack(side="right",padx=10)
        inc=data.get("income",[])
        if inc:
            ctk.CTkLabel(sc,text="Income",font=ctk.CTkFont(size=14,weight="bold"),text_color=SUCCESS).pack(anchor="w",pady=(14,5))
            for i in inc:
                r=ctk.CTkFrame(sc,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",pady=1)
                ctk.CTkLabel(r,text=i.get("name",""),anchor="w").pack(side="left",padx=10,pady=5)
                ctk.CTkLabel(r,text=f"{fmt(float(i.get('amount',0)))} / {KEY_TO_LABEL.get(i.get('frequency','monthly'),'Monthly')}",text_color=(SUCCESS,SUCCESS)).pack(side="right",padx=10)
        exps=data.get("expenses",[])
        if exps:
            ctk.CTkLabel(sc,text="Expenses",font=ctk.CTkFont(size=14,weight="bold")).pack(anchor="w",pady=(14,5))
            for e in exps:
                r=ctk.CTkFrame(sc,fg_color=("#f8f9fc","#21253a"),corner_radius=6); r.pack(fill="x",pady=1)
                ctk.CTkLabel(r,text=e.get("name",""),anchor="w").pack(side="left",padx=10,pady=5)
                ctk.CTkLabel(r,text=f"{fmt(float(e.get('amount',0)))} / {KEY_TO_LABEL.get(e.get('frequency','monthly'),'Monthly')}",text_color=(DANGER,DANGER)).pack(side="right",padx=10)

    def _csv(self, data, snap):
        path=filedialog.asksaveasfilename(defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile=f"IRIS_Snap_{snap['file'].replace('.json','')}.csv",parent=self)
        if not path: return
        try:
            with open(path,"w",newline="",encoding="utf-8") as f:
                w=csv.writer(f); w.writerow([APP_NAME,"Snapshot"]); w.writerow(["Date:",snap.get("date","")]); w.writerow([])
                w.writerow(["INCOME"]); w.writerow(["Name","Category","Amount","Frequency"])
                for i in data.get("income",[]): w.writerow([i.get("name",""),i.get("category",""),i.get("amount",0),i.get("frequency","")])
                w.writerow([]); w.writerow(["NET WORTH"]); w.writerow(["Category","Name","Value"])
                nwd=data.get("net_worth",{})
                for key,lbl in[("banks","Bank"),("crypto","Crypto"),("stocks","Stocks"),("assets","Asset")]:
                    for it in nwd.get(key,[]): w.writerow([lbl,it.get("name",""),it.get("value",0)])
                w.writerow([]); w.writerow(["EXPENSES"]); w.writerow(["Name","Category","Amount","Frequency"])
                for e in data.get("expenses",[]): w.writerow([e.get("name",""),e.get("category",""),e.get("amount",0),e.get("frequency","")])
            messagebox.showinfo("Exported",f"Saved to:\n{path}",parent=self)
        except Exception as ex: messagebox.showerror("Error",str(ex),parent=self)

    def _pdf(self, data, snap):
        path=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")],initialfile=f"IRIS_Snap_{snap['file'].replace('.json','')}.pdf",parent=self)
        if not path: return
        class FA:
            username=self.app.username
            def __init__(s,d): s.data=d
            def total_net_worth(s): return sum(float(i.get("value",0)) for cat in("banks","crypto","stocks","assets") for i in s.data.get("net_worth",{}).get(cat,[]))
            def monthly_bills_only(s): return sum(float(e.get("amount",0)) for e in s.data.get("expenses",[]) if e.get("frequency","monthly")=="monthly")
            def monthly_equiv(s): return sum(exp_monthly(e) for e in s.data.get("expenses",[]))
            def annual_total(s): return sum(exp_annual(e) for e in s.data.get("expenses",[]))
            def monthly_income(s): return sum(exp_monthly(i) for i in s.data.get("income",[]))
            def annual_income(s): return sum(exp_annual(i) for i in s.data.get("income",[]))
        try: _generate_pdf(path,FA(data)); messagebox.showinfo("Exported",f"PDF saved:\n{path}",parent=self)
        except Exception as ex: messagebox.showerror("Error",str(ex),parent=self)


# ── Settings Page ──────────────────────────────────────────────────────────────
class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent,fg_color="transparent"); self.app=app; self._build()

    def _build(self):
        ctk.CTkLabel(self,text="Settings",font=ctk.CTkFont(size=24,weight="bold")).pack(anchor="w",padx=25,pady=(20,15))
        sc=ctk.CTkScrollableFrame(self,fg_color="transparent"); sc.pack(fill="both",expand=True,padx=25,pady=5)
        for builder in [self._build_profile, self._build_appearance, self._build_account,
                        self._build_data, self._build_tips, self._build_about]:
            try: builder(sc)
            except Exception as ex:
                ctk.CTkLabel(sc,text=f"⚠ Section error: {ex}",
                             text_color=DANGER,font=ctk.CTkFont(size=11)).pack(anchor="w",padx=8,pady=4)

    def _build_profile(self, sc):
        section_lbl(sc,"👤  Profile & Avatar")
        pc=card(sc); pc.pack(fill="x",pady=(4,16))
        pr=ctk.CTkFrame(pc,fg_color="transparent"); pr.pack(fill="x",padx=14,pady=14)
        # Avatar container — always a fixed-size frame, never configure a label with fg_color
        self._av_wrap=ctk.CTkFrame(pr,width=64,height=64,fg_color="transparent"); self._av_wrap.pack(side="left",padx=(0,16)); self._av_wrap.pack_propagate(False)
        self._draw_settings_avatar()
        info=ctk.CTkFrame(pr,fg_color="transparent"); info.pack(side="left",fill="both",expand=True)
        ctk.CTkLabel(info,text=self.app.username,font=ctk.CTkFont(size=14,weight="bold")).pack(anchor="w")
        ctk.CTkLabel(info,text="Personal Finance Account",font=ctk.CTkFont(size=11),text_color=("#6b7280","#8892a4")).pack(anchor="w",pady=(2,8))
        bf=ctk.CTkFrame(info,fg_color="transparent"); bf.pack(anchor="w")
        abtn(bf,"📷 Upload Photo",self._upload_avatar,height=34,width=140).pack(side="left",padx=(0,8))
        if self.app.dm.avatar_path().exists():
            ghost_btn(bf,"Remove",self._remove_avatar,height=34,width=80).pack(side="left")

    def _draw_settings_avatar(self):
        for w in self._av_wrap.winfo_children(): w.destroy()
        ap=self.app.dm.avatar_path()
        if ap.exists() and PIL_OK:
            ph=make_avatar(str(ap),60)
            if ph:
                lbl=ctk.CTkLabel(self._av_wrap,image=ph,text="",width=60,height=60)
                lbl.image=ph; lbl.pack(expand=True); return
        # Initials fallback
        initials_avatar(self._av_wrap, self.app.username, 60)

    def _build_appearance(self, sc):
        section_lbl(sc,"🎨  Appearance")
        ap=card(sc); ap.pack(fill="x",pady=(4,16))

        # Theme row — three toggle buttons (compatible with all CTk 5.x)
        r1=ctk.CTkFrame(ap,fg_color="transparent"); r1.pack(fill="x",padx=14,pady=(14,6))
        ctk.CTkLabel(r1,text="Theme",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        btn_row=ctk.CTkFrame(r1,fg_color="transparent"); btn_row.pack(side="right")
        current=self.app.sm.get("theme","dark")
        self._theme_btns={}
        for val,label in [("light","☀ Light"),("dark","🌙 Dark"),("system","⚙ System")]:
            active = (val==current)
            b=ctk.CTkButton(btn_row,text=label,width=90,height=34,corner_radius=8,
                            fg_color=ACCENT if active else ("#e2e8f0","#2d3446"),
                            hover_color=_HOVER.get(ACCENT,ACCENT) if active else ("#d1d5db","#374151"),
                            text_color="white" if active else ("#374151","#d1d5db"),
                            font=ctk.CTkFont(size=11,weight="bold"),
                            command=lambda v=val: self._set_theme(v))
            b.pack(side="left",padx=2); self._theme_btns[val]=b

        divider(ap)

        # Currency symbol row
        r2=ctk.CTkFrame(ap,fg_color="transparent"); r2.pack(fill="x",padx=14,pady=10)
        ctk.CTkLabel(r2,text="Currency Symbol",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        cur_var=tk.StringVar(value=self.app.sm.get("currency","$"))
        cur_cb=ctk.CTkComboBox(r2,values=["$","€","£","¥","₹","₩","C$","A$"],
                               variable=cur_var,width=80,height=34,
                               command=lambda v: self.app.sm.set("currency",v))
        cur_cb.pack(side="right")

        divider(ap)

        # Date format row
        r3=ctk.CTkFrame(ap,fg_color="transparent"); r3.pack(fill="x",padx=14,pady=10)
        ctk.CTkLabel(r3,text="Date Format",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        fmt_var=tk.StringVar(value=self.app.sm.get("date_fmt","MM/DD/YYYY"))
        fmt_cb=ctk.CTkComboBox(r3,values=["MM/DD/YYYY","DD/MM/YYYY","YYYY-MM-DD"],
                               variable=fmt_var,width=130,height=34,
                               command=lambda v: self.app.sm.set("date_fmt",v))
        fmt_cb.pack(side="right")

    def _build_account(self, sc):
        section_lbl(sc,"🔐  Account")
        ac=card(sc); ac.pack(fill="x",pady=(4,16))
        for lbl,val in[("Username",self.app.username),("Data Location",str(self.app.dm.user_dir))]:
            r=ctk.CTkFrame(ac,fg_color="transparent"); r.pack(fill="x",padx=14,pady=8)
            ctk.CTkLabel(r,text=lbl,font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
            ctk.CTkLabel(r,text=val,text_color=("#6b7280","#8892a4"),font=ctk.CTkFont(size=11)).pack(side="right")
            divider(ac)
        rp=ctk.CTkFrame(ac,fg_color="transparent"); rp.pack(fill="x",padx=14,pady=8)
        ctk.CTkLabel(rp,text="Password",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        abtn(rp,"Change Password",self._change_pw,height=34,width=150).pack(side="right")
        divider(ac)
        rsq=ctk.CTkFrame(ac,fg_color="transparent"); rsq.pack(fill="x",padx=14,pady=8)
        ctk.CTkLabel(rsq,text="Security Question",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        abtn(rsq,"Update",self._update_sq,height=34,width=100).pack(side="right")

    def _build_data(self, sc):
        section_lbl(sc,"💾  Data Management")
        dm=card(sc); dm.pack(fill="x",pady=(4,16))
        snaps=self.app.dm.history()
        for lbl,val in[("Snapshots",f"{len(snaps)} saved"),("Auto-save","On every manual save")]:
            r=ctk.CTkFrame(dm,fg_color="transparent"); r.pack(fill="x",padx=14,pady=8)
            ctk.CTkLabel(r,text=lbl,font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
            ctk.CTkLabel(r,text=val,text_color=("#6b7280","#8892a4")).pack(side="right"); divider(dm)
        rs=ctk.CTkFrame(dm,fg_color="transparent"); rs.pack(fill="x",padx=14,pady=8)
        ctk.CTkLabel(rs,text="Save Now",font=ctk.CTkFont(size=13,weight="bold")).pack(side="left")
        abtn(rs,"💾 Save",self.app._save,color=SUCCESS,height=34,width=110).pack(side="right")

    def _build_tips(self, sc):
        section_lbl(sc,"💡  Tips")
        tip=card(sc); tip.pack(fill="x",pady=(4,16))
        ctk.CTkLabel(tip,text=(
            "Variable Bills (electric, water, groceries):\n"
            "• Add with your 3–6 month average and check 'Variable ≈'\n"
            "• The ≈ icon reminds you it's an estimate — update it quarterly\n\n"
            "Income Tips:\n"
            "• Use 'Bi-Weekly' for bi-weekly paychecks — the app calculates the monthly equiv. automatically\n"
            "• Rental income → use 'Monthly' with the day rent is received as 'Day of Month'\n"
            "• Investment income → use 'Quarterly' or 'Annual' as appropriate"),
            font=ctk.CTkFont(size=11),text_color=("#374151","#d1d5db"),
            justify="left",wraplength=750).pack(anchor="w",padx=14,pady=12)

    def _build_about(self, sc):
        section_lbl(sc,"ℹ️  About")
        ab=card(sc); ab.pack(fill="x",pady=(4,20))
        for lbl,val in[("App",APP_NAME),("Version",APP_VERSION),
                       ("Charts","Matplotlib ✓" if MATPLOTLIB_OK else "Not installed"),
                       ("PDF","ReportLab ✓" if REPORTLAB_OK else "Not installed")]:
            r=ctk.CTkFrame(ab,fg_color="transparent"); r.pack(fill="x",padx=14,pady=6)
            ctk.CTkLabel(r,text=lbl,font=ctk.CTkFont(size=12,weight="bold")).pack(side="left")
            ctk.CTkLabel(r,text=val,text_color=("#6b7280","#8892a4")).pack(side="right"); divider(ab)

    def _upload_avatar(self):
        path=filedialog.askopenfilename(filetypes=[("Images","*.png *.jpg *.jpeg *.webp *.bmp"),("All","*.*")],parent=self)
        if not path: return
        try:
            img=Image.open(path).convert("RGBA")
            size=min(img.width,img.height); left=(img.width-size)//2; top=(img.height-size)//2
            img=img.crop((left,top,left+size,top+size)).resize((256,256),Image.LANCZOS)
            img.save(str(self.app.dm.avatar_path()))
            self._draw_settings_avatar(); self.app.refresh_avatar()
            messagebox.showinfo("Done","Profile picture updated!",parent=self)
        except Exception as ex: messagebox.showerror("Error",str(ex),parent=self)

    def _remove_avatar(self):
        ap=self.app.dm.avatar_path()
        if ap.exists(): ap.unlink()
        self._draw_settings_avatar(); self.app.refresh_avatar()

    def _set_theme(self, val):
        val=val.lower(); ctk.set_appearance_mode(val); self.app.sm.set("theme",val)
        for k,b in getattr(self,"_theme_btns",{}).items():
            active=(k==val)
            b.configure(fg_color=ACCENT if active else ("#e2e8f0","#2d3446"),
                        hover_color=_HOVER.get(ACCENT,ACCENT) if active else ("#d1d5db","#374151"),
                        text_color="white" if active else ("#374151","#d1d5db"))

    def _change_pw(self):
        dlg=ctk.CTkToplevel(self); dlg.title("Change Password"); dlg.geometry("360x260"); dlg.resizable(False,False); dlg.grab_set()
        ctk.CTkLabel(dlg,text="Change Password",font=ctk.CTkFont(size=15,weight="bold")).pack(pady=20)
        op=lbl_entry(dlg,"Current Password","",secret=True); np=lbl_entry(dlg,"New Password","6+ characters",secret=True)
        def do():
            ok,msg=self.app.um.change_pw(self.app.username,op.get(),np.get())
            if ok: messagebox.showinfo("Done",msg,parent=dlg); dlg.destroy()
            else: messagebox.showerror("Error",msg,parent=dlg)
        abtn(dlg,"Change Password",do,height=42).pack(fill="x",padx=22,pady=12)

    def _update_sq(self):
        dlg=ctk.CTkToplevel(self); dlg.title("Security Question"); dlg.geometry("380x260"); dlg.resizable(False,False); dlg.grab_set()
        ctk.CTkLabel(dlg,text="Update Security Question",font=ctk.CTkFont(size=15,weight="bold")).pack(pady=20)
        ctk.CTkLabel(dlg,text="Question",anchor="w").pack(fill="x",padx=22,pady=(4,2))
        qcb=ctk.CTkComboBox(dlg,values=SECURITY_QUESTIONS,height=40); qcb.set(SECURITY_QUESTIONS[0]); qcb.pack(fill="x",padx=22,pady=(0,8))
        ae=lbl_entry(dlg,"Answer","Your answer")
        def do():
            if not ae.get().strip(): messagebox.showwarning("Missing","Enter your answer.",parent=dlg); return
            self.app.um.set_sq(self.app.username,qcb.get(),ae.get()); messagebox.showinfo("Updated","Security question updated.",parent=dlg); dlg.destroy()
        abtn(dlg,"Save",do,height=42).pack(fill="x",padx=22,pady=10)


# ── Entry Point ────────────────────────────────────────────────────────────────
def main():
    um=UserManager(); sm=SettingsManager()
    login=LoginWindow(um,sm); login.mainloop()
    if login.logged_in:
        app=IRISApp(login.logged_in,sm,um); app.mainloop()

if __name__=="__main__":
    main()
