# Simple Expense Tracker

This version contains only normal visible files. You do not need to upload
`.devcontainer`, `.streamlit`, or `data`.

## Upload to GitHub

Upload these files directly to the root of a GitHub repository:

- `streamlit_app.py`
- `database.py`
- `requirements.txt`
- `README.md`

## Run without a terminal

1. Go to Streamlit Community Cloud.
2. Sign in with GitHub.
3. Select **Create app**.
4. Choose your repository.
5. Set the main file path to `streamlit_app.py`.
6. Select **Deploy**.

The app creates the `data` folder and SQLite database automatically.

## Important storage note

Streamlit Community Cloud may restart or rebuild the app, so a local SQLite
database is not guaranteed to be permanent. Export your transactions to CSV
regularly. For permanent cloud storage, connect the app to a hosted database.
