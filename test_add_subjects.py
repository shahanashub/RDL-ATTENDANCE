from app import app

with app.test_client() as client:
    # set admin session
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'admin1'
        sess['role'] = 'admin'

    resp = client.post('/add_subjects', data={'class_num':'1','section':'A','subjects':'Math, English, Science'}, follow_redirects=True)
    print('Status:', resp.status_code)
    print('Response length:', len(resp.data))
    print('Flash messages (html snippet):')
    text = resp.data.decode(errors='ignore')
    start = text.find('<div')
    print(text[start:start+300])
