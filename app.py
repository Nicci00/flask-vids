#-*- coding: utf-8 -*-

from __future__ import unicode_literals
from __future__ import print_function

from flask import Flask, render_template, request, redirect, url_for, session
from flask.ext.sqlalchemy import SQLAlchemy
from werkzeug import secure_filename
from werkzeug.contrib.fixers import ProxyFix

from ConfigParser import SafeConfigParser

from ffvideo import VideoStream ##thumbnails
import magic ##filetype check

import random
import sys
import os
import logging
import shutil
import hashlib
import tempfile

## Set up
app = Flask(__name__)

ProxyFix(app.wsgi_app)

parser = SafeConfigParser()
parser.read('config.ini')

app.config['upload_dir'] = parser.get('application', 'upload_dir')
app.config['allowed_mime'] = set(['video/webm','video/mp4','video/ogg'])
app.config['thumbs_dir'] = parser.get('application', 'thumbs_dir')
app.config['MAX_CONTENT_LENGTH'] = int(parser.get('application', 'max_file_size'))* 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///videos.db'

db = SQLAlchemy(app)

logging.basicConfig(filename='videos-log.log', level=logging.ERROR)

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
			print("Error, file not allowed")
			return "<script> alert('File type not allowed!'); \
				window.location.replace('');</script>", 415

		file_hash = hashlib.md5(open(temp_file).read()).hexdigest()
		if file_hash in list_hash():
			os.remove(temp_file)
			return "<script> alert('File already exists!'); \
				window.location.replace('');</script>"

		#everything seems to be alright, saving file

		title = None
		description = None
		ip = None

		print(title)
		print(description)

		if request.form["title"] is None:
			title = parser.get("application","default_title")
		else:
			title = request.form["title"]

		if request.form["description"] is None:
			description = parser.get("application","default_description")
		else:
			description = request.form["description"]

		#nginx IP fuckery

		if parser.getboolean("application", "dev"):
			uploader_ip = request.remote_addr
		else:
			ip = request.headers.getlist("X-Forwarded-For")[0]

		new_video(title, file.filename, ip, file_hash, description)

		return redirect('/')
	
	else:
		return render_template('videos.html', videos=Video.query.all())

@app.route('/v')
def video_page():
	id = request.args.get('v')
	
	if not id:
		return redirect('/')

	video = Video.query.get_or_404(id)

	return render_template('video.html', video=video)

@app.route('/tos')
def tos():
	return render_template('tos.html')

@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html'),404


@app.errorhandler(500)
def internal_server_error(e):
	return render_template('500.html', admin_email=parser.get("other", "admin_email")),500


@app.errorhandler(413)
def request_entity_too_large(e):
	logging.warning(request.remote_addr + " atempted to upload file larger than allowed")
	return '''<script> alert("I-it won't f-fit in! - File too large");
			window.location.replace("");</script>''',413

#misc funcs
def new_video(title, file_name, uploader_ip, file_hash, description):
	#this methods assumes the video is in the temp folder
	try:

		temp_file = os.path.join(tempfile.gettempdir(), file_name)

		vs = VideoStream(temp_file)
		thumb = vs.get_frame_at_sec(int(vs.duration/2)).image()
		thumb.save(os.path.join(app.config["thumbs_dir"], file_name) + '.jpg')

		def_file = os.path.join(app.config["upload_dir"] + file_name)

		shutil.move(temp_file, def_file)

		video = Video(title, file_name, file_hash, uploader_ip, description)

		db.session.add(video)
		db.session.commit()

	except Exception, e:
		abort(500)


def list_hash():
	try:
		hashes = []

		for v in Video.query.all():
			hashes.append(v.file_md5_hash)

		return hashes

	except Exception as e:
		logging.error(e)
		abort(500)


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

    app.run(debug=parser.getboolean("application", "dev"), host='0.0.0.0')
    