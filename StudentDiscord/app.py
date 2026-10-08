
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, join_room
import secrets


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = "student-discord-secret-key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///student.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*"
)


# =========================================================
# LOGIN MANAGER
# =========================================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"


# =========================================================
# ONLINE USERS
# =========================================================

online_users = {}


# =========================================================
# SERVER MEMBERS ASSOCIATION TABLE
# =========================================================

server_members = db.Table(
    "server_members",

    db.Column(
        "student_id",
        db.Integer,
        db.ForeignKey("student.id"),
        primary_key=True
    ),

    db.Column(
        "server_id",
        db.Integer,
        db.ForeignKey("server.id"),
        primary_key=True
    )
)


# =========================================================
# STUDENT MODEL
# =========================================================

class Student(UserMixin, db.Model):

    __tablename__ = "student"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(255),
        nullable=False
    )

    # Servers owned by this student
    servers = db.relationship(
        "Server",
        backref="owner",
        lazy=True
    )

    # Messages sent by this student
    messages = db.relationship(
        "Message",
        backref="sender",
        lazy=True
    )

    # Servers joined by this student
    joined_servers = db.relationship(
        "Server",
        secondary=server_members,
        back_populates="members"
    )


# =========================================================
# SERVER MODEL
# =========================================================

class Server(db.Model):

    __tablename__ = "server"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    description = db.Column(
        db.String(255)
    )

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("student.id"),
        nullable=False
    )

    invite_code = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    # Server channels
    channels = db.relationship(
        "Channel",
        backref="server",
        lazy=True,
        cascade="all, delete-orphan"
    )

    # Server members
    members = db.relationship(
        "Student",
        secondary=server_members,
        back_populates="joined_servers"
    )


# =========================================================
# CHANNEL MODEL
# =========================================================

class Channel(db.Model):

    __tablename__ = "channel"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    server_id = db.Column(
        db.Integer,
        db.ForeignKey("server.id"),
        nullable=False
    )

    messages = db.relationship(
        "Message",
        backref="channel",
        lazy=True,
        cascade="all, delete-orphan"
    )


# =========================================================
# MESSAGE MODEL
# =========================================================

class Message(db.Model):

    __tablename__ = "message"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    content = db.Column(
        db.Text,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now()
    )

    channel_id = db.Column(
        db.Integer,
        db.ForeignKey("channel.id"),
        nullable=False
    )

    sender_id = db.Column(
        db.Integer,
        db.ForeignKey("student.id"),
        nullable=False
    )


# =========================================================
# LOGIN USER LOADER
# =========================================================

@login_manager.user_loader
def load_user(user_id):

    try:

        return db.session.get(
            Student,
            int(user_id)
        )

    except (ValueError, TypeError):

        return None


# =========================================================
# HOME / DASHBOARD
# =========================================================

@app.route("/")
@login_required
def home():

    owned_servers = current_user.servers

    joined_servers = current_user.joined_servers

    all_servers = []

    for server in owned_servers:

        if server not in all_servers:

            all_servers.append(server)

    for server in joined_servers:

        if server not in all_servers:

            all_servers.append(server)

    return render_template(
        "dashboard.html",
        servers=all_servers
    )
# =========================================================
# PROFILE
# =========================================================
@app.route("/profile")
@login_required
def profile():

    return render_template(
        "profile.html"
    )

@app.route("/profile/<int:student_id>")
@login_required
def student_profile(student_id):

    student = db.session.get(
        Student,
        student_id
    )

    if not student:
        return "Student not found!", 404

    return render_template(
        "student_profile.html",
        student=student
    )
# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        if not username or not email or not password:

            return "All fields are required!", 400

        existing_student = Student.query.filter(
            (Student.username == username) |
            (Student.email == email)
        ).first()

        if existing_student:

            return "Username or email already exists!", 400

        hashed_password = generate_password_hash(
            password
        )

        student = Student(
            username=username,
            email=email,
            password=hashed_password
        )

        db.session.add(student)

        db.session.commit()

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        student = Student.query.filter_by(
            email=email
        ).first()

        if student and check_password_hash(
            student.password,
            password
        ):

            login_user(student)

            return redirect(
                url_for("home")
            )

        return "Invalid email or password!", 401

    return render_template(
        "login.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
@login_required
def logout():

    if current_user.id in online_users:

        del online_users[
            current_user.id
        ]

    logout_user()

    return redirect(
        url_for("login")
    )


# =========================================================
# CREATE SERVER
# =========================================================

@app.route(
    "/create-server",
    methods=["GET", "POST"]
)
@login_required
def create_server():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not name:

            return "Server name is required!", 400

        # Generate unique invite code
        invite_code = secrets.token_urlsafe(6)

        while Server.query.filter_by(
            invite_code=invite_code
        ).first():

            invite_code = secrets.token_urlsafe(6)

        server = Server(
            name=name,
            description=description,
            owner_id=current_user.id,
            invite_code=invite_code
        )

        # Owner automatically becomes member
        server.members.append(current_user)

        db.session.add(server)

        db.session.flush()

        # Create default general channel
        general_channel = Channel(
            name="general",
            server_id=server.id
        )

        db.session.add(general_channel)

        db.session.commit()

        return redirect(
            url_for(
                "server_page",
                server_id=server.id
            )
        )

    return render_template(
        "create_server.html"
    )


# =========================================================
# SERVER PAGE
# =========================================================

@app.route(
    "/server/<int:server_id>"
)
@login_required
def server_page(server_id):

    server = db.session.get(
        Server,
        server_id
    )

    if not server:

        return "Server not found!", 404

    # Check membership
    if current_user not in server.members:

        return redirect(
            url_for("home")
        )

    return render_template(
        "server.html",
        server=server
    )


# =========================================================
# CREATE CHANNEL
# =========================================================

@app.route(
    "/server/<int:server_id>/create-channel",
    methods=["POST"]
)
@login_required
def create_channel(server_id):

    server = db.session.get(
        Server,
        server_id
    )

    if not server:

        return "Server not found!", 404

    # Only owner
    if server.owner_id != current_user.id:

        return "You are not the server owner!", 403

    channel_name = request.form.get(
        "name",
        ""
    ).strip()

    if not channel_name:

        return "Channel name cannot be empty!", 400

    # Prevent duplicate channel names
    existing_channel = Channel.query.filter_by(
        server_id=server.id,
        name=channel_name
    ).first()

    if existing_channel:

        return "Channel already exists!", 400

    channel = Channel(
        name=channel_name,
        server_id=server.id
    )

    db.session.add(channel)

    db.session.commit()

    return redirect(
        url_for(
            "server_page",
            server_id=server.id
        )
    )


# =========================================================
# CHANNEL PAGE
# =========================================================

@app.route(
    "/server/<int:server_id>/channel/<int:channel_id>"
)
@login_required
def channel_page(
    server_id,
    channel_id
):

    server = db.session.get(
        Server,
        server_id
    )

    if not server:

        return "Server not found!", 404

    # Student must belong to server
    if current_user not in server.members:

        return redirect(
            url_for("home")
        )

    channel = db.session.get(
        Channel,
        channel_id
    )

    if not channel:

        return "Channel not found!", 404

    # Make sure channel belongs to this server
    if channel.server_id != server.id:

        return "Channel does not belong to this server!", 403

    messages = Message.query.filter_by(
        channel_id=channel.id
    ).order_by(
        Message.created_at.asc()
    ).all()

    return render_template(
        "channel.html",
        server=server,
        channel=channel,
        messages=messages
    )


# =========================================================
# JOIN SERVER
# =========================================================

@app.route(
    "/join-server",
    methods=["GET", "POST"]
)
@login_required
def join_server():

    if request.method == "POST":

        invite_code = request.form.get(
            "invite_code",
            ""
        ).strip()

        if not invite_code:

            return "Invite code is required!", 400

        server = Server.query.filter_by(
            invite_code=invite_code
        ).first()

        if not server:

            return "Invalid invite code!", 404

        # Already a member
        if current_user in server.members:

            return redirect(
                url_for(
                    "server_page",
                    server_id=server.id
                )
            )

        server.members.append(
            current_user
        )

        db.session.commit()

        return redirect(
            url_for(
                "server_page",
                server_id=server.id
            )
        )

    return render_template(
        "join_server.html"
    )


# =========================================================
# SERVER MEMBERS API
# =========================================================

@app.route(
    "/api/server/<int:server_id>/members"
)
@login_required
def server_members_api(server_id):

    server = db.session.get(
        Server,
        server_id
    )

    if not server:

        return {
            "error": "Server not found"
        }, 404

    if current_user not in server.members:

        return {
            "error": "Access denied"
        }, 403

    members = []

    for student in server.members:

        members.append({
            "id": student.id,
            "username": student.username,
            "online": student.id in online_users
        })

    # Online members first
    members.sort(
        key=lambda member: (
            not member["online"],
            member["username"].lower()
        )
    )

    return {
        "members": members
    }


# =========================================================
# SOCKET.IO CONNECT
# =========================================================

@socketio.on("connect")
def socket_connect():

    if not current_user.is_authenticated:

        return False

    online_users[current_user.id] = {
        "username": current_user.username
    }

    print(
        f"[ONLINE] {current_user.username}"
    )


# =========================================================
# SOCKET.IO DISCONNECT
# =========================================================

@socketio.on("disconnect")
def socket_disconnect():

    if not current_user.is_authenticated:

        return

    if current_user.id in online_users:

        del online_users[
            current_user.id
        ]

        print(
            f"[OFFLINE] {current_user.username}"
        )


# =========================================================
# JOIN CHANNEL
# =========================================================

@socketio.on("join_channel")
def socket_join_channel(data):

    if not current_user.is_authenticated:

        return

    try:

        channel_id = int(
            data.get("channel_id")
        )

    except (
        TypeError,
        ValueError
    ):

        return

    channel = db.session.get(
        Channel,
        channel_id
    )

    if not channel:

        return

    # Check membership
    if current_user not in channel.server.members:

        return

    room = f"channel_{channel_id}"

    join_room(room)

    print(
        f"{current_user.username} joined {room}"
    )


# =========================================================
# SEND MESSAGE
# =========================================================

@socketio.on("send_message")
def socket_send_message(data):

    if not current_user.is_authenticated:

        return

    try:

        channel_id = int(
            data.get("channel_id")
        )

    except (
        TypeError,
        ValueError
    ):

        return

    content = data.get(
        "content",
        ""
    )

    if content is None:

        return

    content = str(content).strip()

    if not content:

        return

    # Limit message length
    if len(content) > 2000:

        content = content[:2000]

    channel = db.session.get(
        Channel,
        channel_id
    )

    if not channel:

        return

    # Make sure student belongs to server
    if current_user not in channel.server.members:

        print(
            f"[DENIED] {current_user.username}"
        )

        return

    try:

        message = Message(
            content=content,
            channel_id=channel.id,
            sender_id=current_user.id
        )

        db.session.add(message)

        db.session.commit()

        # Make sure server-generated values are loaded
        db.session.refresh(message)

        created_time = ""

        if message.created_at:

            created_time = message.created_at.strftime(
                "%H:%M"
            )

        socketio.emit(
            "receive_message",
            {
                "id": message.id,
                "username": current_user.username,
                "content": message.content,
                "created_at": created_time
            },
            room=f"channel_{channel.id}"
        )

        print(
            f"[MESSAGE] "
            f"{current_user.username}: "
            f"{message.content}"
        )

    except Exception as e:

        db.session.rollback()

        print(
            "[MESSAGE ERROR]",
            e
        )


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

with app.app_context():

    db.create_all()


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("       STUDENT DISCORD SERVER")
    print("========================================")
    print()
    print("Open:")
    print("http://127.0.0.1:5000")
    print()

    socketio.run(
        app,
        debug=True
    )

