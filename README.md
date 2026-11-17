# PAVEL BOT HOSTING — Render-ready starter

## Deploy
1. Create a GitHub repository and upload the contents of this folder (not the outer folder).
2. In Render, choose **New + → Blueprint** and connect the repository. Render reads `render.yaml`.
   Alternatively create a **Web Service**, choose Python, build command `pip install -r requirements.txt`,
   start command `gunicorn app:app --workers 1 --threads 4 --timeout 120`.
3. If using manual Web Service setup, add `SECRET_KEY` as a long random secret in Environment.
   With Blueprint deployment, Render generates it automatically.
4. Deploy and open the `onrender.com` URL.

## Included
- Registration and login
- SQLite user database
- Two uploaded project slots per account
- `.py` and `.zip` upload (20 MB max)
- Requirements text storage
- Delete uploaded project

## Important limitations
This is a deployable **file-management starter**, not a live arbitrary-code execution service.
The Start / Stop / Restart controls deliberately do not execute uploaded Python code. Running code
uploaded by public users requires a separately isolated worker/sandbox with strict CPU, memory,
network, filesystem and time limits. Do not enable unrestricted `subprocess` execution inside the
public Flask web service.

Render Free web services can sleep and their local filesystem is ephemeral. Data stored on the
instance may be lost on restart/redeploy; this starter uses `/tmp` by default. For persistent user
accounts/uploads you need persistent storage or an external database/object storage service, which
may not be free. A generated SECRET_KEY can also change if you do not configure it manually,
which can log users out after a restart.

No one can guarantee a zero-error deployment across all Render account settings or future platform
changes. Check the Render deploy logs if deployment fails.
