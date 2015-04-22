#-*- coding: utf-8 -*-

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug import secure_filename

from ffvideo import VideoStream ##thumbnails
import magic

import random
import sys
import os
import logging
import shutil
import filecmp

app = Flask(__name__)

app.config['upload_dir'] = 'static/videos/'
app.config['temp_dir'] = 'tmp/'
app.config['allowed_mime'] = set(['video/webm','video/mp4','video/ogg'])
app.config['thumbs_dir'] = 'static/img/video-thumb/'
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024 #80MB

logging.basicConfig(filename='videos-log.log', level=logging.INFO)

print("Detected %d videos" % len(os.listdir(app.config['upload_dir'])))


def list_videos():
	video_path = 'static/videos/'
	thumbs_path = 'static/img/video-thumb/'
	videos = os.listdir(video_path)
	files = []
	
	for v in videos:
		if not os.path.exists(thumbs_path + v + '.jpg'):
			try:
				vs = VideoStream(video_path + v)
				thumb = vs.get_frame_at_sec(int(vs.duration/2)).image()
				thumb.save(thumbs_path + v + '.jpg')
			except Exception, e:
				logging.warning("Cannot get thumb from file" + v)

		files.append(['videos/' + v, 'img/video-thumb/' + v + '.jpg'])

	return files


@app.route('/', methods = ['GET', 'POST'])
def videos():
	error = None
	if request.method == 'POST':
		file = request.files['file']

		filename = secure_filename(file.filename)

		temp_file = os.path.join(app.config['temp_dir'], filename)

		if filename == '':
			return "<script> alert('No file to be uploaded'); \
				window.location.replace('');</script>"

		#save file as temporary
		file.save(temp_file)

		#mime check
		mime = magic.from_file(temp_file, mime=True)
		if mime not in app.config['allowed_mime']:
			os.remove(temp_file)
			print("Error, file not allowed")
			return "<script> alert('File type not allowed!'); \
				window.location.replace('');</script>"
		
		exists = False

		for v in os.listdir(app.config['upload_dir']):
			cpath = app.config['upload_dir'] + v
			if filecmp.cmp(temp_file, cpath):
				os.remove(temp_file)
				exists = True
		
		if exists:
			return "<script> alert('File already exists!'); \
				window.location.replace('');</script>"
		else:
			logging.info("Uploaded: %s by %s" % (filename, request.remote_addr))
			save_path = os.path.join(app.config['upload_dir'], filename)
			shutil.move(temp_file, save_path)
			return render_template('videos.html', files=list_videos())
	
	else:
		return render_template('videos.html', files=list_videos())

@app.route('/v')
def video_page():
	video = request.args.get('v')

	if not video:
		return redirect('/')

	mime = 'video/ogv'

	return render_template('video.html', video=video, mime=mime)

@app.errorhandler(404)
def page_not_found(e):
	return render_template('404.html'),404


@app.errorhandler(500)
def internal_server_error(e):
	return render_template('500.html'),500


@app.errorhandler(413)
def request_entity_too_large(e):
	logging.warning(request.remote_addr + " atempted to upload file larger than allowed")
	return '''<script> alert("I-it won't f-fit in! - File too large");
			window.location.replace("");</script>''',413


if __name__ == '__main__':
    app.run(debug=True)