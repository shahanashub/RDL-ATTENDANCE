from app import app
import json

with app.test_client() as client:
    # set admin session
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'admin1'
        sess['role'] = 'admin'

    print('POST /add_subjects with class_num=2, section=B')
    resp = client.post('/add_subjects', data={'class_num':'2','section':'B','subjects':'Biology, Chemistry'}, follow_redirects=True)
    print('  status', resp.status_code)

    # find class id for Class 2-B
    from app import get_db
    conn = get_db()
    class_row = conn.execute('SELECT id FROM classes WHERE class_name=? AND section=?', ('Class 2','B')).fetchone()
    cid = class_row['id'] if class_row else None
    print('  class id:', cid)

    print('GET /get_subjects/2-B')
    resp = client.get('/get_subjects/2-B')
    print('  status', resp.status_code)
    print('  json:', resp.get_json())

    print('Access attendance page')
    # set teacher session
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'teacher1'
        sess['role'] = 'teacher'

    resp = client.get('/attendance')
    print('  attendance page status', resp.status_code)
    # basic check for subject dropdown in page
    text = resp.get_data(as_text=True)
    print('  contains Subject label?', 'Subject' in text or 'Subject (Optional)' in text)

print('Done')
