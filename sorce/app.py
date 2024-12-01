from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import markdown
from flask import Markup 
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
# SQLiteの設定
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'  # データベースファイルの場所
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # トラッキング機能を無効化
db = SQLAlchemy(app)

UPLOAD_FOLDER = 'static/uploads'  # アップロード先のフォルダ
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# データベースモデルの定義
class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    introduction = db.Column(db.String(200))
    experience = db.relationship('Experience', backref='profile', lazy=True)
    skills = db.relationship('Skill', backref='profile', lazy=True)
    projects = db.relationship('Project', backref='profile', lazy=True)

class Experience(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(50))
    description = db.Column(db.String(200))
    profile_id = db.Column(db.Integer, db.ForeignKey('profile.id'), nullable=False)
    
class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255))
    image_url = db.Column(db.String(255))  # スキルの画像URL
    profile_id = db.Column(db.Integer, db.ForeignKey('profile.id'), nullable=False)
    level = db.Column(db.Integer, nullable=False)  # スキルのレベルを追加


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    link = db.Column(db.String(255), nullable=False)
    link_text = db.Column(db.String(100), default='View Project')  # ここでリンクテキストを管理
    profile_id = db.Column(db.Integer, db.ForeignKey('profile.id'), nullable=False)

# データベースを初期化
@app.before_first_request
def create_tables():
    db.create_all()

# 管理者アカウント情報（変更可）
ADMIN_USERNAME = '*****'
ADMIN_PASSWORD = '*****'

# ログインの制限をかけるデコレーター
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    profile = Profile.query.first()  # プロフィール情報を取得
    if profile and profile.introduction:
        # MarkdownをHTMLに変換し、Markupで安全に表示できるようにする
        profile.introduction = Markup(markdown.markdown(profile.introduction))
    return render_template('index.html', profile=profile)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if (request.form['username'] == ADMIN_USERNAME and
                request.form['password'] == ADMIN_PASSWORD):
            session['logged_in'] = True
            return redirect(url_for('edit'))
        else:
            return "Invalid credentials, please try again."
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('home'))

@app.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    profile = Profile.query.first()  # プロフィール情報を取得
    if request.method == 'POST':
        # プロフィールを更新
        if profile is None:
            profile = Profile(introduction=request.form["introduction"])
            db.session.add(profile)
        else:
            profile.introduction = request.form["introduction"]

        # 経歴を更新
        Experience.query.filter_by(profile_id=profile.id).delete()  # 既存の経歴を削除
        for year, desc in zip(request.form.getlist("year"), request.form.getlist("description")):
            if year and desc:  # 空でない場合のみ追加
                experience = Experience(year=year, description=desc, profile_id=profile.id)
                db.session.add(experience)

        # スキルを更新
        Skill.query.filter_by(profile_id=profile.id).delete()  # 既存のスキルを削除
        skill_names = request.form.getlist("skill_name")
        skill_descriptions = request.form.getlist("skill_description")
        skill_images = request.files.getlist("skill_image")
        skill_levels = request.form.getlist("skill_level")
        existing_skill_images = request.form.getlist("existing_skill_image")  # 既存の画像も取得

        # インデックスを使ってスキルを追加する
        for index in range(len(skill_names)):
            skill_name = skill_names[index]
            skill_description = skill_descriptions[index]
            skill_image = skill_images[index] if index < len(skill_images) else None
            skill_level = skill_levels[index]
            existing_image_url = existing_skill_images[index] if index < len(existing_skill_images) else None

            # 新しい画像がアップロードされたかどうかを確認
            if skill_image and allowed_file(skill_image.filename):
                filename = secure_filename(skill_image.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                skill_image.save(filepath)  # サーバーに画像を保存
            else:
                # 画像がアップロードされなかった場合、既存の画像を使用
                filepath = existing_image_url if existing_image_url else None
            
            skill = Skill(
                name=skill_name, 
                description=skill_description, 
                image_url=filepath, 
                profile_id=profile.id, 
                level=int(skill_level)
            )
            db.session.add(skill)

        # プロジェクトを更新
        Project.query.filter_by(profile_id=profile.id).delete()  # 既存のプロジェクトを削除
        for name, desc, link, link_text in zip(request.form.getlist("proj_name"), 
                                                request.form.getlist("proj_desc"), 
                                                request.form.getlist("proj_link"),
                                                request.form.getlist("proj_link_text")):  # リンクテキストを追加
            if name and desc and link:  # 空でない場合のみ追加
                project = Project(name=name, description=desc, link=link, link_text=link_text, profile_id=profile.id)
                db.session.add(project)

        db.session.commit()  # 変更をデータベースに保存
        
        # ログアウト処理
        session.pop('logged_in', None)
        
        return redirect(url_for('home'))
    
    return render_template('edit.html', profile=profile)

if __name__ == '__main__':
    app.run(debug=True)
