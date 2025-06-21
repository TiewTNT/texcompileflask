from io import BytesIO
from pdfminer.pdfinterp import PDFResourceManager
from io import StringIO
from pdfminer.converter import HTMLConverter
from pdfminer.layout import LAParams
from pdfminer.high_level import extract_text_to_fp
from flask import Flask, request, send_file, render_template, jsonify
import flask_cors
import subprocess
import hashlib
import os
import zipfile
import regex as re

app = Flask(__name__)
flask_cors.CORS(app)

# Directory where temporary compilation files will be stored.  Use an absolute
# path so Flask can reliably locate the generated output regardless of the
# current working directory.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TEMP_DIR = os.path.join(BASE_DIR, 'temp')
print('Using temp directory:', TEMP_DIR)
MIMETYPES = {
    'pdf': 'application/pdf',
    'zip': 'application/zip',
    'txt': 'text/plain',
    'html': 'text/html',
    'md': 'text/markdown',
    'png':  'image/png',
    'jpg':  'image/jpeg',
    'webp': 'image/webp',
    'gif':  'image/gif',
    'tiff': 'image/tiff',
    'avif': 'image/avif',
    'bmp':  'image/bmp',
}


def pdf_to_html(pdf_path, output_html_path):
    """
    Convert a PDF to HTML using pdfminer.six without triggering codec-on-text-stream errors.
    """
    laparams = LAParams()
    buffer = BytesIO()

    # Extract HTML into a binary buffer (BytesIO honours the default 'utf-8' codec)
    with open(pdf_path, 'rb') as pdf_file:
        extract_text_to_fp(
            pdf_file,
            buffer,
            laparams=laparams,
            output_type='html'
        )

    # Decode once, then write to your text file
    html = buffer.getvalue().decode('utf-8')
    buffer.close()

    with open(output_html_path, 'w', encoding='utf-8') as html_file:
        html_file.write(html)


def clean_temp_dir():
    """Ensure the temp directory exists and remove all files inside it."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    for filename in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, filename)
        try:
            os.remove(file_path)
            print(f"Deleted: {filename}")
        except Exception as e:
            print(f"Failed to delete {filename}: {e}")


def run_subprocess(args, shell=False, cwd='.'):
    """Run subprocess and return success, stdout, and stderr."""
    try:
        result = subprocess.run(
            args,
            shell=shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60  # don’t let it hang forever
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, '', str(e)


def process_json(data):
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)

    hashed = hashlib.sha256(str(data).encode()).hexdigest()
    engine = data.get('engine', 'pdflatex')
    name = os.path.splitext(data.get('name', 'file'))[0]
    format = data.get('format', 'pdf')

    tex_filename = f'{hashed}.tex'
    tex_path = os.path.join(TEMP_DIR, tex_filename)

    # Write TeX file
    with open(tex_path, 'w', encoding='utf-8') as f:
        f.write(data.get('tex', 'user did not send TeX'))

    if engine == "context":
        args = [
            'context',
            '--batchmode',               # quiet mode (like nonstopmode)
            f'--result={hashed}.pdf',
            f'--path={TEMP_DIR}',
            tex_filename.replace(os.sep, '/')
        ]
        success, out, err = run_subprocess(args, cwd=TEMP_DIR)
    else:
        args = [
            engine,
            f'-jobname={hashed}',
            '-interaction=nonstopmode',
            f'-output-directory={TEMP_DIR}',
            tex_path.replace(os.sep, '/')
        ]
        success, out, err = run_subprocess(args)
    print('LaTeX STDOUT:', out)
    print('LaTeX STDERR:', err)

    if format == 'bmp':
        dpi = data.get('dpi', 200)
        pdf_path = os.path.join(TEMP_DIR, f"{hashed}.pdf")
        r_path = os.path.join(
            TEMP_DIR, f"{hashed}.{data.get('imgFormat', 'png')}")

        # run convert without shell (safer) and with full paths
        success, out, err = run_subprocess([
            'magick',
            '-density', str(dpi),
            pdf_path.replace(os.sep, '/'),
            '-background', 'white',
            '-alpha', 'remove',
            '-alpha', 'off',
            r_path.replace(os.sep, '/')
        ], shell=False)

        print('ImageMagick STDOUT:', out)
        print('ImageMagick STDERR:', err)
        if not success:
            raise RuntimeError(f"ImageMagick convert failed: {err or out}")

        format = data.get('imgFormat', 'png')
        print('BMP branch: wrote', r_path)
    elif format != 'pdf':
        if format in ['html', 'md']:
            pdf_to_html(os.path.join(TEMP_DIR, f"{hashed}.pdf"), os.path.join(
                TEMP_DIR, f"{hashed}.html"))
            output_path = os.path.join(TEMP_DIR, f"{hashed}.{format}")
            input_path = '/'.join([TEMP_DIR, f"{hashed}.html"])
        else:
            output_path = os.path.join(TEMP_DIR, f"{hashed}.{format}")
            input_path = '/'.join([TEMP_DIR, f"{hashed}.html"])
        pandoc_args = [
    "pandoc",
    "-f", "html" if format in ['html', 'md'] else "latex",
    input_path,
    "-o", output_path,
]

        if format == 'md':
            pandoc_args.insert(1, "--markdown-fenced_divs")

        success, out, err = run_subprocess(pandoc_args)
        print('Pandoc STDOUT:', out)
        print('Pandoc STDERR:', err)

        if not success:
            raise RuntimeError(f"Pandoc failed: {err or out}")

        print('Converted to', output_path)

    return hashed, format, name


@app.route('/')
def home():
    return render_template('app.html')


@app.route('/api', methods=['POST'])
def api():
    clean_temp_dir()
    incoming_data = request.get_json()
    try:
        hashed, format, name = process_json(incoming_data)
        print(format, '====================')

        if len([f for f in os.listdir(TEMP_DIR) if re.compile(rf"{hashed}-\d+\.{format}").match(f)]) > 1:
            with zipfile.ZipFile(os.path.join(TEMP_DIR, f"{hashed}.zip"), 'w', zipfile.ZIP_DEFLATED) as zip_file:
                pattern = re.compile(rf"{hashed}-\d+\.{format}")
                for filename in os.listdir(TEMP_DIR):
                    if pattern.match(filename):
                        full_path = os.path.join(TEMP_DIR, filename)
                        zip_file.write(full_path, arcname=name +
                                       '-'+filename.split('-')[1])
                format = "zip"
        path = os.path.join(TEMP_DIR, f"{hashed}.{format}")
        print(path, '@@@@@@')
        if not os.path.exists(path):
            print(path, '←')
            return jsonify({"error": f"File generation failed ({path} does not exist.)"}), 500

        return send_file(
            path,
            mimetype=MIMETYPES.get(format, 'application/octet-stream'),
            as_attachment=True,
            download_name=f"{name}.{format}"
        )
    except Exception as e:
        print('Error:', e)
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
    app.run()
