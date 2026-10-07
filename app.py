"""TR Auto • Oficina Online. Compatível com o banco SQLite do sistema original."""
import io
import hashlib
import os
import re
import secrets
import shutil
import sqlite3
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, send_from_directory, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", str(ROOT / "data"))).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / "oficina.db"
TIMEZONE = ZoneInfo(os.environ.get("TZ", "America/Sao_Paulo"))
USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
if not PASSWORD_HASH:
    if len(PASSWORD) < 10:
        raise RuntimeError("Configure ADMIN_PASSWORD com pelo menos 10 caracteres antes de iniciar.")
    PASSWORD_HASH = generate_password_hash(PASSWORD)
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    raise RuntimeError("Configure SECRET_KEY com pelo menos 32 caracteres aleatórios.")

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY, MAX_CONTENT_LENGTH=5 * 1024 * 1024,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "true").lower() == "true",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
if os.environ.get("TRUST_PROXY", "false").lower() == "true":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

STATUSES = ["Aberta", "Em andamento", "Aguardando peças", "Concluída", "Entregue", "Cancelada"]

def now():
    return datetime.now(TIMEZONE)

def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFD", str(value or "").lower())
                   if unicodedata.category(c) != "Mn").strip()

def status_name(value):
    return next((s for s in STATUSES if normalized(s) == normalized(value)), "Aberta")

def status_class(value):
    return {"Aberta": "open", "Em andamento": "progress", "Aguardando peças": "waiting",
            "Concluída": "done", "Entregue": "done", "Cancelada": "cancelled"}[status_name(value)]

def money(value):
    return "R$ " + f"{float(value or 0):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")

def br_date(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(value or "—")

def whatsapp_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) in (10, 11):
        return "55" + digits
    return digits

def paginate(rows, size=30):
    count = len(rows)
    pages = max(1, (count + size - 1) // size)
    try:
        number = max(1, min(int(request.args.get("page", "1")), pages))
    except ValueError:
        number = 1
    args = request.args.to_dict()
    previous = url_for(request.endpoint, **{**args, "page": number-1}) if number > 1 else None
    following = url_for(request.endpoint, **{**args, "page": number+1}) if number < pages else None
    return rows[(number-1)*size:number*size], dict(number=number,pages=pages,count=count,previous=previous,following=following)

def decimal_value(value, name="Valor", maximum=Decimal("100000000")):
    try:
        val = Decimal(str(value or 0).replace(",", "."))
        if not val.is_finite() or val < 0 or val > maximum:
            raise ValueError()
        return val
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}: informe um número válido, maior ou igual a zero.")

def rounded(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=30000")
    return g.db

@app.teardown_appcontext
def close_db(_error):
    conn = g.pop("db", None)
    if conn:
        conn.close()

def init_db():
    # A cópia inicial só acontece quando não existe banco no volume.
    if not DB_PATH.exists() and (ROOT / "seed/oficina.db").exists():
        src = sqlite3.connect(f"file:{ROOT / 'seed/oficina.db'}?mode=ro", uri=True)
        dest = sqlite3.connect(DB_PATH)
        src.backup(dest)
        dest.close()
        src.close()
    db = get_db()
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT);
      CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER NOT NULL,
        plate TEXT,model TEXT,FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE);
      CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,
        price REAL NOT NULL DEFAULT 0,qty REAL NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER NOT NULL,
        vehicle_id INTEGER NOT NULL,notes TEXT,labor REAL NOT NULL DEFAULT 0,total REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'Aberta',created_at TEXT NOT NULL,client_cpf TEXT,client_address TEXT,
        payment_method TEXT,discount_percent REAL NOT NULL DEFAULT 0,discount_value REAL NOT NULL DEFAULT 0,
        total_bruto REAL NOT NULL DEFAULT 0,FOREIGN KEY(client_id) REFERENCES clients(id),
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id));
      CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,
        description TEXT,qty REAL NOT NULL DEFAULT 0,unit_price REAL NOT NULL DEFAULT 0,stock_id INTEGER,
        FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
        FOREIGN KEY(stock_id) REFERENCES stock(id));
      CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT PRIMARY KEY,attempts INTEGER NOT NULL,started_at REAL NOT NULL);
      CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);
      CREATE INDEX IF NOT EXISTS idx_orders_client ON orders(client_id);
      CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
      CREATE INDEX IF NOT EXISTS idx_vehicles_client ON vehicles(client_id);
    """)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(orders)")}
    for column, kind in {"client_cpf":"TEXT", "client_address":"TEXT", "payment_method":"TEXT",
                         "discount_percent":"REAL NOT NULL DEFAULT 0", "discount_value":"REAL NOT NULL DEFAULT 0",
                         "total_bruto":"REAL NOT NULL DEFAULT 0"}.items():
        if column not in cols:
            db.execute(f"ALTER TABLE orders ADD COLUMN {column} {kind}")
    db.commit()

with app.app_context():
    init_db()

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]

@app.before_request
def protect():
    if request.endpoint in ("static", "health"):
        return
    if request.endpoint != "login" and not session.get("user"):
        if request.path.startswith("/api/"):
            return jsonify(error="Faça login para continuar."), 401
        return redirect(url_for("login"))
    if request.method == "POST":
        submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(str(submitted).encode("utf-8"), str(session.get("csrf", "")).encode("utf-8")) or not submitted:
            abort(400, "A sessão do formulário expirou. Atualize a página e tente novamente.")

@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    return response

STATIC_VERSIONS = {
    name: hashlib.sha256((ROOT / 'static' / name).read_bytes()).hexdigest()[:12]
    for name in ('app.css', 'app.js', 'logo-background.png')
}

def static_asset(filename):
    return url_for('static', filename=filename, v=STATIC_VERSIONS[filename])

@app.context_processor
def common():
    return dict(static_asset=static_asset, app_name="TR Auto Elétrica", csrf_token=csrf_token, statuses=STATUSES,
                status_name=status_name, status_class=status_class,
                whatsapp_phone=whatsapp_phone,
                today=now().strftime("%d/%m/%Y"), username=session.get("user"),
                current_year=now().year)

app.jinja_env.filters.update(money=money, brdate=br_date)

@app.get("/health")
def health():
    get_db().execute("SELECT 1").fetchone()
    return jsonify(status="ok")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        db = get_db()
        ip = request.remote_addr or "unknown"
        t = now().timestamp()
        attempt = db.execute("SELECT * FROM login_attempts WHERE ip=?", (ip,)).fetchone()
        if attempt and t - attempt["started_at"] < 900 and attempt["attempts"] >= 10:
            return render_template("login.html", error="Muitas tentativas. Aguarde 15 minutos e tente novamente."), 429
        valid_password = check_password_hash(PASSWORD_HASH, request.form.get("password", ""))
        if secrets.compare_digest(request.form.get("username", "").encode("utf-8"), USERNAME.encode("utf-8")) and valid_password:
            db.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
            db.commit()
            session.clear()
            session["user"] = USERNAME
            session.permanent = True
            return redirect(url_for("index"))
        count = attempt["attempts"] + 1 if attempt and t - attempt["started_at"] < 900 else 1
        started = attempt["started_at"] if attempt and count > 1 else t
        db.execute("INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)", (ip, count, started))
        db.commit()
        error = "Usuário ou senha incorretos."
    return render_template("login.html", error=error)

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

ORDER_JOIN = """SELECT o.*,c.name AS client_name,c.phone,v.plate,v.model FROM orders o
                JOIN clients c ON c.id=o.client_id JOIN vehicles v ON v.id=o.vehicle_id"""

def get_order(order_id):
    row = get_db().execute(ORDER_JOIN + " WHERE o.id=?", (order_id,)).fetchone()
    if not row:
        abort(404)
    return row

@app.get("/")
def index():
    db = get_db()
    prefix = now().strftime("%Y-%m")
    all_orders = db.execute("SELECT status,total,labor,created_at FROM orders").fetchall()
    active = [o for o in all_orders if status_name(o["status"]) in STATUSES[:3]]
    month = [o for o in all_orders if o["created_at"].startswith(prefix) and status_name(o["status"]) != "Cancelada"]
    completed = len([o for o in month if status_name(o["status"]) in ("Concluída", "Entregue")])
    stats = dict(active=len(active), month_count=len(month), completed=completed,
                 month_total=sum(o["total"] for o in month), clients=db.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
                 low=db.execute("SELECT COUNT(*) FROM stock WHERE qty<=3").fetchone()[0])
    chart = []
    for delta in range(6, -1, -1):
        day = (now() - timedelta(days=delta)).date()
        value = sum(o["total"] for o in all_orders if o["created_at"].startswith(day.isoformat()) and status_name(o["status"]) != "Cancelada")
        chart.append(dict(day=day.strftime("%d/%m"), value=value))
    max_value = max([d["value"] for d in chart] + [1])
    for d in chart:
        d["height"] = max(2, round(d["value"] / max_value * 100))
    recent = db.execute(ORDER_JOIN + " ORDER BY o.id DESC LIMIT 6").fetchall()
    counts = [(s, sum(status_name(o["status"]) == s for o in all_orders)) for s in STATUSES[:3]]
    low_items = db.execute("SELECT * FROM stock WHERE qty<=3 ORDER BY qty,name LIMIT 5").fetchall()
    return render_template("index.html", page="Painel", section="dashboard", stats=stats,
                           chart=chart, recent=recent, workflow=counts, low_items=low_items,
                           month_label=now().strftime("%m/%Y"))

@app.get("/os")
def lista_os():
    q = request.args.get("q", "").strip()
    selected = request.args.get("status", "")
    sql = ORDER_JOIN
    args = []
    if q:
        sql += " WHERE c.name LIKE ? OR v.plate LIKE ? OR REPLACE(v.plate,'-','') LIKE ? OR CAST(o.id AS TEXT)=?"
        args = [f"%{q}%", f"%{q}%", f"%{q.upper().replace('-', '').replace(' ', '')}%", q.lstrip("#")]
    rows = get_db().execute(sql + " ORDER BY o.id DESC", args).fetchall()
    if selected in STATUSES:
        rows = [r for r in rows if status_name(r["status"]) == selected]
    rows, pagination = paginate(rows)
    return render_template("os_list.html", page="Ordens de serviço", section="orders", rows=rows, q=q, selected=selected,pagination=pagination)

def read_items():
    descs, qtys, prices = (request.form.getlist(k) for k in ("desc[]", "qty[]", "unit[]"))
    if not len(descs) == len(qtys) == len(prices):
        raise ValueError("Confira as quantidades e valores dos itens.")
    items = []
    for desc, qty, price in zip(descs, qtys, prices):
        if not desc.strip():
            continue
        quantity = decimal_value(qty, "Quantidade")
        if quantity == 0:
            raise ValueError("A quantidade de cada item precisa ser maior que zero.")
        items.append((desc.strip()[:500], quantity, decimal_value(price, "Preço")))
    labor = decimal_value(request.form.get("labor"), "Mão de obra")
    pct = decimal_value(request.form.get("discount_percent"), "Desconto", Decimal("100"))
    parts = sum((q * p for _, q, p in items), Decimal("0"))
    gross = Decimal(str(rounded(parts + labor)))
    discount = Decimal(str(rounded(gross * pct / 100)))
    return items, labor, pct, gross, discount, gross - discount

@app.route("/os/nova", methods=["GET", "POST"])
def nova_os():
    return edit_order(None)

@app.route("/os/<int:order_id>/editar", methods=["GET", "POST"])
def editar_os(order_id):
    return edit_order(order_id)

def edit_order(order_id):
    db = get_db()
    order = get_order(order_id) if order_id else None
    error = None
    draft_items = None
    if request.method == "POST":
        try:
            name, phone, plate, model = [request.form.get(k, "").strip() for k in ("client_name", "phone", "plate", "model")]
            if not name or not plate:
                raise ValueError("Informe o cliente e a placa do veículo.")
            plate = plate.upper()[:20]
            items, labor, pct, gross, discount, total = read_items()
            client_id = request.form.get("client_id", "").strip()
            if client_id:
                client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
                if not client:
                    raise ValueError("Cliente não encontrado. Selecione novamente.")
                # Mantém o cadastro vinculado à OS quando só os itens são editados.
                db.execute("UPDATE clients SET name=?,phone=? WHERE id=?", (name, phone, client_id))
            else:
                client = db.execute("SELECT id FROM clients WHERE name=? AND IFNULL(phone,'')=?", (name, phone)).fetchone()
                if client:
                    client_id = client["id"]
                else:
                    client_id = db.execute("INSERT INTO clients(name,phone) VALUES (?,?)", (name, phone)).lastrowid
            vehicle = db.execute("SELECT * FROM vehicles WHERE client_id=? AND plate=?", (client_id, plate)).fetchone()
            if vehicle:
                vehicle_id = vehicle["id"]
                db.execute("UPDATE vehicles SET model=? WHERE id=?", (model, vehicle_id))
            else:
                vehicle_id = db.execute("INSERT INTO vehicles(client_id,plate,model) VALUES (?,?,?)", (client_id, plate, model)).lastrowid
            values = (client_id, vehicle_id, request.form.get("notes", ""), rounded(labor), rounded(total),
                      request.form.get("cpf", ""), request.form.get("client_address", ""),
                      request.form.get("payment_method", ""), float(pct), rounded(discount), rounded(gross))
            if order_id:
                db.execute("""UPDATE orders SET client_id=?,vehicle_id=?,notes=?,labor=?,total=?,client_cpf=?,
                  client_address=?,payment_method=?,discount_percent=?,discount_value=?,total_bruto=? WHERE id=?""", values + (order_id,))
                db.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
            else:
                order_id = db.execute("""INSERT INTO orders(client_id,vehicle_id,notes,labor,total,client_cpf,
                  client_address,payment_method,discount_percent,discount_value,total_bruto,status,created_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", values + ("Aberta", now().strftime("%Y-%m-%d %H:%M"))).lastrowid
            db.executemany("INSERT INTO order_items(order_id,description,qty,unit_price) VALUES (?,?,?,?)",
                           [(order_id, d, float(q), float(p)) for d, q, p in items])
            db.commit()
            flash("Ordem de serviço salva com sucesso.", "success")
            return redirect(url_for("ver_os", order_id=order_id))
        except ValueError as exc:
            db.rollback()
            error = str(exc)
            draft_items = [dict(description=d, qty=q, unit_price=p) for d,q,p in zip(
                request.form.getlist("desc[]"),request.form.getlist("qty[]"),request.form.getlist("unit[]"))]
        except sqlite3.Error:
            db.rollback()
            raise
    items = draft_items if draft_items is not None else [dict(r) for r in db.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,))] if order_id else []
    clients = [dict(r) for r in db.execute("SELECT * FROM clients ORDER BY name")]
    vehicles = [dict(r) for r in db.execute("SELECT * FROM vehicles ORDER BY model")]
    stock = [dict(r) for r in db.execute("SELECT * FROM stock ORDER BY name")]
    return render_template("os_form.html", page="Editar OS" if order else "Nova ordem de serviço", section="orders",
                           o=order, items=items, clients=clients, vehicles=vehicles, stock=stock, error=error,
                           posted=request.form if request.method == "POST" else {})

@app.get("/os/<int:order_id>")
def ver_os(order_id):
    o = get_order(order_id)
    items = get_db().execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
    parts = sum(r["qty"] * r["unit_price"] for r in items)
    phone = whatsapp_phone(o["phone"])
    return render_template("os_view.html", page=f"Ordem de serviço #{order_id:04d}", section="orders", o=o,
                           items=items, parts=parts, phone=phone)

@app.post("/os/<int:order_id>/status")
def os_status(order_id):
    get_order(order_id)
    value = request.form.get("status")
    if value not in STATUSES:
        abort(400, "Status inválido.")
    db = get_db()
    db.execute("UPDATE orders SET status=? WHERE id=?", (value, order_id))
    db.commit()
    flash("Status atualizado.", "success")
    if request.form.get("detail"):
        return redirect(url_for("ver_os", order_id=order_id))
    return redirect(url_for("lista_os", q=request.form.get("q", ""), status=request.form.get("filter_status", "")))

@app.post("/os/<int:order_id>/delete")
def os_delete(order_id):
    get_order(order_id)
    db = get_db()
    db.execute("DELETE FROM orders WHERE id=?", (order_id,))
    db.commit()
    flash("Ordem de serviço excluída.", "success")
    return redirect(url_for("lista_os"))

@app.route("/clientes", methods=["GET", "POST"])
def clientes():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Informe o nome do cliente.", "error")
        else:
            cid = db.execute("INSERT INTO clients(name,phone) VALUES (?,?)", (name, request.form.get("phone", ""))).lastrowid
            if request.form.get("plate", "").strip():
                db.execute("INSERT INTO vehicles(client_id,plate,model) VALUES (?,?,?)", (cid, request.form["plate"].strip().upper(), request.form.get("model", "")))
            db.commit()
            flash("Cliente cadastrado.", "success")
        return redirect(url_for("clientes"))
    q = request.args.get("q", "").strip()
    rows = db.execute("""SELECT c.*,COUNT(DISTINCT v.id) AS vehicle_count,
      (SELECT COUNT(*) FROM orders WHERE client_id=c.id) AS order_count FROM clients c
      LEFT JOIN vehicles v ON v.client_id=c.id WHERE c.name LIKE ? OR c.phone LIKE ? OR v.plate LIKE ?
      GROUP BY c.id ORDER BY c.name""", (f"%{q}%",)*3).fetchall()
    rows, pagination = paginate(rows)
    return render_template("clientes.html", page="Clientes e veículos", section="clients", rows=rows, q=q,pagination=pagination)

@app.route("/clientes/<int:client_id>/editar", methods=["GET", "POST"])
def cliente_editar(client_id):
    db = get_db()
    c = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not c:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Informe o nome do cliente.", "error")
        else:
            db.execute("UPDATE clients SET name=?,phone=? WHERE id=?", (name, request.form.get("phone", ""), client_id))
            for vid in request.form.getlist("vehicle_id[]"):
                db.execute("UPDATE vehicles SET plate=?,model=? WHERE id=? AND client_id=?",
                           (request.form.get(f"plate_{vid}", "").upper(), request.form.get(f"model_{vid}", ""), vid, client_id))
            if request.form.get("new_plate", "").strip():
                db.execute("INSERT INTO vehicles(client_id,plate,model) VALUES (?,?,?)", (client_id, request.form["new_plate"].strip().upper(), request.form.get("new_model", "")))
            db.commit()
            flash("Cadastro atualizado.", "success")
            return redirect(url_for("clientes"))
    vehicles = db.execute("SELECT * FROM vehicles WHERE client_id=?", (client_id,)).fetchall()
    history = db.execute("SELECT * FROM orders WHERE client_id=? ORDER BY id DESC", (client_id,)).fetchall()
    return render_template("cliente_edit.html", page="Cadastro do cliente", section="clients", c=c, vehicles=vehicles, history=history)

@app.post("/clientes/<int:client_id>/delete")
def cliente_delete(client_id):
    db = get_db()
    if db.execute("SELECT 1 FROM orders WHERE client_id=?", (client_id,)).fetchone():
        flash("Este cliente tem OS vinculadas. Preserve o cadastro para manter o histórico.", "error")
    else:
        db.execute("DELETE FROM clients WHERE id=?", (client_id,))
        db.commit()
        flash("Cliente excluído.", "success")
    return redirect(url_for("clientes"))

@app.route("/estoque", methods=["GET", "POST"])
def estoque():
    db = get_db()
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            if not name:
                raise ValueError("Informe a descrição da peça.")
            price = decimal_value(request.form.get("price"), "Preço")
            qty = decimal_value(request.form.get("qty"), "Quantidade")
            db.execute("INSERT INTO stock(name,price,qty) VALUES (?,?,?)", (name, rounded(price), float(qty)))
            db.commit()
            flash("Peça adicionada.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("estoque"))
    q = request.args.get("q", "").strip()
    low = request.args.get("low") == "1"
    rows = db.execute("SELECT * FROM stock WHERE name LIKE ?" + (" AND qty<=3" if low else "") + " ORDER BY name", (f"%{q}%",)).fetchall()
    summary = db.execute("SELECT COUNT(*) AS count,COALESCE(SUM(price*qty),0) AS value,SUM(qty<=3) AS low FROM stock").fetchone()
    rows,pagination = paginate(rows)
    return render_template("estoque.html", page="Estoque de peças", section="stock", rows=rows, q=q, low=low, summary=summary,pagination=pagination)

@app.route("/estoque/<int:item_id>/editar", methods=["GET", "POST"])
def estoque_editar(item_id):
    db = get_db()
    row = db.execute("SELECT * FROM stock WHERE id=?", (item_id,)).fetchone()
    if not row:
        abort(404)
    error = None
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            if not name:
                raise ValueError("Informe a descrição da peça.")
            price = decimal_value(request.form.get("price"), "Preço")
            qty = decimal_value(request.form.get("qty"), "Quantidade")
            db.execute("UPDATE stock SET name=?,price=?,qty=? WHERE id=?", (name, rounded(price), float(qty), item_id))
            db.commit()
            flash("Peça atualizada.", "success")
            return redirect(url_for("estoque"))
        except ValueError as exc:
            error = str(exc)
    return render_template("stock_edit.html", page="Editar peça", section="stock", row=row, error=error)

@app.post("/estoque/<int:item_id>/delete")
def estoque_delete(item_id):
    db = get_db()
    # As descrições e valores permanecem no histórico da OS.
    db.execute("UPDATE order_items SET stock_id=NULL WHERE stock_id=?", (item_id,))
    db.execute("DELETE FROM stock WHERE id=?", (item_id,))
    db.commit()
    flash("Peça removida do cadastro.", "success")
    return redirect(url_for("estoque"))

@app.get("/api/estoque/busca")
@app.get("/api/inventory_search")
def inventory_search():
    q = request.args.get("q", "").strip()
    rows = get_db().execute("SELECT * FROM stock WHERE name LIKE ? ORDER BY name LIMIT 30", (f"%{q}%",)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.get("/resumo")
def resumo_dia():
    try:
        selected_date = date.fromisoformat(request.args.get("date", now().date().isoformat()))
    except ValueError:
        selected_date = now().date()
    period = request.args.get("period", "day")
    start = selected_date.replace(day=1) if period == "month" else selected_date
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) if period == "month" else start + timedelta(days=1)
    rows = get_db().execute(ORDER_JOIN + " WHERE o.created_at>=? AND o.created_at<? ORDER BY o.id DESC", (start.isoformat(), end.isoformat())).fetchall()
    valid = [r for r in rows if status_name(r["status"]) != "Cancelada"]
    ids = [r["id"] for r in valid]
    parts = get_db().execute("SELECT COALESCE(SUM(qty*unit_price),0) FROM order_items WHERE order_id IN (" + ",".join("?"*len(ids)) + ")", ids).fetchone()[0] if ids else 0
    totals = dict(parts=parts, labor=sum(r["labor"] for r in valid), total=sum(r["total"] for r in valid),
                  discount=sum(r["discount_value"] for r in valid), count=len(valid))
    return render_template("resumo.html", page="Relatórios", section="reports", rows=rows, totals=totals,
                           selected_date=selected_date.isoformat(), period=period,
                           period_label=start.strftime("%m/%Y" if period == "month" else "%d/%m/%Y"))

@app.route("/config/logo", methods=["GET", "POST"])
@app.route("/config", methods=["GET", "POST"])
def config_logo():
    if request.method == "POST":
        from PIL import Image, UnidentifiedImageError
        kind = request.form.get("kind", "logo")
        if kind not in ("logo", "qr_pix"):
            abort(400)
        upload = request.files.get("image")
        try:
            if not upload or not upload.filename:
                raise ValueError("Selecione uma imagem.")
            im = Image.open(upload.stream)
            if im.width * im.height > 25000000:
                raise ValueError("A imagem é muito grande.")
            im.load()
            im.thumbnail((2000, 2000))
            im.convert("RGBA").save(DATA / f"{kind}.tmp.png", "PNG")
            os.replace(DATA / f"{kind}.tmp.png", DATA / f"{kind}.png")
            flash("Imagem atualizada.", "success")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            flash(str(exc) if isinstance(exc, ValueError) else "Envie uma imagem PNG ou JPEG válida.", "error")
        return redirect(url_for("config_logo"))
    return render_template("config.html", page="Configurações", section="settings")

@app.get("/media/<kind>.png")
def media(kind):
    if kind not in ("logo", "qr_pix"):
        abort(404)
    path = DATA / f"{kind}.png"
    return send_file(path if path.exists() else ROOT / "static" / f"{kind}.png", mimetype="image/png")

@app.get("/backup")
def backup():
    # A API de backup do SQLite inclui transações confirmadas no WAL.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "oficina.db"
        copy = sqlite3.connect(p)
        get_db().backup(copy)
        copy.close()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(p, "oficina.db")
            for kind in ("logo", "qr_pix"):
                path = DATA / f"{kind}.png"
                z.write(path if path.exists() else ROOT / "static" / f"{kind}.png", f"{kind}.png")
        buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=now().strftime("TR_AUTO_BACKUP_%Y-%m-%d_%H%M.zip"))

@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
def user_error(error):
    return render_template("error.html", page="Confira esta informação", section="", error=error), error.code

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=False)
