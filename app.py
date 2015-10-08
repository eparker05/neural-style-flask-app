import os
import glob
import imghdr
import Queue
import subprocess
import threading
import time

from PIL import Image
from werkzeug import secure_filename
from flask import Flask, flash, request, render_template_string
from flask_wtf import Form
from flask.ext.uploads import UploadSet, IMAGES, configure_uploads
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField
from wtforms.validators import DataRequired

master_q = Queue.Queue(maxsize=20)
app = Flask(__name__, static_folder="data")
app.config['SECRET_KEY'] = "fake not random key dfdfsdpp"
template_str = """ 
    {% macro render_err(field) %}
        {% if field.errors %}
          <ul class=errors>
          {% for error in field.errors %}
            <li>{{ error }}</li>
          {% endfor %}
          </ul>
        {% endif %}
    {% endmacro %}
    <div style="margin-top: 30px; margin-left: 20px;">
    <h2>Neural-style web app: apply any artistic style to your own photo</h2>
    <p>For more info on how this works, check out
      <a href="https://github.com/jcjohnson/neural-style">JC Johnson's github page</a>
    </p>
    <form method="POST" action="/" enctype="multipart/form-data">
      {{ form.hidden_tag() }}
      {{ form.name.label }} {{ form.name(size=20) }} {{ render_err(form.name) }} <br>
      {{ form.style.label }} {{ form.style() }} {{ render_err(form.style) }}<br>
      {{ form.content.label }} {{ form.content() }} {{ render_err(form.content) }}<br>
    <input type="submit" value="Go">
    </form>
    </div><hr>
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <div><ul class=flashes>
        {% for message in messages %}
          <li>{{ message }}</li>
        {% endfor %}
        </ul></div>
        <hr>
      {% endif %}
    {% endwith %}
    <div>
    {% for item in pictures %}
    <div>
       <a href="{{ item["style"] }}">
       <img src="{{ item["stylethumb"] }}" width="250"></a>
       <a href="{{ item["content"] }}">
       <img src="{{ item["contentthumb"] }}" width="250"></a>
       <a href="{{ item["output"] }}">
       <img src="{{ item["output"] }}" width="250"></a>
    </div>
    {% endfor %}
    </div>
"""
# STUPID STUPID syntax for configuring flask-upload
app.config['UPLOADED_IMAGES_DEST'] = '/tmp/flask_uploads'
images = UploadSet('images', IMAGES)
configure_uploads(app, (images,))

class MyForm(Form):
    name = StringField('Password', validators=[DataRequired()])
    style = FileField('Style photo', validators=[
            DataRequired(),
            FileAllowed(images, 'Images only!')])
    content = FileField('Content photo', validators=[
            DataRequired(),
            FileAllowed(images, 'Images only!')])


def get_dirs():
    dir_dict = {}
    dir_list = []
    dirlen = len('/home/ubuntu/flaskapp/data/')
    for dir in list(os.walk('/home/ubuntu/flaskapp/data/'))[1:]:
        """('/home/ubuntu/flaskapp/data/1', [], ['out.png', 'style.jpg', 'content.jpg'])]"""
        single_dir = {}
        stylefile = ''
        prefix = dir[0].split("/")[-1]
        single_dir["dirname"] = prefix
        for filename in dir[2]:
            single_dir["dirname"] = dir[0].split("/")[-1]
            if "style.thumb" in filename:
                single_dir['stylethumb'] = "data/" + prefix + "/" + filename
            elif "style" in filename:
                single_dir['style'] = "data/" + prefix + "/" + filename
            if "content.thumb" in filename:
                single_dir['contentthumb'] = "data/" + prefix + "/" + filename
            elif "content" in filename:
                single_dir['content'] = "data/" + prefix + "/" + filename
            if "out" in filename:
                single_dir['output'] = "data/" + prefix + "/" + filename
        if 'output' not in single_dir:
            single_dir['output'] = "data/pending.jpg"
        if "style" in single_dir and "content" in single_dir:
            dir_dict[prefix] = single_dir  # This may be needed in the future!
            dir_list.append(single_dir)
            print single_dir
    dir_list.sort(key = lambda v: -1*float(v["dirname"]))
    return dir_list


@app.route('/', methods=('GET', 'POST'))
def submit():
    form = MyForm()
    while form.validate_on_submit():
        if form.name.data.lower() != "evan":
            flash("incorrect password")
            print("what, wrong pw!")
            break
        ok_types = ("png", "jpeg")
        content_type = Image.open(form.content.data).format.lower()
        if content_type not in ok_types:
            flash("file types must both be png, jpg, or jpeg. Files may have misleading extension")
            flash("The content file appears to be a %s" % imghdr.what(form.content.data))
            break
        style_type = Image.open(form.style.data).format.lower()
        if style_type not in ok_types:
            flash("file types must both be png, jpg, or jpeg. Files may have misleading extension")
            flash("The style file appears to be a %s" % imghdr.what(form.style.data))
            break
        job = {"dirname": str(time.time())}
        full_dir =  "/home/ubuntu/flaskapp/data/" + job["dirname"] + "/"
        os.mkdir(full_dir)
        job["content"] = full_dir + "content." + content_type
        job["style"] = full_dir + "style." + style_type
        if master_q.full():
            flash("Queue is currently full, try again later")
            break
        form.style.data.seek(0)
        form.style.data.save(job["style"])
        form.content.data.seek(0)
        form.content.data.save(job["content"])
        # make style thumb
        fname, _ = os.path.splitext(job["style"])
        im = Image.open(job["style"])
        im.thumbnail((250,250))
        im.save(fname + ".thumb.jpg", "JPEG")
        # Content thumb.
        fname, _ = os.path.splitext(job["content"])
        im = Image.open(job["content"])
        im.thumbnail((250,250))
        im.save(fname + ".thumb.jpg", "JPEG")
        master_q.put(job)
        print("processing")
        #process_job(job)  # for debug
        time.sleep(0.5)
        flash("new image entered for processing")
        break
    current_images = get_dirs()
    return render_template_string(template_str, form=form, pictures=current_images)


def listen_to_queue(in_q):
    """Uses a queue that produces job dicts.

    Job dict has fields "dirname", "style", and "content"
    """
    while True:
        job = in_q.get()
        process_job(job)

def process_job(job):
    out_image_fname = "/home/ubuntu/flaskapp/data/" + job["dirname"] + "/out.png"
    call_args = ["th", "/home/ubuntu/neural-style/neural_style.lua",
                 "-style_image", job["style"], "-content_image", job["content"],
                 "-save_iter", "0", "-image_size", "512", "-gpu", "0",
                 "-backend", "cudnn", "-output_image", out_image_fname,
                 "-num_iterations", "1000"]
    print("calling now")
    print " ".join(call_args)
    subprocess.call(call_args)
    time.sleep(1)
        

if __name__ == "__main__":
    threading.Thread(target=listen_to_queue, args=(master_q,)).start()
    app.run(host="0.0.0.0", debug=None, port=8080)
