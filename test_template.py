from flask import Flask, render_template, session
import os

app = Flask(__name__, template_folder='templates')
app.secret_key = 'test'

@app.route('/test_profile')
def test_profile():
    session['role'] = 'student'
    # Test with None profile
    return render_template('profile.html', profile=None)

if __name__ == '__main__':
    with app.test_request_context():
        try:
            rendered = render_template('profile.html', profile=None)
            print("Rendered successfully with profile=None")
        except Exception as e:
            print(f"Error rendering with profile=None: {e}")
        
        try:
            dummy_profile = {'name': 'Test', 'reg_no': '123', 'class_name': '10', 'section': 'A'}
            rendered = render_template('profile.html', profile=dummy_profile)
            print("Rendered successfully with dummy profile")
        except Exception as e:
            print(f"Error rendering with dummy profile: {e}")
