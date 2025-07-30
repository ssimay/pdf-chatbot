# app.py 
import os
from flask import Flask, render_template, request, session, redirect, url_for, flash
from werkzeug.utils import secure_filename
from query import query_rag
from ingest import ingest_pdf_to_chroma 
import uuid
from dotenv import load_dotenv

from db_manager import load_db_index, save_db_index, add_pdf_to_index, remove_pdf_from_index, get_chroma_path_by_pdf_name, clear_database_and_index_entry, CHROMA_DB_DIR

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/', methods=['GET', 'POST'])
def chat():
    if 'history' not in session:
        session['history'] = []
    if 'remember' not in session:
        session['remember'] = True
    if 'active_chroma_path' not in session:
        session['active_chroma_path'] = None
    if 'active_pdf_name' not in session:
        session['active_pdf_name'] = None

    remember = session.get('remember', True)

    if request.method == 'POST':
        question = request.form['question']
        remember_from_form = 'remember' in request.form
        session['remember'] = remember_from_form

        current_chroma_path = session.get('active_chroma_path')

        if not current_chroma_path:
            bot_message = "Please upload a PDF or select an existing one to start the conversation."
            session['history'].append({'sender': 'user', 'message': question})
            session['history'].append({'sender': 'bot', 'message': bot_message})
        else:
            db_index = load_db_index()
            if not os.path.exists(current_chroma_path) or current_chroma_path not in db_index.values():
                flash("The previously loaded PDF's data is no longer available. Please upload the PDF again or select another.", 'error')
                session['active_chroma_path'] = None
                session['active_pdf_name'] = None
                session['history'] = [] 
                return redirect(url_for('chat'))

            if remember_from_form:
                answer = query_rag(question, history=session['history'], use_history=True, chroma_path=current_chroma_path)
            else:
                answer = query_rag(question, history=[], use_history=False, chroma_path=current_chroma_path)

            session['history'].append({'sender': 'user', 'message': question})
            session['history'].append({'sender': 'bot', 'message': answer})

        session.modified = True

    display_history = session['history'][-20:]
    available_pdfs = load_db_index().keys() 

    return render_template(
        'index.html',
        history=display_history,
        remember=session.get('remember', True),
        active_pdf_name=session.get('active_pdf_name'),
        available_pdfs=sorted(list(available_pdfs)) 
    )

@app.route("/upload", methods=["POST"])
def upload_pdf():
    if 'pdf_file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('chat'))
    file = request.files['pdf_file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('chat'))
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(upload_filepath)

        existing_chroma_path_for_name = get_chroma_path_by_pdf_name(filename)
        if existing_chroma_path_for_name:
            clear_database_and_index_entry(filename)
            flash(f"Replacing existing data for '{filename}'.", 'info')

        unique_db_id = str(uuid.uuid4())
        new_chroma_db_path = os.path.join(CHROMA_DB_DIR, unique_db_id)
        os.makedirs(new_chroma_db_path, exist_ok=True)

        if session.get('active_chroma_path') and session['active_chroma_path'] != new_chroma_db_path:
            pass

        try:
            flash(f'Processing "{filename}"... This may take a moment. Please wait.', 'info')
            ingest_pdf_to_chroma(upload_filepath, new_chroma_db_path)

            add_pdf_to_index(filename, new_chroma_db_path)

            session['active_chroma_path'] = new_chroma_db_path
            session['active_pdf_name'] = filename
            session['history'] = []
            flash(f'Successfully loaded "{filename}"! You can now ask questions.', 'success')
        except Exception as e:
            flash(f'Error processing PDF "{filename}": {e}', 'error')
            clear_database_and_index_entry(filename) 
            session['active_chroma_path'] = None
            session['active_pdf_name'] = None
        finally:
            if os.path.exists(upload_filepath):
                os.remove(upload_filepath)

    else:
        flash('Invalid file type. Only PDFs are allowed.', 'error')

    return redirect(url_for('chat'))

@app.route("/set_active_pdf", methods=["POST"])
def set_active_pdf():
    pdf_name_to_load = request.form.get('pdf_name')
    if not pdf_name_to_load:
        flash("No PDF selected.", 'error')
        return redirect(url_for('chat'))

    chroma_path = get_chroma_path_by_pdf_name(pdf_name_to_load)

    if not chroma_path or not os.path.exists(chroma_path):
        flash(f"Data for '{pdf_name_to_load}' not found or database directory missing. Please re-upload.", 'error')
        remove_pdf_from_index(pdf_name_to_load) 
        session['active_chroma_path'] = None
        session['active_pdf_name'] = None
        session['history'] = []
        return redirect(url_for('chat'))

    session['active_chroma_path'] = chroma_path
    session['active_pdf_name'] = pdf_name_to_load
    session['history'] = [] 
    flash(f"Switched to '{pdf_name_to_load}'.", 'info')
    session.modified = True
    return redirect(url_for('chat'))


@app.route('/reset')
def reset():
    if session.get('active_pdf_name'):
        clear_database_and_index_entry(session['active_pdf_name'])

    session['history'] = []
    session['active_chroma_path'] = None
    session['active_pdf_name'] = None

    flash('Conversation and active PDF context reset.', 'info')
    session.modified = True
    return redirect(url_for('chat'))

@app.route('/delete_pdf', methods=['POST'])
def delete_pdf():
    pdf_name_to_delete = request.form.get('pdf_name')
    if not pdf_name_to_delete:
        flash("No PDF selected for deletion.", 'error')
        return redirect(url_for('chat'))

    if session.get('active_pdf_name') == pdf_name_to_delete:
        session['active_chroma_path'] = None
        session['active_pdf_name'] = None
        session['history'] = []

    clear_database_and_index_entry(pdf_name_to_delete)
    flash(f"'{pdf_name_to_delete}' and its data have been removed.", 'success')
    session.modified = True
    return redirect(url_for('chat'))


if __name__ == '__main__':
    load_db_index()
    if not os.environ.get('FLASK_SECRET_KEY'):
        print("WARNING: FLASK_SECRET_KEY environment variable not set. Using a temporary key.")
        print("For production, set a strong, random FLASK_SECRET_KEY.")
    app.run(debug=True)