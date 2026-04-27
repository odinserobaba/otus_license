# Deploy In Russia (API-ready)

Этот набор файлов помогает развернуть проект на Linux-сервере в РФ и обеспечить доступ веба к внешним API (Yandex Cloud / AITunnel).

## Рекомендуемые площадки в РФ

- `Yandex Cloud` (рекомендуется для этого проекта): простая связка с Yandex API, дата-центры в РФ, удобный VPC/Firewall.
- `Selectel Cloud`: стабильные VM в РФ, подходит для классического VPS-деплоя.
- `VK Cloud`: альтернативная облачная площадка в РФ с IaaS и managed-сервисами.
- `Timeweb Cloud`: бюджетный вариант для курсового/демо окружения.

## Минимальная конфигурация VM

- Ubuntu 22.04/24.04
- 2 vCPU, 4-8 GB RAM, 30+ GB SSD
- Открытые порты:
  - `22/tcp` (SSH)
  - `80/tcp` и `443/tcp` (nginx)
- Исходящий доступ в интернет по `443/tcp` (для API-запросов)

## Быстрый деплой

1. Скопировать репозиторий на сервер:

```bash
git clone <repo_url> /opt/normatives
cd /opt/normatives
```

2. Запустить bootstrap:

```bash
chmod +x release/deploy/provision_ubuntu.sh
sudo ./release/deploy/provision_ubuntu.sh
```

3. Подготовить env:

```bash
cp release/.env.final.example .env.final
```

Заполните минимум:
- `YANDEX_CLOUD_API_KEY`
- `YANDEX_CLOUD_FOLDER` (если используете yandex backend)

4. Настроить bind для reverse-proxy:

```bash
echo 'WEB_SERVER_NAME=127.0.0.1' | sudo tee -a /opt/normatives/.env.final
echo 'WEB_SERVER_PORT=7860' | sudo tee -a /opt/normatives/.env.final
```

5. Включить systemd сервис:

```bash
sudo cp release/deploy/systemd/normatives-rag.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now normatives-rag
sudo systemctl status normatives-rag --no-pager
```

6. Включить nginx:

```bash
sudo cp release/deploy/nginx/normatives-rag.conf /etc/nginx/sites-available/normatives-rag
sudo ln -sf /etc/nginx/sites-available/normatives-rag /etc/nginx/sites-enabled/normatives-rag
sudo nginx -t
sudo systemctl reload nginx
```

## Очистка временных файлов перед сдачей

```bash
chmod +x release/deploy/cleanup_coursework_artifacts.sh
./release/deploy/cleanup_coursework_artifacts.sh
```

Скрипт удаляет временные eval/qa артефакты и оставляет финальный комплект `iter4_full_*_keyretry*`.

## Проверка

- Локально на сервере:
  - `curl -I http://127.0.0.1:7860`
- Снаружи:
  - `curl -I http://<SERVER_PUBLIC_IP>`

## Примечание по API

Чтобы веб-сервер мог общаться с API, достаточно:
- корректного `YANDEX_CLOUD_API_KEY` (или `AITUNNEL_API_KEY`);
- исходящего `443/tcp`;
- рабочей DNS-резолюции на сервере.
