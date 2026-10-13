# Раскатка Intention на сервер (atoomyk.ru)

Домен: `https://atoomyk.ru`. В `server_name` оставлен и `www.atoomyk.ru`:
сертификат выдан на оба имени, иначе автопродление может ругаться.
Путь деплоя: `/opt/intention`, данные: `/opt/intention/data`.
Пользователь сервиса: `intention`.
Приложение слушает только `127.0.0.1:8000`, наружу — nginx с HTTPS.

Все команды ниже — на сервере (Ubuntu/Debian, нужен root/sudo).

Состояние сервера `atoomyk.ru` (31.77.78.166) на момент переноса: шаги 1–5 уже выполнены —
пользователь `intention`, код в `/opt/intention`, сервис `intention` запущен и проверен после перезагрузки.
Старый сайт `pulse` (`/opt/pulse`, `/var/www/pulse`, `pulse-api.service`) удалён. Осталось включить nginx-сайт (шаг 6).

## 0. Что должно быть готово заранее

- Сервер с IP, доступ по SSH.
- DNS: A-запись `atoomyk.ru` → этот IP (проверить: `dig +short atoomyk.ru`).
- Локально у вас уже есть `run_web.sh`, `deploy/` и правки в `server/app.py`.

## 1. Пакеты

```bash
sudo apt update
sudo apt install -y python3 python3-venv nginx certbot python3-certbot-nginx sqlite3 rsync curl
python3 --version   # ожидается 3.10+
```

## 2. Пользователь и каталоги

```bash
sudo useradd --system --home /opt/intention --shell /usr/sbin/nologin intention
sudo mkdir -p /opt/intention
sudo chown -R intention:intention /opt/intention
sudo chmod 750 /opt/intention
```

## 3. Перенос кода

Вариант A — с вашей машины (git-bash/WSL в папке проекта):

```bash
rsync -av --delete \
  --exclude '.venv/' --exclude 'data/' --exclude '__pycache__/' \
  --exclude 'dist/' --exclude 'build/' --exclude 'save.json' --exclude '.idea/' \
  ./ user@atoomyk.ru:/tmp/intention/
```

затем на сервере:

```bash
sudo rsync -a /tmp/intention/ /opt/intention/ && rm -rf /tmp/intention
```

Вариант B — репозиторий (если заведёте git): `sudo -u intention git clone <repo> /opt/intention`.

Проверьте права после копирования:

```bash
sudo chown -R intention:intention /opt/intention
sudo chmod 750 /opt/intention /opt/intention/deploy /opt/intention/server /opt/intention/web
```

## 4. Окружение и зависимости

```bash
cd /opt/intention
sudo chmod +x run_web.sh
sudo -u intention ./run_web.sh
```

Скрипт создаст `.venv`, поставит `server/requirements.txt`, создаст `data/` и запустит uvicorn.
Убедились, что в консоли нет ошибок → `Ctrl+C`.

```bash
sudo chmod 700 /opt/intention/data
sudo chmod 600 /opt/intention/data/secret.key   # если файл уже появился
```

`secret.key` — ключ подписи сессий. Если его потерять, все пользователи разлогинятся. Резервировать обязательно, в репозиторий не класть.

## 5. Автозапуск (systemd)

```bash
sudo cp /opt/intention/deploy/intention.service /etc/systemd/system/intention.service
sudo systemctl daemon-reload
sudo systemctl enable --now intention
systemctl status intention --no-pager
journalctl -u intention -n 50 --no-pager
```

Проверка без интернета:

```bash
curl -s http://127.0.0.1:8000/api/health     # {"ok":true}
```

## 6. nginx + HTTPS

Конфиг ссылается на `/etc/letsencrypt/live/atoomyk.ru/...`, поэтому порядок зависит от того, есть ли сертификат: `sudo certbot certificates`.

Сертификат уже есть (обычный случай для этого сервера):

```bash
sudo mkdir -p /var/www/certbot
sudo cp /opt/intention/deploy/atoomyk.ru.conf /etc/nginx/sites-available/atoomyk.ru.conf
sudo ln -sf /etc/nginx/sites-available/atoomyk.ru.conf /etc/nginx/sites-enabled/atoomyk.ru.conf
sudo nginx -t && sudo systemctl reload nginx
```

Сертификата нет: получаем перед включением конфига (nginx на время останавливаем) и только потом включаем сайт:

```bash
sudo mkdir -p /var/www/certbot
sudo systemctl stop nginx
sudo certbot certonly --standalone -d atoomyk.ru -d www.atoomyk.ru
sudo systemctl start nginx
```

Заглушку по умолчанию можно отключить, если она мешает: `sudo rm -f /etc/nginx/sites-enabled/default`.

Продление: `systemctl status certbot.timer`, проверка без реального продления — `sudo certbot renew --dry-run`.

Примечание: на nginx 1.25+ строка `listen 443 ssl http2;` устарела — можно заменить на `listen 443 ssl;` + `http2 on;` (на Ubuntu 24.04 с nginx 1.24 текущий вариант ещё valid).

## 7. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
sudo ufw status
```

Порт 8000 наружу **не открывать**.

## 8. Проверка «всё живое»

```bash
curl -sI https://atoomyk.ru | head -1              # 200
curl -s  https://atoomyk.ru/api/health             # {"ok":true}
curl -sI https://atoomyk.ru/docs | head -1         # 404 (документация закрыта)
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://atoomyk.ru/api/login \
  -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}'   # 401
```

Затем в браузере: регистрация → вход → игра → «Статистика» (лидерборд) → перезагрузка страницы (сессия сохраняется) → `sudo systemctl restart intention` → сессия всё ещё жива.

## 9. Обновление версии

```bash
# залить новый код в /tmp/intention (rsync, как в шаге 3), затем:
sudo rsync -a --delete --exclude 'data/' --exclude '.venv/' /tmp/intention/ /opt/intention/
sudo chown -R intention:intention /opt/intention
sudo -u intention /opt/intention/.venv/bin/pip install -r /opt/intention/server/requirements.txt
sudo systemctl restart intention
```

`data/` и `.venv/` при таком обновлении не трогаются — пользователи и сессии сохраняются.

## 10. Резервные копии

```bash
sudo mkdir -p /var/backups/intention
sudo crontab -e
```

Строка (снимок БД + ключ каждый день в 04:00):

```cron
0 4 * * * sqlite3 /opt/intention/data/intention.db ".backup '/var/backups/intention/intention-$(date +\%F).db'" && cp -p /opt/intention/data/secret.key /var/backups/intention/secret.key
```

Восстановление: остановить сервис, вернуть `.db` и `secret.key` на место, запустить сервис.

## 11. Если что-то не работает

| Симптом | Что смотреть |
|---|---|
| `502 Bad Gateway` | `systemctl status intention`, `journalctl -u intention -n 100` |
| `database is locked` | один воркер uvicorn (в unit так и есть); проверить права на `data/` |
| `Permission denied` при записи в `data/` | владелец и `chmod 700 data`, `ReadWritePaths` в unit |
| Все сессии слетели | пропал или заменён `data/secret.key` (восстановить из бэкапа) |
| `nginx -t` падает на ssl | нет файлов в `/etc/letsencrypt/live/atoomyk.ru/` — получить сертификат: `systemctl stop nginx && certbot certonly --standalone -d atoomyk.ru -d www.atoomyk.ru && systemctl start nginx` |
| Не грузит `app.js`/`styles.css` | пути в приложении абсолютные: приложение должно стоять в корне домена, а не в подпапке |
| Пустая страница после логина | открыть консоль браузера, посмотреть ответы `/api/me`, `/api/leaderboard` |
