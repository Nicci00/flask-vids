#-*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals

import hashlib
import logging
import os
import shutil
import tempfile

import magic 

from configparser import ConfigParser

import av
from flask import Config, Flask, abort, redirect, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix

## Set up
app = Flask(__name__)

ProxyFix(app.wsgi_app)

parser = ConfigParser()
parser.read('config.ini')

app.secret_key = parser.get('application', 'key')

app.config['upload_dir'] = parser.get('application', 'upload_dir')
app.config['allowed_mime'] = set(['video/webm','video/mp4','video/ogg'])
app.config['thumbs_dir'] = parser.get('application', 'thumbs_dir')
app.config['MAX_CONTENT_LENGTH'] = int(parser.get('application', 'max_file_size'))* 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///%s' % parser.get('database', 'db_name')

APP_ROOT = os.getcwd()

db = SQLAlchemy(app)

#logging.basicConfig(filename='videos-log.log', level=logging.ERROR)

##view funcs
@app.route('/', methods = ['GET', 'POST'])
def videos():
    error = None
    if request.method == 'POST':
        file = request.files['file']

        if not file:
            return "<script> alert('No file to be uploaded'); \
                window.location.replace('');</script>", 400

        file.filename = secure_filename(file.filename)
        temp_file = os.path.join(tempfile.gettempdir(), file.filename)
        file.save(temp_file)

        #mime check
        mime = magic.from_file(temp_file, mime=True)

        if mime not in app.config['allowed_mime']:
            os.remove(temp_file)
            return "<script> alert('File type not allowed!'); \
                window.location.replace('');</script>", 415

        file_hash = hashlib.md5(open(temp_file,'rb').read()).hexdigest()

        if file_hash in list_hash():
            os.remove(temp_file)
            return "<script> alert('File already exists!'); \
                window.location.replace('');</script>"

        #everything seems to be alright, saving file

        title = None
        description = None
        ip = None

        if not request.form["title"]:
            title = file.filename
        else:
            title = request.form["title"]

        if not request.form["description"]:
            description = parser.get("application","default_description")
        else:
            description = request.form["description"]

        #nginx IP fuckery

        if parser.getboolean("application", "dev"):
            ip = request.remote_addr
        else:
            ip = request.headers.getlist("X-Forwarded-For")[0]


        print("new video filename:", file.filename )
        new_video(title, file.filename, ip, file_hash, description)

        return redirect('/')
    
    else:
        return render_template('videos.html', videos=Video.query.all())


@app.route('/video/<int:id>')
def show(id):
    video = Video.query.get_or_404(id)
    return render_template('video.html', video=video)


@app.route('/tos')
def tos():
    return render_template('tos.html', admin_email = parser.get('admin', 'admin_email'))


@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['user'] == parser.get('admin', 'username') \
            and request.form['password'] == parser.get('admin','password'):
            session['logged'] = True
            return redirect('/admin')
        else:
            abort(403)
    else:

        return render_template('login.html')


@app.route('/admin', methods=['GET', 'POST'])
def admin_page():

    try:
        logged = session['logged']
    except KeyError:
        abort(403)

    if request.method == 'POST':
        return redirect('/admin')
    else:
        return render_template('admin.html', logged=logged, videos=Video.query.all())


@app.route('/logout')
def admin_logout():
    try:
        if session['logged']:
            session.pop('logged', None)
            return redirect('/')
    except KeyError:
        return "Not logged"
        

@app.route('/delete')
def delete_vid():
    try:
        logged = session['logged']
    except KeyError:
        abort(403)

    try:
        id = request.args['v']
        
        vid = Video.query.get(id)
        
        db.session.delete(vid)

        os.remove(os.path.join(app.config['upload_dir'], vid.file_name))
        os.remove(os.path.join(app.config['thumbs_dir'], vid.file_name + '.jpg'))

        db.session.commit()
    except Exception as e:
        logging.error(e)
        abort(500)

    return redirect('/admin')


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'),404


#@app.errorhandler(500)
#def internal_server_error(e):
#    return render_template('500.html', admin_email=parser.get("admin", "admin_email")),500


@app.errorhandler(413)
def request_entity_too_large(e):
    logging.warning(request.remote_addr + " atempted to upload file larger than allowed")
    return '''<script> alert("I-it won't f-fit in! - File too large");
            window.location.replace("");</script>''',413


#misc funcs
def new_video(title, file_name, uploader_ip, file_hash, description):
    #this methods assumes the video is in the temp folder
    temp_file = os.path.join(tempfile.gettempdir(), file_name)

    container = av.open(temp_file)
    stream = container.streams.video[0]
    middle_frame = stream.frames // 2
    frame =  next((x for i,x in enumerate(container.decode(stream)) if i==middle_frame), None)
    
    thumb_filename =  file_name + ".jpg"
    thumb_path = os.path.join(APP_ROOT, app.config["thumbs_dir"], thumb_filename)
    frame.to_image().save(thumb_path)
    
    def_file = os.path.join(APP_ROOT, app.config["upload_dir"], file_name)
    shutil.move(temp_file, def_file)

    video = Video(title, file_name, file_hash, uploader_ip, description)

    db.session.add(video)
    db.session.commit()

def list_hash():
    hashes = []
    for v in Video.query.all():
        hashes.append(v.file_md5_hash)
    return hashes

class Video(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80))
    file_name = db.Column(db.String(80))
    file_md5_hash = db.Column(db.String(80))
    uploader_ip = db.Column(db.String(16))
    description = db.Column(db.String(255))

    def __init__(self, title, file_name, file_md5_hash, uploader_ip, description):
        self.title = title
        self.file_name = file_name
        self.file_md5_hash = file_md5_hash
        self.uploader_ip = uploader_ip
        self.description = description

    def __repr__(self):
        return "<Video %s>" % self.file_name

if __name__ == '__main__':
    app.run(debug=parser.getboolean("application", "dev"))
    
