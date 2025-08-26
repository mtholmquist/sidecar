import os, sqlite3, pathlib, pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class SimpleIndex:
    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        pathlib.Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, title TEXT, text TEXT, tags TEXT)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v BLOB)")
        self._conn.commit()
    def upsert_docs(self, docs):
        cur = self._conn.cursor()
        cur.execute("DELETE FROM docs")
        cur.executemany("INSERT INTO docs (title,text,tags) VALUES (?,?,?)", docs)
        self._conn.commit(); self._rebuild_tfidf()
    def _rebuild_tfidf(self):
        cur = self._conn.cursor()
        rows = list(cur.execute("SELECT id, text FROM docs ORDER BY id"))
        ids = [r[0] for r in rows]; texts = [r[1] for r in rows] or [""]
        vec = TfidfVectorizer(max_features=20000).fit(texts)
        mat = vec.transform(texts)
        for k,v in (("tfidf_vec",vec),("tfidf_mat",mat),("tfidf_ids",ids)):
            cur.execute("INSERT OR REPLACE INTO meta (k,v) VALUES (?,?)", (k, pickle.dumps(v)))
        self._conn.commit()
    def query(self, q: str, k: int = 4):
        cur = self._conn.cursor()
        rows = list(cur.execute("SELECT id,title,text,tags FROM docs ORDER BY id"))
        if not rows: return []
        vec = pickle.loads(cur.execute("SELECT v FROM meta WHERE k='tfidf_vec'").fetchone()[0])
        mat = pickle.loads(cur.execute("SELECT v FROM meta WHERE k='tfidf_mat'").fetchone()[0])
        qv = vec.transform([q])
        sims = cosine_similarity(qv, mat)[0]
        order = sims.argsort()[::-1][:k]
        out = []
        for idx in order:
            doc_id, title, text, tags = rows[idx]
            out.append({"id": doc_id, "title": title, "text": text[:1200], "tags": tags, "score": float(sims[idx])})
        return out
