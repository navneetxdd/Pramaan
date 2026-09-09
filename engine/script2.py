import sqlite3
conn = sqlite3.connect('../.localdata/forensic.db')
cur = conn.cursor()
cur.execute("SELECT id FROM devices WHERE case_id='cba5a5329825421ab2d309cbf283f236'")
print(cur.fetchone()[0])
