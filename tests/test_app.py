"""Testes de integração em cópia temporária. Nunca alteram a base de entrega."""
import importlib.util
import io
import os
import re
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkshopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ.update(DATA_DIR=cls.tmp.name, ADMIN_USERNAME="test-admin",
                          ADMIN_PASSWORD="Integration-Test-Password_2026",
                          SECRET_KEY="integration-only-64-character-random-secret-for-testing-123456789",
                          COOKIE_SECURE="false", TRUST_PROXY="false")
        spec = importlib.util.spec_from_file_location("workshop_test", ROOT / "app.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        cls.app = cls.mod.app
        cls.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.client.get("/login")
        with self.client.session_transaction() as s:
            self.token = s["csrf"]
        response = self.client.post("/login", data=self.form(username="test-admin", password="Integration-Test-Password_2026"))
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as s:
            s["csrf"] = self.token

    def form(self, **data):
        return {"csrf_token": self.token, **data}

    def query(self, sql, params=()):
        with self.app.app_context():
            return [dict(r) for r in self.mod.get_db().execute(sql, params).fetchall()]

    def create_order(self, **extra):
        payload = self.form(client_name="Cliente integração", phone="32999998888", plate="TST1234", model="Teste",
                            labor="100.00", discount_percent="10", payment_method="Pix",
                            **{"desc[]": ["Peça teste", "Segundo item"], "qty[]": ["2", "1.5"], "unit[]": ["20", "10"]})
        payload.update(extra)
        response = self.client.post("/os/nova", data=payload)
        self.assertEqual(response.status_code, 302)
        return int(re.search(r"/os/(\d+)", response.location).group(1))

    def test_01_import_preserves_every_original_row(self):
        original = sqlite3.connect(ROOT / "seed/oficina.db")
        with self.app.app_context():
            db = self.mod.get_db()
            for table in ("clients", "vehicles", "stock", "orders", "order_items"):
                self.assertEqual([tuple(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY id")],
                                 original.execute(f"SELECT * FROM {table} ORDER BY id").fetchall(), table)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        original.close()

    def test_02_authentication_and_csrf(self):
        anonymous = self.app.test_client()
        for path in ("/", "/os", "/estoque", "/clientes", "/backup", "/media/logo.png"):
            self.assertEqual(anonymous.get(path).status_code, 302, path)
        self.assertEqual(anonymous.get("/api/inventory_search").status_code, 401)
        self.assertEqual(anonymous.get("/health").status_code, 200)
        self.assertEqual(self.client.post("/clientes", data={"name": "Sem CSRF"}).status_code, 400)
        self.assertEqual(self.client.post("/clientes", data={"name":"Inválido","csrf_token":"símbolo"}).status_code,400)
        anonymous.get("/login")
        with anonymous.session_transaction() as s: login_token=s["csrf"]
        self.assertEqual(anonymous.post("/login",data={"username":"usuário","password":"incorreta","csrf_token":login_token}).status_code,200)
        self.assertEqual(self.client.post("/os/317/status", data=self.form(status="inventado")).status_code, 400)

    def test_03_all_pages_render_with_imported_data(self):
        c = self.query("SELECT id FROM clients LIMIT 1")[0]["id"]
        p = self.query("SELECT id FROM stock LIMIT 1")[0]["id"]
        for path in ("/", "/os", "/os?q=317", "/os?status=Concluída", "/os/nova", "/os/317", "/os/317/editar",
                     "/clientes", f"/clientes/{c}/editar", "/estoque", f"/estoque/{p}/editar", "/resumo",
                     "/resumo?period=month", "/config", "/media/logo.png", "/media/qr_pix.png"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            response.close()

    def test_04_atomic_order_totals_edit_and_delete(self):
        oid = self.create_order()
        row = self.query("SELECT * FROM orders WHERE id=?", (oid,))[0]
        self.assertEqual(row["total_bruto"], 155)
        self.assertEqual(row["discount_value"], 15.5)
        self.assertEqual(row["total"], 139.5)
        self.assertEqual(len(self.query("SELECT * FROM order_items WHERE order_id=?", (oid,))), 2)
        response = self.client.post(f"/os/{oid}/editar", data=self.form(
            client_id=str(row["client_id"]), client_name="Cliente integração", phone="32999998888",
            plate="TST1234", model="Atualizado", labor="200", discount_percent="5",
            **{"desc[]":["Substituta"],"qty[]":["1"],"unit[]":["50"]}))
        self.assertEqual(response.status_code, 302)
        row = self.query("SELECT * FROM orders WHERE id=?", (oid,))[0]
        self.assertEqual(row["total"], 237.5)
        self.assertEqual(len(self.query("SELECT * FROM order_items WHERE order_id=?", (oid,))), 1)
        response = self.client.post(f"/os/{oid}/status", data=self.form(status="Em andamento",detail="1"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.query("SELECT status FROM orders WHERE id=?", (oid,))[0]["status"], "Em andamento")
        self.assertIn("Cliente integração", self.client.get("/os?q=TST1234").text)
        self.client.post(f"/os/{oid}/delete", data=self.form())
        self.assertEqual(self.query("SELECT * FROM order_items WHERE order_id=?", (oid,)), [])
        self.assertEqual(self.client.get(f"/os/{oid}").status_code, 404)

    def test_05_invalid_values_do_not_write_partial_records(self):
        before = [self.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in ("orders", "clients", "vehicles")]
        for bad in ("-1", "NaN", "Infinity", "xyz"):
            response = self.client.post("/os/nova", data=self.form(client_name="Não salvar", plate="BAD1234", labor=bad))
            self.assertEqual(response.status_code, 200)
            self.assertIn("informe um número válido", response.text)
        after = [self.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in ("orders", "clients", "vehicles")]
        self.assertEqual(before, after)

    def test_06_reports_discount_and_cancelled(self):
        oid = self.create_order(client_name="Relatório integração", plate="REP1234")
        today = self.mod.now().date().isoformat()
        html = self.client.get(f"/resumo?date={today}").text
        self.assertIn("139,50", html)
        self.client.post(f"/os/{oid}/status", data=self.form(status="Cancelada"))
        rows = self.query("SELECT * FROM orders WHERE created_at LIKE ?", (today + "%",))
        expected = sum(r["total"] for r in rows if self.mod.status_name(r["status"]) != "Cancelada")
        html = self.client.get(f"/resumo?date={today}").text
        self.assertIn(self.mod.money(expected), html)
        self.assertIn("Cancelada", html)
        self.client.post(f"/os/{oid}/delete", data=self.form())

    def test_07_client_vehicle_and_history_protection(self):
        self.client.post("/clientes", data=self.form(name="Cadastro integração",phone="32988887777",plate="CLI1234",model="Novo"))
        c = self.query("SELECT * FROM clients WHERE name='Cadastro integração'")[0]
        v = self.query("SELECT * FROM vehicles WHERE client_id=?", (c["id"],))[0]
        self.client.post(f"/clientes/{c['id']}/editar",data=self.form(name="Cadastro alterado",phone="32988886666",
                         **{"vehicle_id[]":[str(v["id"])],f"plate_{v['id']}":"CLI1234",f"model_{v['id']}":"Modelo alterado"}))
        self.assertEqual(self.query("SELECT model FROM vehicles WHERE id=?",(v["id"],))[0]["model"],"Modelo alterado")
        self.client.post(f"/clientes/{c['id']}/delete",data=self.form())
        self.assertEqual(self.query("SELECT * FROM vehicles WHERE id=?",(v["id"],)),[])
        linked = self.query("SELECT client_id FROM orders LIMIT 1")[0]["client_id"]
        self.client.post(f"/clientes/{linked}/delete",data=self.form())
        self.assertTrue(self.query("SELECT * FROM clients WHERE id=?",(linked,)))

    def test_08_stock_edit_search_and_delete(self):
        self.client.post("/estoque",data=self.form(name="Peça integração <segura>",price="25.50",qty="2"))
        item=self.query("SELECT * FROM stock WHERE name=?",("Peça integração <segura>",))[0]
        html=self.client.get("/estoque?q=integração&low=1").text
        self.assertIn("&lt;segura&gt;",html)
        self.client.post(f"/estoque/{item['id']}/editar",data=self.form(name="Peça alterada",price="30",qty="4"))
        self.assertEqual(self.query("SELECT qty FROM stock WHERE id=?",(item["id"],))[0]["qty"],4)
        results=self.client.get("/api/inventory_search?q=Peça alterada").json
        self.assertEqual(results[0]["price"],30)
        self.client.post(f"/estoque/{item['id']}/delete",data=self.form())
        self.assertEqual(self.query("SELECT * FROM stock WHERE id=?",(item["id"],)),[])

    def test_09_backup_upload_and_restart_persistence(self):
        from PIL import Image
        image=io.BytesIO();Image.new("RGB",(16,16),"red").save(image,"PNG");image.seek(0)
        response=self.client.post("/config",data=self.form(kind="logo",image=(image,"logo.png")))
        self.assertEqual(response.status_code,302)
        response=self.client.post("/config",data=self.form(kind="qr_pix",image=(io.BytesIO(b"not a photo"),"bad.png")),follow_redirects=True)
        self.assertIn("imagem PNG ou JPEG válida",response.text)
        response = self.client.get("/media/logo.png")
        self.assertEqual(response.status_code,200)
        response.close()
        response=self.client.get("/backup")
        z=zipfile.ZipFile(io.BytesIO(response.data))
        self.assertEqual(set(z.namelist()),{"oficina.db","logo.png","qr_pix.png"})
        target=Path(self.tmp.name)/"backup-check.db";target.write_bytes(z.read("oficina.db"))
        copy=sqlite3.connect(target)
        self.assertEqual(copy.execute("PRAGMA integrity_check").fetchone()[0],"ok")
        self.assertEqual(copy.execute("SELECT COUNT(*) FROM orders").fetchone()[0],self.query("SELECT COUNT(*) AS n FROM orders")[0]["n"])
        copy.close()
        with self.app.app_context():
            before=[tuple(r) for r in self.mod.get_db().execute("SELECT * FROM orders ORDER BY id")]
            self.mod.init_db()
            after=[tuple(r) for r in self.mod.get_db().execute("SELECT * FROM orders ORDER BY id")]
        self.assertEqual(before,after)

    def test_10_session_logout_and_cookie_settings(self):
        response=self.client.post("/logout",data=self.form())
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get("/os").status_code,302)
        self.assertTrue(self.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(self.app.config["SESSION_COOKIE_SAMESITE"],"Lax")

    def test_11_pagination_and_decimal_rounding(self):
        html = self.client.get("/os").text
        self.assertIn("Página 1 de", html)
        self.assertEqual(html.count('class="status-form noprint"'),30)
        self.assertIn("Página 2 de", self.client.get("/os?page=2").text)
        self.assertEqual(self.client.get("/os?page=abc").status_code,200)
        oid=self.create_order(labor="0.05",discount_percent="10",**{"desc[]":[],"qty[]":[],"unit[]":[]})
        row=self.query("SELECT * FROM orders WHERE id=?",(oid,))[0]
        self.assertEqual(row["discount_value"],0.01)
        self.assertEqual(row["total"],0.04)
        self.client.post(f"/os/{oid}/delete",data=self.form())

    def test_12_login_attempt_limiting(self):
        c=self.app.test_client();c.get("/login")
        with c.session_transaction() as s: token=s["csrf"]
        for _ in range(10):
            response=c.post("/login",data={"username":"test-admin","password":"incorrect","csrf_token":token})
            self.assertEqual(response.status_code,200)
        response=c.post("/login",data={"username":"test-admin","password":"incorrect","csrf_token":token})
        self.assertEqual(response.status_code,429)
        self.assertIn("Aguarde 15 minutos",response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
