import sqlite3

def test_query():
    conn = sqlite3.connect('scientia.db')
    conn.row_factory = sqlite3.Row
    try:
        class_id = 5
        query = 'SELECT * FROM timetables WHERE class_id = ? ORDER BY CASE \
            WHEN day="Monday" THEN 1 \
            WHEN day="Tuesday" THEN 2 \
            WHEN day="Wednesday" THEN 3 \
            WHEN day="Thursday" THEN 4 \
            WHEN day="Friday" THEN 5 \
            WHEN day="Saturday" THEN 6 \
            ELSE 7 END'
        res = conn.execute(query, (class_id,)).fetchall()
        print("Query successful")
    except Exception as e:
        print(f"Query failed: {e}")
    conn.close()

if __name__ == '__main__':
    test_query()
