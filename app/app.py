from flask import Flask, request, send_file, render_template, jsonify
import flask_cors
import subprocess
import hashlib
import os

app = Flask(__name__)
flask_cors.CORS(app)

TEMP_DIR = 'temp'
MIMETYPES = {
    'pdf': 'application/pdf',
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


def clean_temp_dir():
    """Deletes all files in the temp directory."""
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

    # Compile with chosen LaTeX engine
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
    # print('LaTeX STDERR:', err)
    # if not success:
    #     raise RuntimeError(f"LaTeX failed: {err or out}")

    # If another format is requested, convert with pandoc
    if format != 'pdf' and format != 'bmp':
        output_path = os.path.join(TEMP_DIR, f"{hashed}.{format}")
        pandoc_args = f"pandoc {tex_path.replace(os.sep, '/')} -o {output_path}"
        success, out, err = run_subprocess(pandoc_args, shell=True)
        print('Pandoc STDOUT:', out)
        print('Pandoc STDERR:', err)
        if not success:
            raise RuntimeError(f"Pandoc failed: {err or out}")
    elif format == 'bmp':
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
        path = os.path.join(TEMP_DIR, f"{hashed}.{format}")
        print(path, '@@@@@@')
        if not os.path.exists(path):
            print(path, '←')
            return jsonify({"error": f"File generation failed ({path} does not exist.)"}), 500

        return send_file(
            fr'.\temp\{hashed}.{format}',
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
