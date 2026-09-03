import os, sys, requests

KEY = os.environ["DROPBOX_APP_KEY"]
SECRET = os.environ["DROPBOX_APP_SECRET"]
REFRESH = os.environ["DROPBOX_REFRESH_TOKEN"]
REMOTE = "/archive.db"

def token():
    r = requests.post("https://api.dropboxapi.com/oauth2/token", data={
        "grant_type": "refresh_token", "refresh_token": REFRESH,
        "client_id": KEY, "client_secret": SECRET})
    print(f"Status: {r.status_code}")

    r.raise_for_status()
    return r.json()["access_token"]

if sys.argv[1] == "download":
    r = requests.post("https://content.dropboxapi.com/2/files/download",
        headers={"Authorization": f"Bearer {token()}",
                 "Dropbox-API-Arg": f'{{"path": "{REMOTE}"}}'})
    if r.status_code == 200:
        open("data/archive.db", "wb").write(r.content)
        print("База скачана")
    else:
        print(f"Базы ещё нет (код {r.status_code}), начинаем с пустой")
else:
    r = requests.post("https://content.dropboxapi.com/2/files/upload",
        headers={"Authorization": f"Bearer {token()}",
                 "Dropbox-API-Arg": f'{{"path": "{REMOTE}", "mode": "overwrite"}}',
                 "Content-Type": "application/octet-stream"},
        data=open("data/archive.db", "rb").read())
    r.raise_for_status()
    print("База залита")