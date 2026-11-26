import pandas as pd, psycopg
Q = pd.read_csv("queries.csv", dtype=str, keep_default_na=False).set_index("query_id")
D = pd.read_csv("danh_gia/details.csv", dtype=str)
with psycopg.connect("postgresql://postgres:btl24@localhost:5434/btl") as c:
    info = {r[0]: r[1:] for r in c.execute(
        "SELECT i.item_id, i.chapter_title, v.video_title, left(i.transcript, 300) FROM item i JOIN video v USING (video_id)")}
rows = []
for _, d in D[D.type.isin(["A", "C"])].iterrows():
    q = Q.loc[d.query_id]
    for k in (1, 2, 3):
        iid = d[f"content{k}"]
        ch, vt, tr = info.get(iid, ("", "", ""))
        rows.append({"query_id": d.query_id, "type": d.type, "query_audio": q.audio_path, "rank": k,
                     "item_id": iid, "score": d[f"content{k}_score"], "cung_video": d[f"content{k}_ok"],
                     "chapter_title": ch, "video_title": vt, "transcript_dau": tr, "lien_quan": ""})
pd.DataFrame(rows).to_csv("danh_gia/gan_nhan_noi_dung.csv", index=False, encoding="utf-8-sig")
print(len(rows), "dòng -> danh_gia/gan_nhan_noi_dung.csv")